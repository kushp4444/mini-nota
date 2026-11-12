"""Lightweight application dispatcher with optional durable PostgreSQL ownership."""
import asyncio
import base64
import hmac
import hashlib
import json
import math
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from .catalog import patients, model_metadata
from .run_repository import RunRepository, Conflict

runs = {}
launches = {}
WORKER_CONTEXT = secrets.token_urlsafe(24)
CHECKPOINT_LIMIT = 4_000_000
_repositories = {}

def repository():
    url = os.environ.get('RUN_DATABASE_URL')
    if not url:
        return None
    if url not in _repositories:
        repo = RunRepository(url)
        _repositories[url] = repo
    return _repositories[url]

def artifact_store():
    if os.environ.get('LOCAL_ARTIFACT_DIR'):
        from .local_artifacts import LocalArtifactStore
        return LocalArtifactStore(os.environ['LOCAL_ARTIFACT_DIR'])
    from .object_storage import ArtifactStore
    return ArtifactStore.from_env(role='results')

def durable_secret(run_id):
    return hmac.new(os.environ['CHECKPOINT_SIGNING_KEY'].encode(), ('run-control:' + run_id).encode(), hashlib.sha256).hexdigest()

def persist(run, **kwargs):
    repo = repository()
    if repo:
        repo.publish(run, **kwargs)

@asynccontextmanager
async def control(run):
    repo = repository()
    if repo:
        async with repo.control(run['id']):
            fresh = repo.authorize(run['id'],run['secret'])
            run.clear()
            run.update(fresh)
            yield
    else:
        async with run.setdefault('control_lock', asyncio.Lock()):
            yield

async def owned_execution(run, phase='imaging', generation=0):
    repo = repository()
    if repo:
        operation = repo.operation(run['id'],phase,generation)
        owner = 'local:' + str(uuid.uuid4())
        fence = repo.claim(operation['id'], owner)
        if fence is None:
            return
        run['_operation'] = {'id':operation['id'],'owner':owner,'fence':fence}
    try:
        if phase == 'imaging':
            await execute(run)
        else:
            await score_run(run, checkpoint_rows(run['checkpoint']))
    except Conflict:
        # A concurrent cancel/control transaction fenced this worker out.
        return

def checkpoint_rows(checkpoint):
    return [{'patient_id':r['patient_id'],'feature_schema':checkpoint['feature_schema'],
             'feature_version':checkpoint['feature_version'],
             'values':dict(zip(checkpoint['feature_schema'],r['values']))} for r in checkpoint['feature_rows']]


def checkpoint_bytes(value):
    # IEEE-754 identity survives JSON.stringify's decimal formatting (1.0, -0,
    # exponent notation, and large integral feature values). Counts stay small.
    def normalize(item):
        if type(item) in (int,float):
            number = float(item)
            if not math.isfinite(number):
                raise ValueError('Nonfinite checkpoint number')
            return 0.0 if number == 0 else number
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if isinstance(item, dict):
            return {k:normalize(v) for k,v in item.items()}
        return item
    return json.dumps(normalize(value), sort_keys=True, allow_nan=False, separators=(',', ':')).encode()

def checkpoint_signature_digest(body, digest):
    key = os.environ['CHECKPOINT_SIGNING_KEY']
    return hmac.new(key.encode(), checkpoint_bytes(body) + b'\0' + digest.encode(), hashlib.sha256).hexdigest()

def checkpoint_signature(body, secret):
    # Workers can sign a new gate with the stored digest without recovering
    # the capability. Legacy raw-secret signatures remain valid on restore.
    return checkpoint_signature_digest(body,hashlib.sha256(secret.encode()).hexdigest())

def valid_checkpoint_signature(body, secret, signature):
    legacy = hmac.new(os.environ['CHECKPOINT_SIGNING_KEY'].encode(),checkpoint_bytes(body) + b'\0' + secret.encode(),hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature,checkpoint_signature(body,secret)) or hmac.compare_digest(signature,legacy)

