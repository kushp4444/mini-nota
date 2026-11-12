"""Public API against real Postgres and a real HTTP FastAPI imaging worker."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
import psycopg
import pydicom
import pytest
from fastapi.testclient import TestClient
from service.app import app
from service.catalog import DATABASE_URL
from test_engine import write_scan
from test_masks_geometry import physical_tumor
from test_features import varied_tumor

@pytest.fixture(scope='module')
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp('api-dicom')
    varied_tumor(root, 'TEST-CLEAN')
    physical_tumor(root, 'TEST-CONSTANT')
    write_scan(root, 'TEST-NO-MASK')
    ct = write_scan(root, 'TEST-PRIVACY')
    ds = pydicom.dcmread(ct / '3.dcm')
    ds.PatientName = 'PRIVATE_VALUE_DO_NOT_DISPLAY'
    ds.save_as(ct / '3.dcm', enforce_file_format=True)
    (root / 'TEST-BROKEN' / 'ct').mkdir(parents=True)
    (root / 'TEST-BROKEN' / 'ct' / 'bad.dcm').write_text('malformed')
    ct = write_scan(root, 'TEST-SPACING')
    ds = pydicom.dcmread(ct / '3.dcm')
    ds.ImagePositionPatient = [0, 0, 10]
    ds.save_as(ct / '3.dcm', enforce_file_format=True)
    ct = write_scan(root, 'TEST-GEOMETRY')
    for path in list(ct.glob('*.dcm'))[1:]: path.unlink()
    ids = ['TEST-CONSTANT','TEST-NO-MASK','TEST-CLEAN','TEST-PRIVACY','TEST-BROKEN','TEST-SPACING','TEST-GEOMETRY']
    with psycopg.connect(DATABASE_URL) as conn:
        for pid in ids:
            conn.execute('INSERT INTO patient_catalog VALUES (%s,%s,true) ON CONFLICT DO NOTHING', (pid,'Automated test fixture'))
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); port = s.getsockname()[1]
    old = {k: os.environ.get(k) for k in ('ENGINE_SECRET','ENGINE_URL')}
    os.environ.update(ENGINE_SECRET='test-engine-secret',ENGINE_URL=f'http://127.0.0.1:{port}')
    proc = subprocess.Popen([sys.executable,'-m','uvicorn','service.engine_api:app','--port',str(port)],env={**os.environ,'RAW_DIR':str(root)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                httpx.get(f'http://127.0.0.1:{port}/health',timeout=.2);break
            except httpx.ConnectError: time.sleep(.1)
        with TestClient(app) as c: yield c
    finally:
        proc.terminate();proc.wait(timeout=10)
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute('DELETE FROM patient_catalog WHERE patient_id = ANY(%s)',(ids,))
        for k,v in old.items():
            if v is None: os.environ.pop(k,None)
            else: os.environ[k]=v

def test_rejects_empty_unknown_and_duplicate_selection(client):
    for selection in ([], ['unknown'], ['TEST-CLEAN','TEST-CLEAN']):
        assert client.post('/runs',json={'patient_ids':selection}).status_code == 422

def test_real_qc_retains_all_patients_and_emits_ordered_private_events(client):
    created=client.post('/runs',json={'patient_ids':['TEST-CLEAN','TEST-PRIVACY','TEST-BROKEN']})
    assert created.status_code == 201
    run=created.json(); url=f"/runs/{run['id']}"; headers={'Authorization':f"Bearer {run['secret']}"}
    assert client.get(url).status_code == 403
    response=client.get(url+'/events',headers=headers)
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert [e['sequence'] for e in events] == list(range(1,len(events)+1))
    assert len({e['id'] for e in events}) == len(events)
    assert events[0]['kind']=='plan' and events[-1]['kind']=='done'
    assert {'plan','tool_call','tool_result','decision','error','done'} <= {e['kind'] for e in events}
    run=client.get(url,headers=headers).json()
    assert run['status']=='completed'
    assert [p['patient_id'] for p in run['patients']]==['TEST-CLEAN','TEST-PRIVACY','TEST-BROKEN']
    clean,private,broken=run['patients']
    assert all(clean['values'][key]['passed'] for key in ('geometry','slice_spacing','anonymized'))
    assert not private['values']['anonymized']['passed']
    assert broken['status']=='failed' and broken['errors'][0]['code']=='processing_failed'
    assert 'PRIVATE_VALUE_DO_NOT_DISPLAY' not in response.text
    replay=client.get(url+'/events?after=2',headers=headers)
    assert json.loads(next(l[6:] for l in replay.text.splitlines() if l.startswith('data: ')))['sequence']==3


def test_geometry_and_spacing_failures_are_visible_by_patient(client):
    run=client.post('/runs',json={'patient_ids':['TEST-GEOMETRY','TEST-SPACING']}).json()
    headers={'Authorization':f"Bearer {run['secret']}"}
    client.get(f"/runs/{run['id']}/events",headers=headers)
    result=client.get(f"/runs/{run['id']}",headers=headers).json()
    geometry,spacing=result['patients']
    assert geometry['patient_id']=='TEST-GEOMETRY'
    assert geometry['values']['geometry']['passed'] is False
    assert spacing['patient_id']=='TEST-SPACING'
    assert spacing['values']['slice_spacing']['passed'] is False
    assert geometry['status']==spacing['status']=='failed'


def test_masks_follow_qc_and_keep_portable_overlay_bytes_and_named_failures(client):
    import base64
    import hashlib
    run = client.post('/runs', json={'patient_ids':['TEST-PRIVACY','TEST-NO-MASK','TEST-CLEAN']}).json()
    headers = {'Authorization': f"Bearer {run['secret']}"}
    url = f"/runs/{run['id']}"
    client.get(url + '/events', headers=headers)
    result = client.get(url, headers=headers).json()
    masks = result['stage_results']['masks']
    assert [p['patient_id'] for p in masks] == ['TEST-NO-MASK','TEST-CLEAN']
    assert masks[0]['errors'][0]['code'] == 'missing_rtstruct'
    assert masks[1]['values']['voxel_count'] == 27
    assert masks[1]['values']['volume_cm3'] == .324
    overlay = next(a for a in masks[1]['artifacts'] if a['role'] == 'overlay')
    data = base64.b64decode(overlay['data_base64'], validate=True)
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    assert hashlib.sha256(data).hexdigest() == overlay['sha256']
    assert all(a['role'] != 'mask' for a in masks[1]['artifacts'])
    calls = [e['payload'] for e in result['events'] if e['kind'] == 'tool_call' and e['payload'].get('stage') == 'masks']
    assert [e['patient_id'] for e in calls] == ['TEST-NO-MASK','TEST-CLEAN']
    assert any(e['kind']=='error' and e['payload'].get('stage')=='masks' and e['payload']['patient_id']=='TEST-NO-MASK' for e in result['events'])

def test_cancel_is_private_idempotent_and_terminal(client):
    run = client.post('/runs', json={'patient_ids': ['TEST-CLEAN']}).json()
    url = f"/runs/{run['id']}"
    headers = {'Authorization': f"Bearer {run['secret']}"}
    assert client.post(url + '/cancel').status_code == 403
    canceled = client.post(url + '/cancel', headers=headers)
    assert canceled.status_code == 200
    assert canceled.json()['status'] == 'canceled'
    assert client.post(url + '/cancel', headers=headers).json()['status'] == 'canceled'
    time.sleep(.2)
    snapshot = client.get(url, headers=headers).json()
    assert snapshot['status'] == 'canceled'
    assert [e['payload']['status'] for e in snapshot['events'] if e['kind'] == 'done'] == ['canceled']


def test_cancel_stops_active_process_and_late_retry_cannot_restart_it(client, tmp_path, monkeypatch):
    """Only the external numerical executable is replaced with a labeled slow fixture."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    engine_url = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'RAW_DIR': str(tmp_path), 'ENGINE_WORKER_MODULE': 'slow_engine_fixture', 'SLOW_ENGINE_STAGE': 'masks',
           'PYTHONPATH': str(Path(__file__).parent)}
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'service.engine_api:app', '--port', str(port)],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                httpx.get(engine_url + '/health', timeout=.2)
                break
            except httpx.ConnectError:
                time.sleep(.05)
        monkeypatch.setenv('ENGINE_URL', engine_url)
        run = client.post('/runs', json={'patient_ids': ['TEST-CLEAN']}).json()
        url = f"/runs/{run['id']}"
        headers = {'Authorization': f"Bearer {run['secret']}"}
        for _ in range(100):
            if (tmp_path / 'started.json').exists():
                break
            time.sleep(.02)
        started = json.loads((tmp_path / 'started.json').read_text())
        assert client.get(url, headers=headers).json()['status'] == 'running'
        canceled = client.post(url + '/cancel', headers=headers)
        assert canceled.status_code == 200 and canceled.json()['status'] == 'canceled'
        with pytest.raises(ProcessLookupError):
            os.kill(started['pid'], 0)
        assert not Path(started['workspace']).exists()
        private_headers = {'Authorization': 'Bearer test-engine-secret'}
        retry = httpx.post(engine_url + '/qc', json={'patient_ids': ['TEST-CLEAN'], 'operation_id': run['id']}, headers=private_headers)
        assert retry.status_code == 409
        assert client.post(url + '/cancel', headers=headers).json()['status'] == 'canceled'
        time.sleep(3.1)
        assert not (tmp_path / 'finished').exists()
        snapshot = client.get(url, headers=headers).json()
        assert snapshot['status'] == 'canceled'
        assert len([e for e in snapshot['events'] if e['kind'] == 'done']) == 1
        assert [e['payload']['stage'] for e in snapshot['events'] if e['kind'] == 'tool_result'] == ['qc']
        assert len(snapshot['stage_results']['qc']) == 1
        assert snapshot['stage_results']['masks'] == []
    finally:
        process.terminate()
        process.wait(timeout=10)

