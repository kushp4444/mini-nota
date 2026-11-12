"""Private HTTP adapter owning ephemeral, truly cancellable engine subprocesses."""
import asyncio
import json
import os
import signal
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

@asynccontextmanager
async def lifespan(app):
    yield
    for operation in list(operations.values()):
        operation['status'] = 'canceled'
        await stop(operation['process'])

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
operations = {}
# Cancellation tombstones prevent a delayed HTTP invocation from restarting work.
# They contain opaque operation IDs only and are discarded with worker memory.
CANCEL_RETENTION_SECONDS = 3600


class Selection(BaseModel):
    patient_ids: list[str]
    operation_id: str | None = None
    feature_rows: list[dict] = []
    model_version: str | None = None
    expected_eligibility: dict | None = None


def authorize(authorization):
    secret = os.environ.get('ENGINE_SECRET')
    if not secret or authorization != f'Bearer {secret}':
        raise HTTPException(403, 'Engine access denied')


def prune():
    for key, operation in list(operations.items()):
        if operation['status'] != 'running' and time.monotonic() - operation['touched'] > CANCEL_RETENTION_SECONDS:
            del operations[key]


async def stop(process):
    if process:
        # A whole process group is owned by this operation, including any tool
        # descendants. SIGKILL also stops native numerical code without waiting
        # for Python to reach an asyncio cancellation point.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


@app.post('/qc')
async def qc(selection: Selection, authorization: str = Header(default='')):
    return await run_stage('qc', selection, authorization)


@app.post('/masks')
async def masks(selection: Selection, authorization: str = Header(default='')):
    return await run_stage('masks', selection, authorization)


@app.post('/operations/{operation_id}/cancel')
async def cancel(operation_id: str, authorization: str = Header(default='')):
    authorize(authorization)
    prune()
    was_running = operation_id in operations and operations[operation_id]['status'] == 'running'
    operation = operations.setdefault(operation_id, {'status': 'canceled', 'process': None,
        'touched': time.monotonic(), 'finished': asyncio.Event()})
    operation['status'] = 'canceled'
    operation['touched'] = time.monotonic()
    await stop(operation['process'])
    # Wait until the request owner has cleaned its temporary workspace.
    if was_running:
        await operation['finished'].wait()
    return {'status': 'canceled'}


async def run_stage(stage, selection, authorization):
    authorize(authorization)
    prune()
    operation_id = selection.operation_id or str(uuid.uuid4())
    old = operations.get(operation_id)
    if old and old['status'] == 'canceled':
        raise HTTPException(409, 'Operation canceled')
    if old and old['status'] == 'running':
        raise HTTPException(409, 'Operation already running')
    operation = {'status': 'running', 'process': None, 'touched': time.monotonic(), 'finished': asyncio.Event()}
    operations[operation_id] = operation
    try:
        with tempfile.TemporaryDirectory(prefix='mini-nota-tool-') as workspace:
            native_env = {**os.environ, **{name:os.environ.get(name,'1') for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS','ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS')}}
            process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'service.tool_entry',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=True, env=native_env,
                pass_fds=(int(os.environ['MINI_NOTA_LIFETIME_FD']),) if os.environ.get('MINI_NOTA_LIFETIME_FD') else ())
            operation['process'] = process
            if operation['status'] == 'canceled':
                await stop(process)
                raise HTTPException(409, 'Operation canceled')
            stdout, _ = await process.communicate(json.dumps({'stage': stage,
                'patient_ids': selection.patient_ids, 'feature_rows':selection.feature_rows, 'model_version':selection.model_version, 'expected_eligibility':selection.expected_eligibility, 'raw_dir': os.environ['RAW_DIR'], 'workspace': workspace}).encode())
            if operation['status'] == 'canceled':
                raise HTTPException(409, 'Operation canceled')
            if process.returncode:
                raise HTTPException(502, 'Imaging subprocess failed')
            result = json.loads(stdout)
            if stage in ('eligibility','score') and result.get('errors'):
                raise HTTPException(422, result['errors'])
            return result
    finally:
        await stop(operation['process'])
        if operation['status'] != 'canceled':
            operation['status'] = 'finished'
        operation['touched'] = time.monotonic()
        operation['finished'].set()

@app.post('/features')
async def features(selection: Selection, authorization: str = Header(default='')):
    return await run_stage('features', selection, authorization)

@app.post('/eligibility')
async def eligibility(selection: Selection, authorization: str = Header(default='')):
    return await run_stage('eligibility', selection, authorization)

@app.post('/score')
async def score(selection: Selection, authorization: str = Header(default='')):
    return await run_stage('score', selection, authorization)