def last_sequence(run):
    return run.get('sequence_base', 0) + len(run['events'])

RETENTION_SECONDS = float(os.environ.get('RUN_RETENTION_SECONDS', '3600'))

@asynccontextmanager
async def lifespan(app):
    if len(os.environ.get('CHECKPOINT_SIGNING_KEY', '')) < 32:
        raise RuntimeError('Set CHECKPOINT_SIGNING_KEY to a stable operator secret of at least 32 characters; retain it across runner replacements for saved approvals')
    async def cleanup():
        while True:
            await asyncio.sleep(float(os.environ.get('RUN_CLEANUP_INTERVAL', '60')))
            for key, run in list(runs.items()):
                if not repository() and run['status'] in ('completed', 'failed', 'canceled') and time.monotonic() - run['touched'] > RETENTION_SECONDS:
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
    seq = last_sequence(run) + 1
    run['events'].append({'id': f"{run['id']}:{seq}", 'run_id': run['id'],
        'sequence': seq, 'timestamp': datetime.now(timezone.utc).isoformat(),
        'kind': kind, 'message': message, 'payload': payload or {}})
    run['touched'] = time.monotonic()
    repo = repository()
    if repo:
        try:
            # Upload before metadata publication. Include the operation fence in
            # the key so a rejected writer cannot occupy another attempt's key.
            for event in run['events']:
                event_payload = event['payload']
                artifacts = [*event_payload.get('artifacts',[]), *event_payload.get('patient',{}).get('artifacts',[])]
                for index, artifact in enumerate(artifacts):
                    if 'data_base64' in artifact:
                        data = base64.b64decode(artifact['data_base64'],validate=True)
                        operation = run.get('_operation',{})
                        identity = f"{operation.get('id','restored')}-{operation.get('fence',0)}-{event['sequence']}-{index}"
                        artifact['object_ref'] = artifact_store().publish(run['id'],identity,data,artifact.get('media_type','application/octet-stream'))
                        artifact['url'] = f"/api/runs/{run['id']}/artifacts/{event['sequence']}/{index}"
                        del artifact['data_base64']
            persist(run, operation=run.get('_operation'), approve=kind == 'decision' and (payload or {}).get('action') == 'approve')
        except Exception:
            # A failed upload/publication must not contaminate the next audit
            # write with unpublished stage data or an unpersisted event.
            runtime = {key:value for key,value in run.items() if key in {'secret','task','control_lock','_operation'}}
            saved = repo.get(run['id'])
            run.clear()
            run.update(saved)
            run.update(runtime)
            raise

def public_value(value):
    if isinstance(value,dict):
        return {key:public_value(item) for key,item in value.items() if key != 'object_ref'}
    if isinstance(value,list):
        return [public_value(item) for item in value]
    return value

async def invoke_stage(stage, patient_id, run_id=None):
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(os.environ.get('ENGINE_URL', 'http://127.0.0.1:8001') + '/' + stage,
            headers={'Authorization': f"Bearer {os.environ.get('ENGINE_SECRET', '')}"},
            json={'patient_ids': [patient_id], 'operation_id': run_id})
        response.raise_for_status()
        result = response.json()
    return result['patients'][0]

async def invoke_model_tool(stage, run, rows):
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(os.environ.get('ENGINE_URL', 'http://127.0.0.1:8001') + '/' + stage,
            headers={'Authorization': f"Bearer {os.environ.get('ENGINE_SECRET', '')}"},
            json={'patient_ids':[r['patient_id'] for r in rows], 'operation_id':run['id'],
                  'feature_rows':rows, 'model_version':run['model']['model_version'],
                  'expected_eligibility':run['eligibility'] if stage == 'score' else None})
        response.raise_for_status()
        return response.json()