def test_reconnect_pages_drain_completed_run_without_snapshot_or_gaps(client):
    run = client.post('/runs', json={'patient_ids':['TEST-CLEAN']}).json()
    url = f"/runs/{run['id']}"
    headers = {'Authorization': f"Bearer {run['secret']}"}
    # No browser event subscription: runner must finish independently.
    for _ in range(200):
        response = client.get(url + '/event-page?after=0&limit=2', headers=headers)
        assert response.status_code == 200
        if response.json()['status'] != 'running': break
        time.sleep(.05)
    cursor, received = 0, []
    while True:
        page = client.get(url + f'/event-page?after={cursor}&limit=2', headers=headers).json()
        assert len(page['events']) <= 2
        received.extend(page['events'])
        cursor = page['next_sequence']
        if cursor == page['last_sequence']: break
    assert received[-1]['kind'] == 'done'
    assert [e['sequence'] for e in received] == list(range(1,cursor+1))
    replay = client.get(url + '/event-page?after=0&limit=2', headers=headers).json()
    assert replay['events'] == received[:2]
    mask = next(e for e in received if e['payload'].get('stage') == 'masks' and e['kind']=='tool_result')
    artifact = mask['payload']['patient']['artifacts'][0]
    assert 'data_base64' not in artifact
    image = client.get(artifact['url'].removeprefix('/api'), headers=headers)
    assert image.status_code == 200 and image.content.startswith(b'\x89PNG')
    assert client.get(artifact['url'].removeprefix('/api')).status_code == 403
    assert client.get(url + '/event-page',headers={'Authorization':'Bearer stale'}).status_code == 403
    assert client.get(url + f'/event-page?after={cursor+1}',headers=headers).status_code == 409
    assert client.get('/runs/absent/event-page',headers=headers).status_code == 404


