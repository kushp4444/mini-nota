"""Durability through the application API using the real imaging fixture harness."""
import os
from test_service import client
from fastapi.testclient import TestClient
from service import app as runner


def test_saved_results_and_launch_receipt_survive_dispatcher_replacement(client, monkeypatch, tmp_path):
    from service.run_repository import RunRepository
    RunRepository(os.environ['DATABASE_URL']).initialize()
    monkeypatch.setenv('RUN_DATABASE_URL', os.environ['DATABASE_URL'])
    monkeypatch.setenv('LOCAL_ARTIFACT_DIR',str(tmp_path/'objects'))
    nonce = 'durable-fixture-launch-' + 'x' * 32
    context = client.get('/runs/launch-context').json()['worker_context']
    request = {'patient_ids':['TEST-CLEAN'], 'launch_nonce':nonce, 'worker_context':context}
    created = client.post('/runs', json=request).json()
    auth = {'Authorization':f"Bearer {created['secret']}"}
    path = '/runs/' + created['id']
    events = client.get(path+'/events', headers=auth)
    assert 'completed' in events.text
    runner.runs.clear()
    runner.launches.clear()
    monkeypatch.setattr(runner, 'WORKER_CONTEXT', 'replacement-dispatcher')
    replay = client.post('/runs', json=request)
    assert replay.status_code == 201
    assert replay.json() == {**created, 'status':'completed'}
    # A fresh OS process has no access to the original dispatcher's dictionaries.
    import socket
    import subprocess
    import sys
    import time
    import httpx
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable,'-m','uvicorn','service.app:app','--port',str(port)],env=os.environ.copy(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        base = f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                if httpx.get(base+'/runs/launch-context',timeout=.2).status_code == 200:
                    break
            except httpx.ConnectError:
                time.sleep(.05)
        remote = httpx.post(base+'/runs',json=request,timeout=10)
        assert remote.status_code == 201
        assert remote.json() == replay.json()
        assert httpx.get(base+path+'/results',headers=auth).json()['status'] == 'completed'
    finally:
        process.terminate()
        process.wait(timeout=10)
    saved = client.get(path+'/results', headers=auth)
    assert saved.json()['status'] == 'completed'
    assert saved.json()['scores'][0]['patient_id'] == 'TEST-CLEAN'
    assert client.get(path+'/results').status_code == 403
    assert client.get('/runs').status_code == 405


def test_gate_survives_replacement_and_duplicate_approval_scores_once(client, monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from service.run_repository import RunRepository
    RunRepository(os.environ['DATABASE_URL']).initialize()
    monkeypatch.setenv('RUN_DATABASE_URL',os.environ['DATABASE_URL'])
    monkeypatch.setenv('LOCAL_ARTIFACT_DIR',str(tmp_path/'objects'))
    created = client.post('/runs',json={'patient_ids':['TEST-CLEAN','TEST-PRIVACY']}).json()
    path = '/runs/'+created['id']
    auth = {'Authorization':f"Bearer {created['secret']}"}
    client.get(path+'/events',headers=auth)
    saved = client.get(path,headers=auth).json()
    assert saved['status'] == 'waiting_approval'
    runner.runs.clear()
    runner.launches.clear()
    restored = client.get(path,headers=auth).json()
    assert restored['checkpoint'] == saved['checkpoint']
    approval = {k:restored['checkpoint'][k] for k in ('disclosure_id','model_version')}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _:client.post(path+'/approve',json=approval,headers=auth),range(4)))
    assert all(r.status_code == 200 for r in responses)
    client.get(path+'/events',headers=auth)
    final = client.get(path,headers=auth).json()
    assert final['status'] == 'completed'
    assert len(final['stage_results']['score']) == 1
    assert len([e for e in final['events'] if e['payload'].get('action') == 'approve']) == 1
    page = client.get(path+'/event-page',headers=auth).json()
    assert all('data_base64' not in str(event) for event in page['events'])
    artifact_event = next(e for e in final['events'] if e['payload'].get('patient',{}).get('artifacts'))
    blob = client.get(path+f"/artifacts/{artifact_event['sequence']}/0",headers=auth)
    assert blob.status_code == 200
    assert blob.content.startswith(b'\x89PNG')