async def execute(run):
    emit(run, 'plan', f"Check {len(run['patient_ids'])} selected patients with real DICOM QC, construct verified tumor masks, then extract radiomic features and score eligible held-out patients with the frozen model.", {'model':run['model']})
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

        rows = [p for p in run['stage_results']['features'] if p['status'] == 'success']
        failed = []
        for stage in ('qc','masks','features'):
            failed.extend({'patient_id':p['patient_id'],'stage':stage,'errors':p['errors']}
                          for p in run['stage_results'][stage] if p['status'] != 'success')
        report = {'scoring_eligible':[p['patient_id'] for p in rows], 'evaluation_eligible':[],
                  'evaluation_exclusions':[], 'processing_exclusions':failed}
        if rows:
            if not run['model']:
                raise RuntimeError('Frozen model metadata is not configured')
            emit(run,'tool_call','Prepare scoring and outcome eligibility.',{'stage':'eligibility'})
            prepared = await invoke_model_tool('eligibility',run,rows)
            if run['status'] != 'running': return
            report.update(prepared)
            report['processing_exclusions'] = failed
        report = disposition_report(run, report)
        run['eligibility'] = report
        emit(run,'decision',f"{len(rows)} scoring-eligible patients; {len(report['evaluation_eligible'])} evaluation-eligible patients.",
             {'stage':'eligibility','report':report})
        if not rows:
            run['status'] = 'failed'
            reason = 'No patients remain eligible for scoring.'
            emit(run,'done',reason,{'status':'failed','reason':reason,'code':'no_scoreable_patients','eligibility':report})
            return
        if failed or report['evaluation_exclusions']:
            disclose(run, rows, report)
            return
        await score_run(run, rows)
    except Exception as exc:
        if run['status'] != 'running':
            return
        run['status'] = 'failed'
        if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code == 422:
            emit(run,'error','Frozen-model input rejected; scoring stopped and available results retained.',{'code':'incompatible_model_input','errors':exc.response.json().get('detail',[])})
        else:
            emit(run, 'error', 'Imaging or model service unavailable; available patient results retained.', {'code': 'engine_unavailable'})
        emit(run, 'done', 'Run failed.', {'status': 'failed'})

def disposition_report(run, report):
    """Account for every selected identity before any score is computed."""
    report = dict(report)
    scoring = set(report['scoring_eligible'])
    evaluation = set(report['evaluation_eligible'])
    processing = {p['patient_id']:p for p in report['processing_exclusions']}
    exclusions = {p['patient_id']:p for p in report['evaluation_exclusions']}
    if scoring | set(processing) != set(run['patient_ids']) or scoring & set(processing):
        raise ValueError('Eligibility did not account for every selected patient')
    if evaluation | set(exclusions) != scoring or evaluation & set(exclusions):
        raise ValueError('Outcome join did not account for every scoreable patient')
    report['dispositions'] = [
        {'patient_id':pid,'scoring_eligible':pid in scoring,'evaluation_eligible':pid in evaluation,
         'reasons':processing[pid]['errors'] if pid in processing else ([exclusions[pid]] if pid in exclusions else []),
         'stage':processing[pid]['stage'] if pid in processing else 'eligibility'} for pid in run['patient_ids']]
    report['scoring_eligible_count'] = len(scoring)
    report['evaluation_eligible_count'] = len(evaluation)
    return report


def build_checkpoint(run, rows, report):
    # Only the numeric model input contract, never artifacts or executable paths.
    compact = [{'patient_id':row['patient_id'],'values':[row['values'][name] for name in row['feature_schema']]} for row in rows]
    body = {'version':1,'generation':run.get('gate_generation',0),'run_id':run['id'],'patient_ids':run['patient_ids'],
            'model_version':run['model']['model_version'],'feature_version':run['model']['feature_version'],
            'feature_schema':rows[0]['feature_schema'],'feature_rows':compact,'eligibility':report}
    body['disclosure_id'] = hashlib.sha256(checkpoint_bytes(body)).hexdigest()
    body['last_sequence'] = last_sequence(run) + 1
    body['signature'] = checkpoint_signature(body,run['secret']) if 'secret' in run else checkpoint_signature_digest(body,run['_secret_digest'])
    return body


