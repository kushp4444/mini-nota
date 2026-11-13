"""Modal provider faults are explicit fixtures; imaging/model calls are real."""
import asyncio
from contextlib import contextmanager
import os
import pytest

from test_service import client
from service import app as runner
from service.run_repository import RunRepository


class LocalFixtureAssets:
    """Explicit small DICOM fixture source, never production source selection."""
    def __init__(self, root):
        self.root = root
        self.scan_requests = []

    @contextmanager
    def selected(self, client, bucket, patient_ids, *, scans=True, **kwargs):
        self.scan_requests.append(scans)
        # Match the production asset tree while keeping the fixture labeled.
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'raw').symlink_to(self.root, target_is_directory=True)
            for name in ('model.json','outcomes.csv'):
                (root/name).symlink_to(self.root/name)
            yield root


def setup_run_store(monkeypatch, tmp_path):
    RunRepository(os.environ['DATABASE_URL']).initialize()
    monkeypatch.setenv('RUN_DATABASE_URL', os.environ['DATABASE_URL'])
    monkeypatch.setenv('EXECUTION_BACKEND', 'deferred')
    monkeypatch.setenv('LOCAL_ARTIFACT_DIR', str(tmp_path/'objects'))


def test_phase_worker_completes_actual_imaging_without_dispatcher_task(client, monkeypatch, tmp_path):
    setup_run_store(monkeypatch, tmp_path)
    receipt = client.post('/runs', json={'patient_ids':['TEST-CLEAN']}).json()
    repo = runner.repository()
    operation = repo.operation(receipt['id'])
    from service.modal_worker import run_phase
    assets = LocalFixtureAssets(client.fixture_outcomes.parent)
    result = asyncio.run(run_phase(operation['id'], 'fc-explicit-fixture-1', assets=assets))
    assert result['status'] == 'completed'
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    saved = client.get('/runs/'+receipt['id'], headers=auth).json()
    assert saved['status'] == 'completed'
    assert saved['stage_results']['masks'][0]['values']['voxel_count'] == 27
    assert len(saved['stage_results']['features'][0]['feature_schema']) == 72
    assert len(saved['stage_results']['score']) == 1
    assert saved['events'][-1]['kind'] == 'done'
    # A provider crash retry retaining the same call ID cannot repeat work.
    assert asyncio.run(run_phase(operation['id'], 'fc-explicit-fixture-1', assets=assets))['status'] == 'skipped'
    assert assets.scan_requests == [True]


class ProviderFixture:
    """Explicit provider boundary fixture: queued calls, outage, lost response."""
    def __init__(self):
        self.calls = {}
        self.lose_response = False
        self.outage = False
        self.counter = 0
        self.blocked_call = None

    async def spawn(self, operation_id):
        self.counter += 1
        call = 'fc-provider-fixture-'+str(self.counter)
        self.calls[call] = {'operation_id':operation_id, 'status':'pending'}
        if self.lose_response:
            self.lose_response = False
            raise ConnectionError('Explicit accepted-but-lost-response fixture')
        return call

    async def poll(self, call_id):
        if self.outage:
            raise ConnectionError('Explicit provider outage fixture')
        return self.calls[call_id]['status']

    async def cancel(self, call_id):
        if self.outage or call_id == self.blocked_call:
            raise ConnectionError('Explicit provider outage fixture')
        self.calls[call_id]['status'] = 'stopped'
        return True

    async def complete(self, assets):
        from service.modal_worker import run_phase
        for call, record in list(self.calls.items()):
            if record['status'] == 'pending':
                await run_phase(record['operation_id'],call, assets=assets)
                record['status'] = 'finished'