def test_features_are_progressive_portable_and_retain_partial_failures(client):
    import base64
    import csv
    import hashlib
    import io
    run = client.post('/runs', json={'patient_ids':['TEST-NO-MASK','TEST-CONSTANT','TEST-CLEAN']}).json()
    headers = {'Authorization': f"Bearer {run['secret']}"}
    url = f"/runs/{run['id']}"
    response = client.get(url + '/events', headers=headers)
    result = client.get(url, headers=headers).json()
    bad, good = result['stage_results']['features']
    assert bad['patient_id'] == 'TEST-CONSTANT' and bad['errors'][0]['code'] == 'invalid_feature_input'
    assert good['patient_id'] == 'TEST-CLEAN' and good['status'] == 'success'
    assert len(good['feature_schema']) == 72
    assert good['values']['original_shape_VoxelVolume'] == 324
    artifact = next(a for a in good['artifacts'] if a['media_type'] == 'text/csv')
    data = base64.b64decode(artifact['data_base64'], validate=True)
    assert hashlib.sha256(data).hexdigest() == artifact['sha256']
    assert list(csv.DictReader(io.StringIO(data.decode())))[0]['patient_id'] == 'TEST-CLEAN'
    assert len(result['stage_results']['qc']) == 3 and len(result['stage_results']['masks']) == 3
    feature_events = [e for e in result['events'] if e['kind']=='tool_result' and e['payload'].get('stage')=='features']
    assert [e['payload']['patient']['patient_id'] for e in feature_events] == ['TEST-CONSTANT','TEST-CLEAN']
    assert any(e['kind']=='error' and e['payload'].get('stage')=='features' and e['payload']['patient_id']=='TEST-CONSTANT' for e in result['events'])
    assert 'Frozen-model scoring is not yet connected' in result['events'][-1]['message']
    assert 'NaN' not in response.text


