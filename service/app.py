"""Temporary runner service behind the Next.js application API.

Runs/events exist only in memory. There is deliberately no public run listing.
"""
import asyncio
import hmac
import hashlib
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
launches = {}
WORKER_CONTEXT = secrets.token_urlsafe(24)
RETENTION_SECONDS = float(os.environ.get('RUN_RETENTION_SECONDS', '3600'))

@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            await asyncio.sleep(float(os.environ.get('RUN_CLEANUP_INTERVAL', '60')))
            for key, run in list(runs.items()):
                if run['status'] in ('completed', 'failed', 'canceled') and time.monotonic() - run['touched'] > RETENTION_SECONDS:
                    del runs[key]
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
class Selection(BaseModel):
    patient_ids: list[str]
    launch_nonce: str | None = None
    worker_context: str | None = None

def emit(run, kind, message, payload=None):
    if run['status'] == 'canceled' and kind != 'done':
        return
    seq = len(run['events']) + 1
    run['events'].append({'id': f"{run['id']}:{seq}", 'run_id': run['id'],
        'sequence': seq, 'timestamp': datetime.now(timezone.utc).isoformat(),
        'kind': kind, 'message': message, 'payload': payload or {}})
    run['touched'] = time.monotonic()

async def invoke_stage(stage, patient_id, run_id=None):
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(os.environ.get('ENGINE_URL', 'http://127.0.0.1:8001') + '/' + stage,
            headers={'Authorization': f"Bearer {os.environ.get('ENGINE_SECRET', '')}"},
            json={'patient_ids': [patient_id], 'operation_id': run_id})
        response.raise_for_status()
        result = response.json()
    return result['patients'][0]

async def execute(run):
    emit(run, 'plan', f"Check {len(run['patient_ids'])} selected patients with real DICOM QC, construct verified tumor masks, then extract radiomic features for passing patients.")
    try:
        for patient_id in run['patient_ids']:
            emit(run, 'tool_call', f'QC · {patient_id}', {'stage': 'qc', 'patient_id': patient_id})
            patient = await invoke_stage('qc', patient_id, run['id'])
            if run['status'] != 'running':
                return
            run['patients'].append(patient)
            run['stage_results']['qc'].append(patient)
            emit(run, 'tool_result', f"{patient_id}: QC {patient['status']}", {'stage': 'qc', 'patient': patient})
            if patient['errors']:
                emit(run, 'error', f'{patient_id}: scan checks failed; patient excluded.', {'stage': 'qc', 'patient_id': patient_id, 'errors': patient['errors']})
            emit(run, 'decision', f"{patient_id}: {'passed QC' if patient['status'] == 'success' else 'excluded from further processing'}.", {'patient_id': patient_id, 'eligible': patient['status'] == 'success'})
        for checked in run['patients']:
            if checked['status'] != 'success':
                continue
            patient_id = checked['patient_id']
            emit(run, 'tool_call', f'Mask construction · {patient_id}', {'stage': 'masks', 'patient_id': patient_id})
            patient = await invoke_stage('masks', patient_id, run['id'])
            if run['status'] != 'running':
                return
            run['stage_results']['masks'].append(patient)
            if patient['status'] == 'success':
                values = patient['values']
                message = f"{patient_id}: mask ready · {values['voxel_count']:,} voxels · {values['volume_cm3']:.3f} cm³."
            else:
                message = f"{patient_id}: mask construction failed."
            emit(run, 'tool_result', message, {'stage': 'masks', 'patient': patient})
            if patient['errors']:
                reasons = '; '.join(error['message'] for error in patient['errors'])
                emit(run, 'error', f'{patient_id}: {reasons}; patient excluded.', {'stage': 'masks', 'patient_id': patient_id, 'errors': patient['errors']})

        for masked in run['stage_results']['masks']:
            if masked['status'] != 'success':
                continue
            patient_id = masked['patient_id']
            emit(run, 'tool_call', f'Feature extraction · {patient_id}', {'stage': 'features', 'patient_id': patient_id})
            patient = await invoke_stage('features', patient_id, run['id'])
            if run['status'] != 'running':
                return
            run['stage_results']['features'].append(patient)
            count = len(patient.get('feature_schema', []))
            message = f'{patient_id}: {count} radiomic features ready.' if patient['status'] == 'success' else f'{patient_id}: feature extraction failed.'
            emit(run, 'tool_result', message, {'stage': 'features', 'patient': patient})
            if patient['errors']:
                reasons = '; '.join(error['message'] for error in patient['errors'])
                emit(run, 'error', f'{patient_id}: {reasons}; patient excluded from scoring.', {'stage': 'features', 'patient_id': patient_id, 'errors': patient['errors']})
        if run['status'] != 'running':
            return

        run['status'] = 'completed'
        succeeded = sum(p['status'] == 'success' for p in run['stage_results']['masks'])
        featured = sum(p['status'] == 'success' for p in run['stage_results']['features'])
        emit(run, 'done', f'QC, masks and feature extraction complete: {succeeded} masks and {featured} feature rows available. Frozen-model scoring is not yet connected.', {'status': 'completed', 'selected': len(run['patient_ids']), 'passed': sum(p['status'] == 'success' for p in run['patients']), 'masks_succeeded': succeeded, 'features_succeeded': featured})
    except Exception:
        if run['status'] != 'running':
            return
        run['status'] = 'failed'
        emit(run, 'error', 'Imaging service unavailable; available patient results retained.', {'code': 'engine_unavailable'})
        emit(run, 'done', 'Run failed.', {'status': 'failed'})