def test_modal_gate_releases_compute_and_duplicate_approval_uses_scan_free_continuation(client, monkeypatch, tmp_path):
    setup_run_store(monkeypatch, tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND','modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner,'execution_provider',lambda:provider)
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN','TEST-PRIVACY']}).json()
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    path = '/runs/'+receipt['id']
    assets = LocalFixtureAssets(client.fixture_outcomes.parent)
    asyncio.run(provider.complete(assets))
    saved = client.get(path,headers=auth).json()
    assert saved['status'] == 'waiting_approval'
    assert len(provider.calls) == 1
    assert saved['stage_results']['score'] == []
    approval = {k:saved['checkpoint'][k] for k in ('disclosure_id','model_version')}
    # The Render API must not depend on any local imaging/eligibility server.
    monkeypatch.setenv('ENGINE_URL','http://127.0.0.1:1')
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _:client.post(path+'/approve',headers=auth,json=approval),range(3)))
    assert all(response.status_code == 200 for response in responses)
    assert len(provider.calls) == 2
    asyncio.run(provider.complete(assets))
    final = client.get(path,headers=auth).json()
    assert final['status'] == 'completed'
    assert len(final['stage_results']['score']) == 1
    assert assets.scan_requests == [True, False]
    assert len([e for e in final['events'] if e['payload'].get('action') == 'approve']) == 1


def test_provider_outage_keeps_canceling_then_queued_input_cannot_compute(client, monkeypatch, tmp_path):
    setup_run_store(monkeypatch,tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND','modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner,'execution_provider',lambda:provider)
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    path = '/runs/'+receipt['id']
    provider.outage = True
    assert client.post(path+'/cancel',headers=auth).status_code == 503
    assert client.get(path,headers=auth).json()['status'] == 'canceling'
    provider.outage = False
    runner.runs.clear()  # explicit dispatcher replacement, provider is external
    assert client.post(path+'/cancel',headers=auth).json()['status'] == 'canceled'
    assets = LocalFixtureAssets(client.fixture_outcomes.parent)
    from service.modal_worker import run_phase
    call_id, call = next(iter(provider.calls.items()))
    assert asyncio.run(run_phase(call['operation_id'],call_id,assets=assets))['status'] == 'skipped'
    assert assets.scan_requests == []
    assert client.get(path,headers=auth).json()['stage_results']['qc'] == []