def disclose(run, rows, report):
    run['gate_generation'] = run.get('gate_generation',0) + 1
    run['eligibility'] = report
    run['checkpoint'] = build_checkpoint(run, rows, report)
    run['status'] = 'waiting_approval'
    emit(run,'gate',f"Approval required: {report['scoring_eligible_count']} scoring-eligible; {report['evaluation_eligible_count']} evaluation-eligible patients. Exclusions are disclosed by patient. Waiting has no deadline.",
         {'status':'waiting_approval','report':report,'checkpoint':run['checkpoint']})


async def score_run(run, rows):
    try:
        emit(run,'tool_call',f"Frozen model scoring · {len(rows)} patients",{'stage':'score','model_version':run['model']['model_version']})
        scored = await invoke_model_tool('score',run,rows)
        if run['status'] != 'running': return
        for patient in scored['patients']:
            run['stage_results']['score'].append(patient)
            emit(run,'tool_result',f"{patient['patient_id']}: frozen-model risk score ready.",{'stage':'score','patient':patient})
        run['evaluation'] = scored.get('evaluation')
        if run['evaluation'] is not None:
            emit(run,'tool_result','Selected-cohort evaluation prepared.',{'stage':'evaluation','evaluation':run['evaluation']})
        run['status'] = 'completed'
        emit(run,'done',f"All four tools complete: {len(scored['patients'])} selected held-out patients scored with {run['model']['model_version']}.",
             {'status':'completed','selected':len(run['patient_ids']),'scored':len(scored['patients']),'model_version':run['model']['model_version']})
    except Exception as exc:
        if run['status'] != 'running': return
        if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code == 422 and 'Eligibility changed' in exc.response.text:
            try:
                prepared = await invoke_model_tool('eligibility',run,rows)
                if run['status'] != 'running': return
                report = disposition_report(run,{**prepared,'processing_exclusions':run['eligibility']['processing_exclusions']})
                disclose(run,rows,report)
                return
            except Exception:
                pass
        run['status'] = 'failed'
        emit(run,'error','Model scoring failed; available results retained.',{'code':'scoring_failed'})
        emit(run,'done','Run failed.',{'status':'failed','reason':'Model scoring failed.'})


class Approval(BaseModel):
    disclosure_id: str
    model_version: str