def test_concurrent_launch_receipts_and_cancel_intent_fence_late_worker(client, monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from service.run_repository import Conflict
    from service.run_repository import RunRepository
    RunRepository(os.environ['DATABASE_URL']).initialize()
    monkeypatch.setenv('RUN_DATABASE_URL',os.environ['DATABASE_URL'])
    monkeypatch.setenv('LOCAL_ARTIFACT_DIR',str(tmp_path/'objects'))
    nonce = 'durable-concurrent-'+'y'*40
    request = {'patient_ids':['TEST-MISSING'], 'launch_nonce':nonce}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _:client.post('/runs',json=request),range(4)))
    receipts = [response.json() for response in responses]
    assert all(r.status_code == 201 for r in responses)
    assert len({r['id'] for r in receipts}) == len({r['secret'] for r in receipts}) == 1
    receipt = receipts[0]
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    path = '/runs/'+receipt['id']
    client.get(path+'/events',headers=auth)
    # Exercise the trusted worker repository interface, observe only public API.
    repo = runner.repository()
    stale = repo.authorize(receipt['id'],receipt['secret'])
    operation = repo.operation(receipt['id'])
    assert repo.claim(operation['id'],'duplicate-worker') is None
    canceled = client.post(path+'/cancel',headers=auth)
    assert canceled.json()['status'] == 'canceled'
    stale['status'] = 'completed'
    import pytest
    with pytest.raises(Conflict):
        repo.publish(stale,operation={'id':operation['id'],'owner':'duplicate-worker','fence':999})
    assert client.get(path,headers=auth).json()['status'] == 'canceled'
    assert client.post(path+'/cancel',headers=auth).json()['status'] == 'canceled'


def test_ambiguous_submission_self_registration_and_queued_cancel(client, monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from service.run_repository import RunRepository
    RunRepository(os.environ['DATABASE_URL']).initialize()
    monkeypatch.setenv('RUN_DATABASE_URL',os.environ['DATABASE_URL'])
    monkeypatch.setenv('EXECUTION_BACKEND','deferred')
    monkeypatch.setenv('LOCAL_ARTIFACT_DIR',str(tmp_path/'objects'))
    created = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    auth = {'Authorization':f"Bearer {created['secret']}"}
    path = '/runs/'+created['id']
    repo = runner.repository()
    op = repo.operation(created['id'])
    repo.register_submission(op['id'],'attempt-1',ambiguous=True)
    assert repo.operation(created['id'])['submission_state'] == 'ambiguous'
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda n:repo.claim(op['id'],f'provider-call-{n}'),range(8)))
    assert len([f for f in claims if f is not None]) == 1
    owner_index = next(i for i,f in enumerate(claims) if f is not None)
    # A dispatcher learning the provider ID after worker self-registration does
    # not overwrite ownership, and replacement cannot steal a live invocation.
    repo.register_submission(op['id'],'attempt-1',f'provider-call-{owner_index}')
    replacement = RunRepository(os.environ['DATABASE_URL'])
    assert replacement.claim(op['id'],'replacement-dispatch') is None
    assert replacement.operation(created['id'])['owner'] == f'provider-call-{owner_index}'
    assert replacement.submissions(op['id']) == [{'submission_id':'attempt-1','provider_call_id':f'provider-call-{owner_index}','ambiguous':False}]
    assert 'secret' not in replacement.operation_context(op['id'])['run']
    assert client.get(path,headers=auth).json()['status'] == 'running'
    assert client.post(path+'/cancel',headers=auth).status_code == 503
    assert client.get(path,headers=auth).json()['status'] == 'canceling'
    assert replacement.claim(op['id'],'late-queued-call') is None
    assert replacement.reconcile_stopped(op['id'],f'provider-call-{owner_index}',claims[owner_index])
    assert client.post(path+'/cancel',headers=auth).json()['status'] == 'canceled'
    assert client.get(path+'/event-page',headers=auth).json()['status'] == 'canceled'