def test_ambiguous_spawn_worker_self_registers_and_restart_preserves_saved_completion(client, monkeypatch, tmp_path):
    setup_run_store(monkeypatch,tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND','modal')
    provider = ProviderFixture()
    provider.lose_response = True
    monkeypatch.setattr(runner,'execution_provider',lambda:provider)
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    path = '/runs/'+receipt['id']
    assets = LocalFixtureAssets(client.fixture_outcomes.parent)
    asyncio.run(provider.complete(assets))
    # No returned submission ID reached Render; actual owner registered itself.
    runner.runs.clear()
    runner._repositories.clear()
    assert client.get(path,headers=auth).json()['status'] == 'completed'
    assert provider.counter == 1
    assert assets.scan_requests == [True]
    provider.outage = True  # saved results do not need provider output retention
    assert client.get(path+'/results',headers=auth).json()['status'] == 'completed'


def test_confirmed_provider_loss_is_explicit_interruption_never_lease_takeover(client, monkeypatch, tmp_path):
    setup_run_store(monkeypatch,tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND','modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner,'execution_provider',lambda:provider)
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    path = '/runs/'+receipt['id']
    call_id, call = next(iter(provider.calls.items()))
    repo = runner.repository()
    assert repo.claim(call['operation_id'],call_id) == 1
    provider.calls[call_id]['status'] = 'expired'
    saved = client.get(path,headers=auth).json()
    assert saved['status'] == 'failed'
    assert saved['events'][-1]['payload']['reason'] == 'Remote execution interrupted.'
    assert repo.claim(call['operation_id'],'fc-replacement-fixture') is None
    assert provider.counter == 1


def test_cancel_waits_for_every_phase_input_termination_ack(client, monkeypatch, tmp_path):
    setup_run_store(monkeypatch,tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND','modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner,'execution_provider',lambda:provider)
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN','TEST-PRIVACY']}).json()
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    path = '/runs/'+receipt['id']
    asyncio.run(provider.complete(LocalFixtureAssets(client.fixture_outcomes.parent)))
    gate = client.get(path,headers=auth).json()['checkpoint']
    assert client.post(path+'/approve',headers=auth,json={k:gate[k] for k in ('disclosure_id','model_version')}).status_code == 200
    provider.blocked_call = list(provider.calls)[-1]
    assert client.post(path+'/cancel',headers=auth).status_code == 503
    assert client.get(path,headers=auth).json()['status'] == 'canceling'
    provider.blocked_call = None
    assert client.post(path+'/cancel',headers=auth).json()['status'] == 'canceled'
    assert all(call['status'] == 'stopped' for call in provider.calls.values())


def test_native_cancel_stops_owned_tool_and_rejects_late_publication(client, monkeypatch, tmp_path):
    """Slow native boundary fixture; not a measured imaging performance test."""
    import json
    import time
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from test_backend_unit import alive, wait_for
    setup_run_store(monkeypatch,tmp_path)
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    path = '/runs/'+receipt['id']
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    marker = tmp_path/'native-started.json'
    # Test fixture spawns a descendant within the owned native process group.
    (tmp_path/'modal_slow_fixture.py').write_text('''import json,os,sys,time,subprocess\nfrom pathlib import Path\nr=json.load(sys.stdin)\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])\nPath(os.environ['MARKER']).write_text(json.dumps({'pid':os.getpid(),'child':p.pid,'workspace':r['workspace']}))\ntime.sleep(120)\n''')
    monkeypatch.setenv('PYTHONPATH',str(tmp_path))
    monkeypatch.setenv('ENGINE_WORKER_MODULE','modal_slow_fixture')
    monkeypatch.setenv('MARKER',str(marker))
    from service.modal_worker import run_phase
    repo = runner.repository()
    op = repo.operation(receipt['id'])
    assets = LocalFixtureAssets(client.fixture_outcomes.parent)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(lambda:asyncio.run(run_phase(op['id'],'fc-native-fixture',assets=assets)))
        wait_for(marker.exists)
        native = json.loads(marker.read_text())
        assert alive(native['pid']) and alive(native['child'])
        # Deferred adapter cannot invent provider ack; worker watches the durable
        # intent and stops native work even while the provider is unavailable.
        assert client.post(path+'/cancel',headers=auth).status_code == 503
        assert future.result(timeout=10)['status'] == 'stopped'
        wait_for(lambda:not alive(native['pid']) and not alive(native['child']))
    assert not __import__('pathlib').Path(native['workspace']).exists()
    assert client.get(path,headers=auth).json()['status'] == 'canceling'
    assert client.get(path,headers=auth).json()['stage_results']['qc'] == []


@pytest.fixture
def http_s3(monkeypatch):
    """Separate Moto HTTP process, preserving original app Pydantic/native deps."""
    import socket
    import subprocess
    import uuid
    import httpx
    import time
    import boto3
    import pytest
    executable = os.environ.get('MOTO_SERVER_PYTHON')
    if not executable:
        pytest.skip('Set MOTO_SERVER_PYTHON for explicit worker/S3 integration')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    endpoint = f'http://127.0.0.1:{port}'
    process = subprocess.Popen([executable,'-m','moto.server','-H','127.0.0.1','-p',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if httpx.get(endpoint,timeout=.2).status_code < 500:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(.05)
        client = boto3.client('s3',endpoint_url=endpoint,region_name='us-east-1',aws_access_key_id='fixture',aws_secret_access_key='fixture')
        bucket = 'worker-fixture-'+uuid.uuid4().hex
        client.create_bucket(Bucket=bucket)
        monkeypatch.delenv('LOCAL_ARTIFACT_DIR',raising=False)
        for name,value in {'ENDPOINT_URL':endpoint,'BUCKET':bucket,'ACCESS_KEY_ID':'fixture','SECRET_ACCESS_KEY':'fixture'}.items():
            monkeypatch.setenv('R2_RESULTS_'+name,value)
        yield client,bucket
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.parametrize('broken_bucket',[False,True])
def test_worker_s3_artifacts_are_saved_or_fail_explicitly_before_completion(client, monkeypatch, tmp_path, http_s3, broken_bucket):
    import hashlib
    setup_run_store(monkeypatch,tmp_path)
    monkeypatch.delenv('LOCAL_ARTIFACT_DIR',raising=False)
    if broken_bucket:
        monkeypatch.setenv('R2_RESULTS_BUCKET','explicit-nonexistent-bucket-fixture')
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    path = '/runs/'+receipt['id']
    auth = {'Authorization':f"Bearer {receipt['secret']}"}
    from service.modal_worker import run_phase
    op = runner.repository().operation(receipt['id'])
    asyncio.run(run_phase(op['id'],'fc-s3-fixture',assets=LocalFixtureAssets(client.fixture_outcomes.parent)))
    saved = client.get(path,headers=auth).json()
    assert saved['stage_results']['qc'][0]['status'] == 'success'
    if broken_bucket:
        assert saved['status'] == 'failed'
        assert saved['stage_results']['masks'] == []
        assert saved['events'][-1]['kind'] == 'done'
    else:
        assert saved['status'] == 'completed'
        assert 'object_ref' not in str(saved) and 'data_base64' not in str(saved)
        event = next(e for e in saved['events'] if e['payload'].get('patient',{}).get('artifacts'))
        artifact_path = path+f"/artifacts/{event['sequence']}/0"
        assert client.get(artifact_path).status_code == 403
        data = client.get(artifact_path,headers=auth).content
        assert data.startswith(b'\x89PNG')
        assert hashlib.sha256(data).hexdigest() == event['payload']['patient']['artifacts'][0]['sha256']
        runner.runs.clear()
        runner._repositories.clear()
        assert client.get(artifact_path,headers=auth).content == data


def test_unclaimed_expired_provider_input_fails_instead_of_waiting_forever(client, monkeypatch, tmp_path):
    setup_run_store(monkeypatch,tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND','modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner,'execution_provider',lambda:provider)
    receipt = client.post('/runs',json={'patient_ids':['TEST-CLEAN']}).json()
    next(iter(provider.calls.values()))['status'] = 'expired'
    saved = client.get('/runs/'+receipt['id'],headers={'Authorization':f"Bearer {receipt['secret']}"}).json()
    assert saved['status'] == 'failed'
    assert saved['events'][-1]['payload']['code'] == 'remote_execution_interrupted'
    assert provider.counter == 1


@pytest.mark.parametrize('claimed', [False, True])
def test_provider_interruption_retries_when_terminal_audit_write_fails(client, monkeypatch, tmp_path, claimed):
    import psycopg

    setup_run_store(monkeypatch, tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND', 'modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner, 'execution_provider', lambda: provider)
    receipt = client.post('/runs', json={'patient_ids': ['TEST-CLEAN']}).json()
    path = '/runs/' + receipt['id']
    auth = {'Authorization': f"Bearer {receipt['secret']}"}
    call_id, call = next(iter(provider.calls.items()))
    if claimed:
        assert runner.repository().claim(call['operation_id'], call_id) == 1
    provider.calls[call_id]['status'] = 'expired'
    database_url = os.environ['DATABASE_URL']
    with psycopg.connect(database_url) as conn:
        conn.execute("""
            ALTER TABLE run_events ADD CONSTRAINT fixture_reject_interruption
            CHECK (event->'payload'->>'code' <> 'remote_execution_interrupted') NOT VALID
        """)
    try:
        saved = client.get(path, headers=auth).json()
        assert saved['status'] == 'running'
        assert provider.calls[call_id]['status'] == 'stopped'
        assert all(event['kind'] != 'done' for event in saved['events'])
    finally:
        with psycopg.connect(database_url) as conn:
            conn.execute('ALTER TABLE run_events DROP CONSTRAINT fixture_reject_interruption')

    runner._repositories.clear()
    saved = client.get(path, headers=auth).json()
    assert saved['status'] == 'failed'
    done = [event for event in saved['events'] if event['kind'] == 'done']
    assert len(done) == 1
    assert done[0]['payload']['code'] == 'remote_execution_interrupted'
    assert provider.counter == 1


def test_worker_diagnostic_keeps_run_recoverable_until_terminal_audit_commits(client, monkeypatch, tmp_path):
    import psycopg
    from service.modal_worker import run_phase

    class UnavailableAssets:
        def selected(self, *args, **kwargs):
            raise OSError('Explicit source bootstrap failure')

    setup_run_store(monkeypatch, tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND', 'modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner, 'execution_provider', lambda: provider)
    receipt = client.post('/runs', json={'patient_ids': ['TEST-CLEAN']}).json()
    path = '/runs/' + receipt['id']
    auth = {'Authorization': f"Bearer {receipt['secret']}"}
    call_id, call = next(iter(provider.calls.items()))
    database_url = os.environ['DATABASE_URL']
    with psycopg.connect(database_url) as conn:
        conn.execute("""
            ALTER TABLE run_events ADD CONSTRAINT fixture_reject_worker_done
            CHECK (event->>'message' <> 'Run failed.') NOT VALID
        """)
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            asyncio.run(run_phase(call['operation_id'], call_id, assets=UnavailableAssets()))
        saved = client.get(path, headers=auth).json()
        assert saved['status'] == 'running'
        assert saved['events'][-1]['payload']['code'] == 'remote_execution_failed'
    finally:
        with psycopg.connect(database_url) as conn:
            conn.execute('ALTER TABLE run_events DROP CONSTRAINT fixture_reject_worker_done')

    call['status'] = 'finished'
    saved = client.get(path, headers=auth).json()
    assert saved['status'] == 'failed'
    assert saved['events'][-1]['kind'] == 'done'


@pytest.mark.parametrize('final_attempt', ['unknown', 'registered', 'claimed'])
def test_dispatch_exhaustion_only_fails_unclaimed_unconfirmed_work(client, monkeypatch, tmp_path, final_attempt):
    import psycopg
    from service.modal_worker import run_phase

    setup_run_store(monkeypatch, tmp_path)
    monkeypatch.setenv('EXECUTION_BACKEND', 'modal')
    provider = ProviderFixture()
    monkeypatch.setattr(runner, 'execution_provider', lambda: provider)
    provider.lose_response = True
    receipt = client.post('/runs', json={'patient_ids': ['TEST-CLEAN']}).json()
    path = '/runs/' + receipt['id']
    auth = {'Authorization': f"Bearer {receipt['secret']}"}

    def age_submissions():
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            conn.execute("""
                UPDATE operation_submissions SET created_at = now() - interval '31 seconds'
                WHERE operation_id = (SELECT id FROM execution_operations WHERE run_id = %s)
            """, (receipt['id'],))

    for attempt in range(2):
        age_submissions()
        provider.lose_response = attempt == 0 or final_attempt != 'registered'
        assert client.get(path, headers=auth).json()['status'] == 'running'
    assert provider.counter == 3
    assert client.get(path, headers=auth).json()['status'] == 'running'
    if final_attempt == 'claimed':
        call_id, call = list(provider.calls.items())[-1]
        assert runner.repository().claim(call['operation_id'], call_id) == 1

    age_submissions()
    saved = client.get(path, headers=auth).json()
    if final_attempt != 'unknown':
        assert saved['status'] == 'running'
        assert not any(event['kind'] == 'done' for event in saved['events'])
        assert provider.counter == 3
        return
    assert saved['status'] == 'failed'
    assert saved['events'][-1]['payload']['code'] == 'remote_dispatch_unconfirmed'
    assert len([event for event in saved['events'] if event['kind'] == 'done']) == 1
    assert client.get(path, headers=auth).json()['events'] == saved['events']

    assets = LocalFixtureAssets(client.fixture_outcomes.parent)
    for call_id, call in provider.calls.items():
        assert call['status'] == 'pending'  # No provider stop was asserted.
        assert asyncio.run(run_phase(call['operation_id'], call_id, assets=assets))['status'] == 'skipped'
    assert assets.scan_requests == []
    assert provider.counter == 3