@app.post('/runs/{run_id}/approve')
async def approve_run(run_id: str, approval: Approval, authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    async with control(run):
        checkpoint = run.get('checkpoint')
        if not checkpoint or approval.disclosure_id != checkpoint['disclosure_id'] or approval.model_version != checkpoint['model_version']:
            raise HTTPException(409,'Approval does not match the disclosed cohort and model')
        if run.get('approved_disclosure') == approval.disclosure_id or run['status'] in ('completed','failed','canceled'):
            return {'id':run_id,'status':run['status']}
        if run['status'] != 'waiting_approval':
            raise HTTPException(409,'Run is not waiting for approval')
        rows = [{'patient_id':r['patient_id'],'feature_schema':checkpoint['feature_schema'],'feature_version':checkpoint['feature_version'],
                 'values':dict(zip(checkpoint['feature_schema'],r['values']))} for r in checkpoint['feature_rows']]
        try:
            prepared = await invoke_model_tool('eligibility',run,rows)
        except Exception:
            raise HTTPException(503,'Cannot verify the disclosed cohort and model; approval remains pending')
        report = disposition_report(run,{**prepared,'processing_exclusions':run['eligibility']['processing_exclusions']})
        current = build_checkpoint(run,rows,report)
        if current['disclosure_id'] != checkpoint['disclosure_id']:
            disclose(run,rows,report)
            raise HTTPException(409,'Eligibility changed; review the new disclosure before approving')
        run['approved_disclosure'] = approval.disclosure_id
        run['status'] = 'running'
        emit(run,'decision','Anonymous run approval recorded for the disclosed cohort and frozen model.',
             {'action':'approve','disclosure_id':approval.disclosure_id,'model_version':approval.model_version,'report':report,'status':'running'})
        if os.environ.get('EXECUTION_BACKEND','local') == 'local':
            run['task'] = asyncio.create_task(owned_execution(run,'scoring',run['gate_generation']))
        return {'id':run_id,'status':run['status']}


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
    repo = repository()
    if repo:
        existing = repo.authorize(run_id, durable_secret(run_id))
        if existing:
            if existing['patient_ids'] != ids:
                raise HTTPException(409,'Launch nonce was already used for a different selection')
            return {'id':existing['id'],'secret':existing['secret'],'status':existing['status']}
    if not repo and nonce and selection.worker_context != WORKER_CONTEXT:
        await stop_lost_launch(run_id)
    old = launches.get(nonce) if nonce and not repo else None
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
    model = await asyncio.to_thread(model_metadata)
    # Recheck after all lookups: concurrent retries create only one task.
    if not repo and nonce and nonce in launches:
        return await create_run(selection)
    run = {'id': run_id, 'secret': durable_secret(run_id) if repo else secrets.token_urlsafe(32), 'status': 'running',
           'patient_ids': ids, 'patients': [], 'model':model, 'eligibility':None, 'checkpoint':None, 'evaluation':None, 'stage_results': {'qc': [], 'masks': [], 'features': [], 'score': []}, 'events': [], 'touched': time.monotonic()}
    if repo:
        try:
            run, created = repo.create(run,nonce)
        except Conflict as exc:
            raise HTTPException(409,str(exc))
        if not created:
            return {'id':run['id'],'secret':run['secret'],'status':run['status']}
    runs[run['id']] = run
    if nonce:
        launches[nonce] = {'id': run['id'], 'patient_ids': list(ids)}
    if os.environ.get('EXECUTION_BACKEND','local') == 'local':
        run['task'] = asyncio.create_task(owned_execution(run))
    return {'id': run['id'], 'secret': run['secret'], 'status': run['status']}

def authorized(run_id, authorization):
    repo = repository()
    if repo:
        try:
            run = repo.authorize(run_id,authorization.removeprefix('Bearer '))
        except PermissionError:
            raise HTTPException(403,'Run access denied')
    else:
        run = runs.get(run_id)
    if run is None:
        raise HTTPException(404, 'Run unavailable')
    if not hmac.compare_digest(authorization, f"Bearer {run['secret']}"):
        raise HTTPException(403, 'Run access denied')
    return run


@app.post('/runs/restore')
async def restore_run(request: Request, authorization: str = Header(default='')):
    # Enforce actual streamed bytes before parsing; below Vercel's 4.5 MB bound.
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > CHECKPOINT_LIMIT:
            raise HTTPException(413, 'Saved approval is too large; start a new run')
    invalid = 'Saved approval is incomplete, incompatible, or cannot be verified. Keep local History and start a new run.'
    try:
        checkpoint = json.loads(raw)['checkpoint']
        body = {k:v for k,v in checkpoint.items() if k != 'signature'}
        secret = authorization.removeprefix('Bearer ')
        if not authorization.startswith('Bearer ') or not secret or not valid_checkpoint_signature(body,secret,checkpoint['signature']):
            raise ValueError('signature')
        fields = {'version','generation','run_id','patient_ids','model_version','feature_version',
                  'feature_schema','feature_rows','eligibility','disclosure_id','last_sequence'}
        if set(body) != fields or body['version'] != 1:
            raise ValueError('version')
        if any(type(body[k]) is not int or body[k] < 1 for k in ('last_sequence','generation')):
            raise ValueError('cursor')
        if not isinstance(body['run_id'],str) or not 1 <= len(body['run_id']) <= 128:
            raise ValueError('identity')
        content = {k:v for k,v in body.items() if k not in ('disclosure_id','last_sequence')}
        if hashlib.sha256(checkpoint_bytes(content)).hexdigest() != body['disclosure_id']:
            raise ValueError('content')
        ids, schema = body['patient_ids'], body['feature_schema']
        known = {p['id'] for p in await asyncio.to_thread(patients)}
        model = await asyncio.to_thread(model_metadata)
        if (not ids or len(ids) != len(set(ids)) or not set(ids) <= known or not model or
            body['model_version'] != model['model_version'] or body['feature_version'] != model['feature_version'] or schema != model['feature_schema']):
            raise ValueError('deployed library or model changed')
        rows = []
        for row in body['feature_rows']:
            if set(row) != {'patient_id','values'} or len(row['values']) != len(schema) or any(type(n) not in (int,float) or not math.isfinite(n) for n in row['values']):
                raise ValueError('numeric inputs')
            rows.append({'patient_id':row['patient_id'],'status':'success','feature_schema':schema,
                         'feature_version':body['feature_version'],'values':dict(zip(schema,row['values'])),'artifacts':[],'errors':[]})
        if not rows or [r['patient_id'] for r in rows] != body['eligibility']['scoring_eligible'] or len(rows) != len({r['patient_id'] for r in rows}):
            raise ValueError('eligible patients')
        run = {'id':body['run_id'],'secret':secret,'status':'waiting_approval','patient_ids':ids,
               'patients':[],'model':model,'eligibility':body['eligibility'],'checkpoint':checkpoint,
               'evaluation':None,'stage_results':{'qc':[],'masks':[],'features':rows,'score':[]},
               'events':[],'sequence_base':body['last_sequence'],'gate_generation':body['generation'],
               'touched':time.monotonic()}
        if disposition_report(run,body['eligibility']) != body['eligibility']:
            raise ValueError('dispositions')
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise HTTPException(422, invalid)
    # No await between checking ownership and publishing the recovered run.
    existing = authorized(run['id'],authorization) if repository() and repository().get(run['id']) else runs.get(run['id'])
    if existing is not None:
        authorized(run['id'], authorization)
        if existing.get('checkpoint',{}).get('disclosure_id') != body['disclosure_id']:
            raise HTTPException(409, 'A newer disclosure exists; reconnect and review the current gate')
        return {'id':existing['id'],'status':existing['status']}
    if repository():
        run, _ = repository().create(run,phase=None)
    runs[run['id']] = run
    return {'id':run['id'],'status':run['status']}

@app.get('/runs/{run_id}')
def get_run(run_id: str, authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    return public_value({**{key: run[key] for key in ('id', 'status', 'patient_ids', 'patients', 'stage_results', 'events', 'model', 'eligibility', 'checkpoint', 'evaluation')},
            'sequence_base':run.get('sequence_base',0),'last_sequence':last_sequence(run)})

@app.get('/runs/{run_id}/events')
async def events(run_id: str, after: int = Query(default=0, ge=0), authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    if after < run.get('sequence_base',0) or after > last_sequence(run):
        raise HTTPException(409, 'Reconnect from the saved checkpoint audit cursor')
    async def stream():
        cursor = after
        while True:
            if repository():
                run.update(authorized(run_id,authorization))
            for event in run['events'][max(0,cursor-run.get('sequence_base',0)):]:
                yield f"id: {event['id']}\ndata: {json.dumps(public_value(event))}\n\n"
                cursor = event['sequence']
            # A producer can finish while an earlier yielded event is in flight.
            # Drain its final batch (including done) before closing the stream.
            if run['status'] in ('completed', 'failed', 'canceled', 'waiting_approval') and cursor >= last_sequence(run):
                break
            await asyncio.sleep(0.05)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

# Bounded, reconnectable delivery for function-hosted application proxies. Artifact
# bytes are fetched separately, so replay never aggregates a cohort's images.
@app.get('/runs/{run_id}/event-page')
def event_page(run_id: str, after: int = Query(default=0, ge=0),
               limit: int = Query(default=20, ge=1, le=50), authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    if after < run.get('sequence_base',0):
        raise HTTPException(409, 'Earlier audit events remain in browser History; reconnect from the saved checkpoint cursor')
    if after > last_sequence(run):
        raise HTTPException(409, 'Event cursor is ahead of temporary runner state')
    page = []
    size = 0
    for event in run['events'][after-run.get('sequence_base',0):after-run.get('sequence_base',0) + limit]:
        item = json.loads(json.dumps(event))
        payload = item['payload']
        artifacts = [*payload.get('artifacts', []), *payload.get('patient', {}).get('artifacts', [])]
        for index, artifact in enumerate(artifacts):
            if artifact.pop('data_base64', None) is not None or 'object_ref' in artifact:
                artifact['url'] = f"/api/runs/{run_id}/artifacts/{event['sequence']}/{index}"
        item = public_value(item)
        encoded_size = len(json.dumps(item).encode())
        if size + encoded_size > 512_000:
            if not page:
                raise HTTPException(413, 'A structured event exceeds the delivery limit')
            break
        page.append(item)
        size += encoded_size
    return {'id': run_id, 'status': run['status'], 'events': page,
            'next_sequence': page[-1]['sequence'] if page else after,
            'last_sequence': last_sequence(run)}

@app.get('/runs/{run_id}/artifacts/{sequence}/{index}')
def artifact_bytes(run_id: str, sequence: int, index: int, authorization: str = Header(default='')):
    import base64
    from fastapi.responses import Response
    run = authorized(run_id, authorization)
    try:
        if sequence <= run.get('sequence_base',0) or index < 0:
            raise IndexError
        payload = run['events'][sequence - run.get('sequence_base',0) - 1]['payload']
        artifacts = [*payload.get('artifacts', []), *payload.get('patient', {}).get('artifacts', [])]
        artifact = artifacts[index]
        data = artifact_store().read(run_id,artifact['object_ref']) if 'object_ref' in artifact else base64.b64decode(artifact['data_base64'], validate=True)
    except (IndexError, KeyError, ValueError):
        raise HTTPException(404, 'Generated artifact bytes are no longer available')
    return Response(data, media_type=artifact.get('media_type', 'application/octet-stream'),
                    headers={'Cache-Control': 'no-store'})

@app.post('/runs/{run_id}/cancel')
async def cancel_run(run_id: str, authorization: str = Header(default='')):
    run = authorized(run_id, authorization)
    async with control(run):
        if run['status'] in ('completed', 'failed', 'canceled'):
            return {'id': run_id, 'status': run['status']}
        # Freeze the run before awaiting the private engine: late responses cannot
        # append results or advance it while the process termination is in flight.
        run['status'] = 'canceling'
        persist(run,cancel=True)
        if repository() and any(not owner['owner'].startswith('local:') for owner in repository().active_owners(run_id)):
            # #18 supplies provider cancellation/reconciliation. Local engine
            # acknowledgement cannot prove a remote invocation has stopped.
            raise HTTPException(503,'Remote worker stop is not confirmed; cancellation intent is saved')
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(os.environ.get('ENGINE_URL', 'http://127.0.0.1:8001') + f'/operations/{run_id}/cancel',
                    headers={'Authorization': f"Bearer {os.environ.get('ENGINE_SECRET', '')}"})
                response.raise_for_status()
        except Exception:
            # Do not claim that computation stopped if the worker did not confirm.
            raise HTTPException(503, 'Cancellation not confirmed by imaging worker; retry cancellation')
        task = runs.get(run_id,run).get('task')
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        run['status'] = 'canceled'
        emit(run, 'done', 'Run canceled by visitor; available results retained.', {'status': 'canceled', 'reason': 'Canceled by visitor'})
        return {'id': run_id, 'status': 'canceled'}


@app.get('/runs/{run_id}/results')
def run_results(run_id: str, authorization: str = Header(default='')):
    """Small query surface for GraphQL; control/replay stays on run endpoints."""
    run = authorized(run_id,authorization)
    return {'id':run_id,'status':run['status'],'patient_ids':run['patient_ids'],
            'model_version':run['model']['model_version'] if run['model'] else None,
            'scores':[{'patient_id':p['patient_id'],**p['values']} for p in run['stage_results']['score']],
            'eligibility':run['eligibility'],'evaluation':run.get('evaluation')}