def test_unavailable_artifact_store_retains_prior_results_and_fails_explicitly(client, monkeypatch, tmp_path):
    import time
    from service.run_repository import RunRepository
    RunRepository(os.environ['DATABASE_URL']).initialize()
    monkeypatch.setenv('RUN_DATABASE_URL',os.environ['DATABASE_URL'])
    unavailable = tmp_path/'not-a-directory'
    unavailable.write_text('Explicit failed storage fixture')
    monkeypatch.setenv('LOCAL_ARTIFACT_DIR',str(unavailable))
    created = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    path = '/runs/'+created['id']
    auth = {'Authorization':f"Bearer {created['secret']}"}
    for _ in range(60):
        saved = client.get(path,headers=auth).json()
        if saved['status'] != 'running':
            break
        time.sleep(.1)
    assert saved['status'] == 'failed'
    assert saved['stage_results']['qc'][0]['status'] == 'success'
    assert saved['stage_results']['masks'] == []
    assert saved['events'][-1]['kind'] == 'done'


def test_catalog_reader_cannot_access_durable_controls_and_writer_needs_no_ddl(client, monkeypatch, tmp_path):
    import uuid
    import psycopg
    import pytest
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from service import catalog
    from service.run_repository import RunRepository
    isolated = os.environ['DATABASE_URL']
    RunRepository(isolated).initialize()
    import secrets
    role_password = secrets.token_urlsafe(32)
    writer, reader = 'test_writer_'+uuid.uuid4().hex, 'test_reader_'+uuid.uuid4().hex
    with psycopg.connect(isolated) as connection:
        schema = connection.execute('SELECT current_schema()').fetchone()[0]
        for role in (writer,reader):
            connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}').format(sql.Identifier(role),sql.Literal(role_password)))
            connection.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema),sql.Identifier(role)))
        connection.execute(sql.SQL('GRANT SELECT ON patient_catalog,model_metadata TO {}').format(sql.Identifier(reader)))
        connection.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON visitor_runs,run_events,execution_operations,operation_submissions TO {}').format(sql.Identifier(writer)))
    try:
        read_url, write_url = make_conninfo(isolated,user=reader,password=role_password), make_conninfo(isolated,user=writer,password=role_password)
        monkeypatch.setattr(catalog,'DATABASE_URL',read_url)
        monkeypatch.setenv('RUN_DATABASE_URL',write_url)
        monkeypatch.setenv('LOCAL_ARTIFACT_DIR',str(tmp_path/'objects'))
        created = client.post('/runs',json={'patient_ids':['TEST-PRIVACY']}).json()
        auth = {'Authorization':f"Bearer {created['secret']}"}
        path = '/runs/'+created['id']
        client.get(path+'/events',headers=auth)
        assert client.get(path,headers=auth).json()['status'] == 'failed'
        assert client.get(path+'/results').status_code == 403
        assert len(catalog.patients()) == 8
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            RunRepository(read_url).get(created['id'])
    finally:
        with psycopg.connect(isolated) as connection:
            for role in (writer,reader):
                connection.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
                connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_real_s3_artifacts_survive_replacement_with_private_capability_access(client, monkeypatch, tmp_path):
    """Actual S3 HTTP adapter with an explicitly labeled local Moto server."""
    import hashlib
    import socket
    import subprocess
    import sys
    import time
    import uuid
    import httpx
    import pytest
    import boto3
    from service.run_repository import RunRepository
    fixture_python = os.environ.get('MOTO_SERVER_PYTHON')
    if not fixture_python:
        pytest.skip('Set MOTO_SERVER_PYTHON to the isolated storage-fixture interpreter for mandatory integrated storage verification')
    def free_port():
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            return sock.getsockname()[1]
    def wait(url):
        for _ in range(100):
            try:
                if httpx.get(url,timeout=.2).status_code < 500:
                    return
            except httpx.ConnectError:
                pass
            time.sleep(.05)
        raise AssertionError('Local fixture server did not start')
    port = free_port()
    endpoint = f'http://127.0.0.1:{port}'
    moto = subprocess.Popen([fixture_python,'-m','moto.server','-H','127.0.0.1','-p',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    replacement = None
    try:
        wait(endpoint)
        bucket = 'fixture-results-'+uuid.uuid4().hex
        s3 = boto3.client('s3',endpoint_url=endpoint,region_name='us-east-1',aws_access_key_id='fixture',aws_secret_access_key='fixture')
        s3.create_bucket(Bucket=bucket)
        RunRepository(os.environ['DATABASE_URL']).initialize()
        monkeypatch.setenv('RUN_DATABASE_URL',os.environ['DATABASE_URL'])
        monkeypatch.delenv('LOCAL_ARTIFACT_DIR',raising=False)
        for key,value in {'ENDPOINT_URL':endpoint,'BUCKET':bucket,'ACCESS_KEY_ID':'fixture','SECRET_ACCESS_KEY':'fixture'}.items():
            monkeypatch.setenv('R2_RESULTS_'+key,value)
        created = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
        path = '/runs/'+created['id']
        auth = {'Authorization':f"Bearer {created['secret']}"}
        client.get(path+'/events',headers=auth)
        saved = client.get(path,headers=auth).json()
        assert saved['status'] == 'completed'
        assert 'object_ref' not in str(saved) and 'data_base64' not in str(saved)
        event = next(e for e in saved['events'] if e['payload'].get('patient',{}).get('artifacts'))
        artifact = event['payload']['patient']['artifacts'][0]
        artifact_path = path+f"/artifacts/{event['sequence']}/0"
        assert client.get(artifact_path).status_code == 403
        other = client.post('/runs',json={'patient_ids':['TEST-PRIVACY']}).json()
        assert client.get(artifact_path,headers={'Authorization':f"Bearer {other['secret']}"}).status_code == 403
        data = client.get(artifact_path,headers=auth).content
        assert data.startswith(b'\x89PNG')
        assert hashlib.sha256(data).hexdigest() == artifact['sha256']
        # The browser download contract retains actual bytes, not an expiring URL.
        retained = tmp_path/'retained-overlay.png'
        retained.write_bytes(data)
        api_port = free_port()
        replacement = subprocess.Popen([sys.executable,'-m','uvicorn','service.app:app','--port',str(api_port)],env=os.environ.copy(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{api_port}'
        wait(base+'/runs/launch-context')
        assert httpx.get(base+artifact_path,headers=auth).content == data
        assert httpx.get(base+artifact_path).status_code == 403
        replacement.terminate(); replacement.wait(timeout=10); replacement = None
        moto.terminate(); moto.wait(timeout=10)
        assert retained.read_bytes() == data
    finally:
        if replacement and replacement.poll() is None:
            replacement.terminate(); replacement.wait(timeout=10)
        if moto.poll() is None:
            moto.terminate(); moto.wait(timeout=10)


def test_valid_legacy_browser_gate_imports_into_durable_store(client, monkeypatch, tmp_path):
    import hashlib
    import hmac
    from service.run_repository import RunRepository
    # Simulate a gate saved before durable storage/signature-digest support.
    monkeypatch.delenv('RUN_DATABASE_URL',raising=False)
    created = client.post('/runs',json={'patient_ids':['TEST-MISSING']}).json()
    path = '/runs/'+created['id']
    auth = {'Authorization':f"Bearer {created['secret']}"}
    client.get(path+'/events',headers=auth)
    saved = client.get(path,headers=auth).json()['checkpoint']
    body = {k:v for k,v in saved.items() if k != 'signature'}
    saved['signature'] = hmac.new(os.environ['CHECKPOINT_SIGNING_KEY'].encode(),runner.checkpoint_bytes(body)+b'\0'+created['secret'].encode(),hashlib.sha256).hexdigest()
    runner.runs.clear()
    runner.launches.clear()
    RunRepository(os.environ['DATABASE_URL']).initialize()
    monkeypatch.setenv('RUN_DATABASE_URL',os.environ['DATABASE_URL'])
    monkeypatch.setenv('LOCAL_ARTIFACT_DIR',str(tmp_path/'objects'))
    imported = client.post('/runs/restore',json={'checkpoint':saved},headers=auth)
    assert imported.status_code == 200
    assert client.get(path,headers=auth).json()['checkpoint'] == saved
    assert runner.repository().active_owners(created['id']) == []
    approval = {key:saved[key] for key in ('disclosure_id','model_version')}
    assert client.post(path+'/approve',json=approval,headers=auth).status_code == 200
    client.get(path+'/events?after='+str(saved['last_sequence']),headers=auth)
    assert client.get(path+'/results',headers=auth).json()['status'] == 'completed'