@app.get('/runs/launch-context')
def launch_context():
    return {'worker_context': WORKER_CONTEXT}

async def stop_lost_launch(run_id):
    # The engine confirms its process is stopped and records a cancellation
    # tombstone, preventing a delayed old runner request from restarting work.
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(os.environ.get('ENGINE_URL', 'http://127.0.0.1:8001') + f'/operations/{run_id}/cancel',
                headers={'Authorization': f"Bearer {os.environ.get('ENGINE_SECRET', '')}"})
            response.raise_for_status()
            if response.json().get('status') != 'canceled':
                raise ValueError('Engine did not acknowledge stopped work')
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, 'Cannot confirm earlier launch has stopped; retry recovery before starting another run')
    raise HTTPException(409, {'code': 'launch_interrupted', 'message': 'Temporary launch state is gone. Earlier engine work has been stopped; results never received may be lost. Start a new run for interrupted computation.'})

@app.post('/runs', status_code=201)
async def create_run(selection: Selection):
    ids = selection.patient_ids
    nonce = selection.launch_nonce
    if nonce and (len(nonce) < 32 or len(nonce) > 128 or not all(c.isalnum() or c in '-_' for c in nonce)):
        raise HTTPException(422, 'Invalid launch recovery nonce')
    run_id = hashlib.sha256(nonce.encode()).hexdigest()[:32] if nonce else str(uuid.uuid4())
    if nonce and selection.worker_context != WORKER_CONTEXT:
        await stop_lost_launch(run_id)
    old = launches.get(nonce) if nonce else None
    if old:
        if old['patient_ids'] != ids:
            raise HTTPException(409, 'Launch nonce was already used for a different selection')
        run = runs.get(old['id'])
        if run is None:
            await stop_lost_launch(old['id'])
        return {'id': run['id'], 'secret': run['secret'], 'status': run['status']}
    known = {p['id'] for p in await asyncio.to_thread(patients)}
    if not ids or len(ids) != len(set(ids)) or not set(ids).issubset(known):
        raise HTTPException(422, 'Select one or more distinct patients from the available catalog')
    # Recheck after the catalog await: concurrent retries create only one task.
    if nonce and nonce in launches:
        return await create_run(selection)
    run = {'id': run_id, 'secret': secrets.token_urlsafe(32), 'status': 'running',
           'patient_ids': ids, 'patients': [], 'stage_results': {'qc': [], 'masks': [], 'features': []}, 'events': [], 'touched': time.monotonic()}
    runs[run['id']] = run
    if nonce:
        launches[nonce] = {'id': run['id'], 'patient_ids': list(ids)}
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
    return {key: run[key] for key in ('id', 'status', 'patient_ids', 'patients', 'stage_results', 'events')}

