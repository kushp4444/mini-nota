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

@pytest.fixture(scope='module')
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp('api-dicom')
    write_scan(root, 'TEST-CLEAN')
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
    ids = ['TEST-CLEAN','TEST-PRIVACY','TEST-BROKEN','TEST-SPACING','TEST-GEOMETRY']
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
