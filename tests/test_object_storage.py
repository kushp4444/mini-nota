"""Explicit S3-compatible HTTP fixtures, not Cloudflare R2 verification."""
import hashlib
import json
import os
import urllib.request
from pathlib import Path

import boto3
import pytest
if os.environ.get('REQUIRE_STORAGE_FIXTURE') == '1':
    from moto.server import ThreadedMotoServer
else:
    ThreadedMotoServer = pytest.importorskip('moto.server', reason='Explicit S3 fixture dependencies not installed; run dedicated storage suite').ThreadedMotoServer
from service.object_storage import ArtifactStore, StorageError


@pytest.fixture
def s3():
    server = ThreadedMotoServer(ip_address='127.0.0.1', port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    urllib.request.urlopen(urllib.request.Request(f'http://{host}:{port}/moto-api/reset',data=b'',method='POST')).close()
    client = boto3.client('s3', endpoint_url=f'http://{host}:{port}', region_name='us-east-1',
                          aws_access_key_id='fixture', aws_secret_access_key='fixture')
    client.create_bucket(Bucket='fixture-results')
    yield client
    server.stop()


def test_artifact_survives_store_replacement_and_repeated_publication(s3):
    store = ArtifactStore(s3, 'fixture-results')
    ref = store.publish('run-a', 'event-1-0', b'hello', 'text/csv')
    assert ref['sha256'] == '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    assert store.publish('run-a', 'event-1-0', b'hello', 'text/csv') == ref
    assert ArtifactStore(s3, 'fixture-results').read('run-a', ref) == b'hello'


def test_artifact_rejects_cross_run_changed_publication_and_corrupt_object(s3):
    store = ArtifactStore(s3, 'fixture-results', max_bytes=16)
    ref = store.publish('run-a','overlay',b'hello','image/png')
    with pytest.raises(StorageError):
        store.read('run-b',ref)
    with pytest.raises(StorageError):
        store.publish('run-a','overlay',b'other','image/png')
    assert store.read('run-a',ref) == b'hello'
    with pytest.raises(StorageError):
        store.publish('../run','overlay',b'x','image/png')
    with pytest.raises(StorageError):
        store.publish('run-a','large',b'x'*17,'image/png')
    s3.put_object(Bucket='fixture-results',Key=ref['key'],Body=b'bad!!')
    with pytest.raises(StorageError,match='checksum'):
        store.read('run-a',ref)


def manifest_fixture(tmp_path):
    """Tiny explicit storage fixture; no real DICOM/model measurement claim."""
    from service.asset_storage import TrustedAssets
    root = tmp_path/'source'; root.mkdir()
    contents = {'model.json':b'fixture model','partition.json':b'fixture partition',
                'catalog.json':b'{}','outcomes.csv':b'patient_id,time\n', 'evaluation.json':b'{}',
                'raw/LUNG1-002/ct/1.dcm':b'hello','raw/LUNG1-009/rtstruct.dcm':b'world'}
    files=[]
    for name,data in contents.items():
        path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        files.append({'path':name,'size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    contract={'model_version':'fixture-v1','partition_sha256':files[1]['sha256'],
              'bundle_file_sha256':files[0]['sha256'],'held_out_count':2}
    value={'schema_version':1,'model_version':'fixture-v1','partition_sha256':contract['partition_sha256'],
           'held_out_ids':['LUNG1-002','LUNG1-009'],'files':files}
    manifest=tmp_path/'manifest.json'; manifest.write_text(json.dumps(value))
    assets=TrustedAssets(manifest,hashlib.sha256(manifest.read_bytes()).hexdigest(),contract=contract)
    return assets,root,value,contract,manifest


def test_selected_manifest_download_cleans_private_workspace_and_resumes_upload(s3,tmp_path):
    assets,root,_,_,_=manifest_fixture(tmp_path)
    plan=assets.upload(s3,'fixture-results',root,dry_run=True)
    assert plan['file_count']==7 and plan['uploaded']==0
    first=assets.upload(s3,'fixture-results',root)
    assert first['uploaded']==7
    assert assets.upload(s3,'fixture-results',root)['skipped']==7
    with assets.selected(s3,'fixture-results',['LUNG1-002'],parent=tmp_path) as workspace:
        location=workspace
        assert (workspace/'raw/LUNG1-002/ct/1.dcm').read_bytes()==b'hello'
        assert not (workspace/'raw/LUNG1-009').exists()
        assert (workspace/'model.json').read_bytes()==b'fixture model'
        assert workspace.stat().st_mode & 0o077 == 0
    assert not location.exists()


@pytest.mark.parametrize('mutation', ['traversal','non-held-out','missing-static','duplicate','bad-size','wrong-model'])
def test_manifest_cannot_authorize_unsafe_or_incompatible_assets(tmp_path,mutation):
    from service.asset_storage import TrustedAssets
    _,_,value,contract,manifest=manifest_fixture(tmp_path)
    if mutation=='traversal': value['files'][-1]['path']='raw/LUNG1-009/../../escape'
    elif mutation=='non-held-out': value['files'][-1]['path']='raw/LUNG1-001/ct.dcm'
    elif mutation=='missing-static': value['files']=value['files'][1:]
    elif mutation=='duplicate': value['files'].append(value['files'][-1])
    elif mutation=='bad-size': value['files'][-1]['size_bytes']=-1
    elif mutation=='wrong-model': value['model_version']='other'
    manifest.write_text(json.dumps(value))
    with pytest.raises(StorageError):
        TrustedAssets(manifest,hashlib.sha256(manifest.read_bytes()).hexdigest(),contract=contract)


def test_remote_corruption_and_missing_bytes_abort_and_remove_workspace(s3,tmp_path):
    assets,root,_,_,_=manifest_fixture(tmp_path)
    assets.upload(s3,'fixture-results',root)
    key=assets.key('raw/LUNG1-002/ct/1.dcm')
    for data in (b'bad!!',b'short?'):
        s3.put_object(Bucket='fixture-results',Key=key,Body=data)
        with pytest.raises(StorageError):
            with assets.selected(s3,'fixture-results',['LUNG1-002'],parent=tmp_path):
                pytest.fail('Corrupt scans must not reach the engine')
        assert not list(tmp_path.glob('mini-nota-assets-*'))
    s3.delete_object(Bucket='fixture-results',Key=key)
    from botocore.exceptions import ClientError
    with pytest.raises(ClientError):
        with assets.selected(s3,'fixture-results',['LUNG1-002'],parent=tmp_path):
            pytest.fail('Missing scans must not reach the engine')
    assert not list(tmp_path.glob('mini-nota-assets-*'))
    for selection in ([],['LUNG1-001'],['../escape'],['LUNG1-002','LUNG1-002']):
        with pytest.raises(StorageError):
            with assets.selected(s3,'fixture-results',selection,parent=tmp_path):
                pytest.fail('Invalid cohort must be rejected')


def test_resume_never_trusts_remote_metadata_and_never_overwrites_corruption(s3,tmp_path):
    assets,root,_,_,_=manifest_fixture(tmp_path)
    assets.upload(s3,'fixture-results',root)
    key=assets.key('model.json')
    s3.put_object(Bucket='fixture-results',Key=key,Body=b'wrong content',Metadata={'sha256':assets.files['model.json']['sha256']})
    with pytest.raises(StorageError):
        assets.upload(s3,'fixture-results',root)
    assert (root/'model.json').read_bytes()==b'fixture model'


def test_manifest_pin_and_source_corruption_fail_before_upload(s3,tmp_path):
    from service.asset_storage import TrustedAssets
    assets,root,_,contract,manifest=manifest_fixture(tmp_path)
    with pytest.raises(StorageError,match='digest'):
        TrustedAssets(manifest,'0'*64,contract=contract)
    (root/'model.json').write_bytes(b'bad')
    with pytest.raises(StorageError,match='Source integrity'):
        assets.upload(s3,'fixture-results',root)
    assert s3.list_objects_v2(Bucket='fixture-results').get('KeyCount')==0


def test_incomplete_http_transfer_never_exposes_a_workspace(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from botocore.config import Config
    from botocore.exceptions import ResponseStreamingError
    assets,_,_,_,_=manifest_fixture(tmp_path)
    class TruncatedS3Fixture(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length','13')
            self.end_headers()
            self.wfile.write(b'bad')
            self.close_connection=True
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),TruncatedS3Fixture)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    client=boto3.client('s3',endpoint_url=f'http://127.0.0.1:{server.server_port}',region_name='us-east-1',
        aws_access_key_id='fixture',aws_secret_access_key='fixture',config=Config(read_timeout=1,retries={'max_attempts':0}))
    try:
        with pytest.raises(ResponseStreamingError):
            with assets.selected(client,'fixture-results',['LUNG1-002'],parent=tmp_path):
                pytest.fail('Incomplete transport must not reach imaging')
        assert not list(tmp_path.glob('mini-nota-assets-*'))
    finally:
        server.shutdown();server.server_close();thread.join()


def test_scoring_continuation_downloads_only_verified_static_assets(s3,tmp_path):
    assets,root,_,_,_=manifest_fixture(tmp_path)
    assets.upload(s3,'fixture-results',root)
    s3.delete_object(Bucket='fixture-results',Key=assets.key('raw/LUNG1-002/ct/1.dcm'))
    with assets.selected(s3,'fixture-results',['LUNG1-002'],parent=tmp_path,scans=False) as workspace:
        assert not (workspace/'raw').exists()
        assert (workspace/'model.json').read_bytes()==b'fixture model'
        assert (workspace/'outcomes.csv').is_file()