@app.get('/runs/{run_id}/events')
async def events(run_id: str, after: int = Query(default=0, ge=0), authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    async def stream():
        cursor = after
        while True:
            for event in run['events'][cursor:]:
                yield f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"
                cursor = event['sequence']
            # A producer can finish while an earlier yielded event is in flight.
            # Drain its final batch (including done) before closing the stream.
            if run['status'] in ('completed', 'failed', 'canceled') and cursor >= len(run['events']):
                break
            await asyncio.sleep(0.05)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

# Bounded, reconnectable delivery for function-hosted application proxies. Artifact
# bytes are fetched separately, so replay never aggregates a cohort's images.
@app.get('/runs/{run_id}/event-page')
def event_page(run_id: str, after: int = Query(default=0, ge=0),
               limit: int = Query(default=20, ge=1, le=50), authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    if after > len(run['events']):
        raise HTTPException(409, 'Event cursor is ahead of temporary runner state')
    page = []
    size = 0
    for event in run['events'][after:after + limit]:
        item = json.loads(json.dumps(event))
        payload = item['payload']
        artifacts = [*payload.get('artifacts', []), *payload.get('patient', {}).get('artifacts', [])]
        for index, artifact in enumerate(artifacts):
            if artifact.pop('data_base64', None) is not None:
                artifact['url'] = f"/api/runs/{run_id}/artifacts/{event['sequence']}/{index}"
        encoded_size = len(json.dumps(item).encode())
        if size + encoded_size > 512_000:
            if not page:
                raise HTTPException(413, 'A structured event exceeds the delivery limit')
            break
        page.append(item)
        size += encoded_size
    return {'id': run_id, 'status': run['status'], 'events': page,
            'next_sequence': page[-1]['sequence'] if page else after,
            'last_sequence': len(run['events'])}

@app.get('/runs/{run_id}/artifacts/{sequence}/{index}')
def artifact_bytes(run_id: str, sequence: int, index: int, authorization: str = Header(default='')):
    import base64
    from fastapi.responses import Response
    run = authorized(run_id, authorization)
    try:
        if sequence < 1 or index < 0:
            raise IndexError
        payload = run['events'][sequence - 1]['payload']
        artifacts = [*payload.get('artifacts', []), *payload.get('patient', {}).get('artifacts', [])]
        artifact = artifacts[index]
        data = base64.b64decode(artifact['data_base64'], validate=True)
    except (IndexError, KeyError, ValueError):
        raise HTTPException(404, 'Generated artifact bytes are no longer available')
    return Response(data, media_type=artifact.get('media_type', 'application/octet-stream'),
                    headers={'Cache-Control': 'no-store'})

@app.post('/runs/{run_id}/cancel')
async def cancel_run(run_id: str, authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    async with run.setdefault('control_lock', asyncio.Lock()):
        if run['status'] in ('completed', 'failed', 'canceled'):
            return {'id': run_id, 'status': run['status']}
        # Freeze the run before awaiting the private engine: late responses cannot
        # append results or advance it while the process termination is in flight.
        run['status'] = 'canceling'
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(os.environ.get('ENGINE_URL', 'http://127.0.0.1:8001') + f'/operations/{run_id}/cancel',
                    headers={'Authorization': f"Bearer {os.environ.get('ENGINE_SECRET', '')}"})
                response.raise_for_status()
        except Exception:
            # Do not claim that computation stopped if the worker did not confirm.
            raise HTTPException(503, 'Cancellation not confirmed by imaging worker; retry cancellation')
        task = run.get('task')
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        run['status'] = 'canceled'
        emit(run, 'done', 'Run canceled by visitor; available results retained.', {'status': 'canceled', 'reason': 'Canceled by visitor'})
        return {'id': run_id, 'status': 'canceled'}
