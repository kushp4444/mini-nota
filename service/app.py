"""Temporary runner service behind the Next.js application API.

Runs/events exist only in memory. There is deliberately no public run listing.
"""
import asyncio
import hmac
import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from .catalog import patients

runs = {}
RETENTION_SECONDS = 3600

@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            await asyncio.sleep(60)
            for key, run in list(runs.items()):
                if run['status'] != 'running' and time.monotonic() - run['touched'] > RETENTION_SECONDS:
                    del runs[key]
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
class Selection(BaseModel):
    patient_ids: list[str]

def emit(run, kind, message, payload=None):
    seq = len(run['events']) + 1
    run['events'].append({'id': f"{run['id']}:{seq}", 'run_id': run['id'],
        'sequence': seq, 'timestamp': datetime.now(timezone.utc).isoformat(),
        'kind': kind, 'message': message, 'payload': payload or {}})
    run['touched'] = time.monotonic()

async def execute(run):
    emit(run, 'plan', f"Check {len(run['patient_ids'])} selected patients with real DICOM QC.")
    try:
        for patient_id in run['patient_ids']:
            emit(run, 'tool_call', f'QC · {patient_id}', {'stage': 'qc', 'patient_id': patient_id})
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(os.environ.get('ENGINE_URL', 'http://127.0.0.1:8001') + '/qc',
                    headers={'Authorization': f"Bearer {os.environ.get('ENGINE_SECRET', '')}"},
                    json={'patient_ids': [patient_id]})
                response.raise_for_status()
                result = response.json()
            patient = result['patients'][0]
            run['patients'].append(patient)
            emit(run, 'tool_result', f"{patient_id}: QC {patient['status']}", {'stage': 'qc', 'patient': patient})
            if patient['errors']:
                emit(run, 'error', f'{patient_id}: scan checks failed; patient excluded.', {'patient_id': patient_id, 'errors': patient['errors']})
            emit(run, 'decision', f"{patient_id}: {'passed QC' if patient['status'] == 'success' else 'excluded from further processing'}.", {'patient_id': patient_id, 'eligible': patient['status'] == 'success'})
        run['status'] = 'completed'
        emit(run, 'done', 'QC complete. Mask, feature, and scoring stages are not part of this fixture slice.', {'status': 'completed', 'selected': len(run['patient_ids']), 'passed': sum(p['status'] == 'success' for p in run['patients'])})
    except Exception:
        run['status'] = 'failed'
        emit(run, 'error', 'QC service unavailable; available patient results retained.', {'code': 'engine_unavailable'})
        emit(run, 'done', 'Run failed.', {'status': 'failed'})

@app.post('/runs', status_code=201)
async def create_run(selection: Selection):
    ids = selection.patient_ids
    known = {p['id'] for p in await asyncio.to_thread(patients)}
    if not ids or len(ids) != len(set(ids)) or not set(ids).issubset(known):
        raise HTTPException(422, 'Select one or more distinct patients from the available catalog')
    run = {'id': str(uuid.uuid4()), 'secret': secrets.token_urlsafe(32), 'status': 'running',
           'patient_ids': ids, 'patients': [], 'events': [], 'touched': time.monotonic()}
    runs[run['id']] = run
    run['task'] = asyncio.create_task(execute(run))
    return {'id': run['id'], 'secret': run['secret'], 'status': run['status']}

def authorized(run_id, authorization):
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(404, 'Temporary run unavailable')
    if not hmac.compare_digest(authorization, f"Bearer {run['secret']}"):
        raise HTTPException(403, 'Run access denied')
    return run

@app.get('/runs/{run_id}')
def get_run(run_id: str, authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    return {key: run[key] for key in ('id', 'status', 'patient_ids', 'patients', 'events')}

@app.get('/runs/{run_id}/events')
async def events(run_id: str, after: int = Query(default=0, ge=0), authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    async def stream():
        cursor = after
        while True:
            for event in run['events'][cursor:]:
                yield f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"
                cursor = event['sequence']
            if run['status'] != 'running':
                break
            await asyncio.sleep(0.05)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