def test_cancellation_after_completion_keeps_original_terminal_result(client):
    run = client.post('/runs', json={'patient_ids': ['TEST-CLEAN']}).json()
    headers = {'Authorization': f"Bearer {run['secret']}"}
    url = f"/runs/{run['id']}"
    client.get(url + '/events', headers=headers)
    before = client.get(url, headers=headers).json()
    assert before['status'] == 'completed'
    assert client.post(url + '/cancel', headers=headers).json()['status'] == 'completed'
    assert client.get(url, headers=headers).json() == before


def test_launch_nonce_recovers_same_run_after_lost_response_and_rejects_reuse(client):
    import secrets
    context = client.get('/runs/launch-context').json()
    request = {'patient_ids':['TEST-CLEAN'], 'launch_nonce': secrets.token_urlsafe(32), 'worker_context': context['worker_context']}
    first = client.post('/runs',json=request)
    assert first.status_code == 201
    replay = client.post('/runs',json=request)
    assert replay.status_code == 201 and replay.json()['id'] == first.json()['id']
    assert replay.json()['secret'] == first.json()['secret']
    assert client.post('/runs',json={**request,'patient_ids':['TEST-NO-MASK']}).status_code == 409
    lost_worker = client.post('/runs',json={**request,'worker_context':'previous-worker'})
    assert lost_worker.status_code == 409
    assert lost_worker.json()['detail']['code'] == 'launch_interrupted'


def test_expired_launch_nonce_never_silently_restarts_computation(client):
    import secrets
    # Separate runner with short temporary retention; test only public HTTP APIs.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
    proc = subprocess.Popen([sys.executable,'-m','uvicorn','service.app:app','--port',str(port)],
        env={**os.environ,'RUN_RETENTION_SECONDS':'.1','RUN_CLEANUP_INTERVAL':'.05'},
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=10) as api:
            for _ in range(100):
                try:
                    context = api.get('/runs/launch-context').json(); break
                except httpx.ConnectError: time.sleep(.05)
            request = {'patient_ids':['TEST-CLEAN'],'launch_nonce':secrets.token_urlsafe(32),'worker_context':context['worker_context']}
            created = api.post('/runs',json=request).json()
            headers = {'Authorization':f"Bearer {created['secret']}"}
            for _ in range(400):
                page = api.get(f"/runs/{created['id']}/event-page",headers=headers)
                if page.status_code == 404: break
                time.sleep(.05)
            assert page.status_code == 404
            retry = api.post('/runs',json=request)
            assert retry.status_code == 409
            assert retry.json()['detail']['code'] == 'launch_interrupted'
    finally:
        proc.terminate();proc.wait(timeout=10)
