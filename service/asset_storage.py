"""Trusted immutable source assets, streamed only into selected worker scratch.

The expected digest is operator configuration, never browser input. A trusted
manifest authorizes membership and paths; an S3 listing is never authority.
"""
import hashlib
import json
import re
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from .object_storage import StorageError, missing

STATIC = {'model.json','partition.json','catalog.json','outcomes.csv','evaluation.json'}


def file_digest(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(name):
    if not isinstance(name,str) or not name or '\\' in name or any(ord(c)<32 for c in name):
        raise StorageError('Unsafe manifest path')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path)!=name:
        raise StorageError('Unsafe manifest path')
    return path


def verify_remote(client,bucket,key,entry,target=None):
    """Bounded streaming, independent SHA256; no multipart ETag assumptions."""
    result=client.get_object(Bucket=bucket,Key=key)
    body=result['Body']; checksum=hashlib.sha256(); total=0
    try:
        if result['ContentLength']!=entry['size_bytes']:
            raise StorageError('Asset size mismatch')
        for chunk in iter(lambda:body.read(1024*1024),b''):
            total+=len(chunk)
            if total>entry['size_bytes']:
                raise StorageError('Asset exceeds manifest size')
            checksum.update(chunk)
            if target is not None:
                target.write(chunk)
        if total!=entry['size_bytes'] or checksum.hexdigest()!=entry['sha256']:
            raise StorageError('Asset checksum or incomplete content mismatch')
    finally:
        body.close()


class TrustedAssets:
    def __init__(self,manifest,expected_sha256,*,contract=None):
        manifest_bytes=Path(manifest).read_bytes()
        if not re.fullmatch('[a-f0-9]{64}',expected_sha256) or hashlib.sha256(manifest_bytes).hexdigest()!=expected_sha256:
            raise StorageError('Immutable manifest digest mismatch')
        self.digest=expected_sha256
        self.value=json.loads(manifest_bytes)
        expected=contract if contract is not None else json.loads((Path(__file__).resolve().parents[1]/'docs/model-v1-manifest.json').read_text())
        value=self.value
        if value.get('schema_version')!=1 or any(value.get(k)!=expected[k] for k in ('model_version','partition_sha256')):
            raise StorageError('Manifest differs from frozen model/partition')
        ids=value.get('held_out_ids',[])
        if len(ids)!=expected['held_out_count'] or len(set(ids))!=len(ids) or any(not re.fullmatch(r'LUNG1-\d{3}',v) for v in ids):
            raise StorageError('Invalid held-out membership')
        self.held_out_ids=frozenset(ids); self.files={}; raw_members=set()
        for entry in value.get('files',[]):
            name=entry['path']; path=safe_path(name)
            if name in self.files or type(entry.get('size_bytes')) is not int or entry['size_bytes']<0 or not re.fullmatch('[a-f0-9]{64}',entry.get('sha256','')):
                raise StorageError('Invalid or repeated asset entry')
            if name not in STATIC:
                if len(path.parts)<3 or path.parts[0]!='raw' or path.parts[1] not in self.held_out_ids:
                    raise StorageError('Asset outside held-out membership')
                raw_members.add(path.parts[1])
            self.files[name]=dict(entry)
        if not STATIC.issubset(self.files) or raw_members!=self.held_out_ids:
            raise StorageError('Missing static assets or held-out scan membership')
        if self.files['model.json']['sha256']!=expected['bundle_file_sha256'] or self.files['partition.json']['sha256']!=expected['partition_sha256']:
            raise StorageError('Frozen model/partition checksum mismatch')

    def key(self,name):
        if name not in self.files:
            raise StorageError('Unmanifested asset')
        return f'assets/{self.digest}/{name}'

    def _source(self,root,name):
        # Mapping supports the existing prepared tree + separate model without copying scans.
        if isinstance(root,dict):
            if name.startswith('raw/'):
                path=Path(root['raw'])/name.removeprefix('raw/')
                anchor=Path(root['raw'])
            else:
                path=Path(root[name]); anchor=path.parent
        else:
            anchor=Path(root); path=anchor/name
        if anchor.is_symlink() or any(p.is_symlink() for p in (path,*path.parents) if p!=p.parent):
            raise StorageError('Source symlink is not allowed')
        entry=self.files[name]
        if not path.is_file() or path.stat().st_size!=entry['size_bytes'] or file_digest(path)!=entry['sha256']:
            raise StorageError(f'Source integrity mismatch: {name}')
        return path

    def upload(self,client,bucket,root,*,dry_run=False):
        # Complete local validation happens before any remote mutation.
        paths={name:self._source(root,name) for name in self.files}
        report={'manifest_sha256':self.digest,'held_out_count':len(self.held_out_ids),'file_count':len(paths),
                'total_bytes':sum(e['size_bytes'] for e in self.files.values()),'uploaded':0,'skipped':0,'dry_run':dry_run}
        if dry_run:
            return report
        for name,path in paths.items():
            key=self.key(name); entry=self.files[name]
            try:
                client.head_object(Bucket=bucket,Key=key)
            except Exception as error:
                if not missing(error):
                    raise
                from botocore.exceptions import ClientError
                try:
                    with path.open('rb') as source:
                        client.put_object(Bucket=bucket,Key=key,Body=source,IfNoneMatch='*',
                            Metadata={'sha256':entry['sha256'],'manifest-sha256':self.digest},
                            ContentType='application/octet-stream')
                    report['uploaded']+=1
                except ClientError as conflict:
                    if conflict.response['Error']['Code'] not in ('PreconditionFailed','ConditionalRequestConflict','412','409'):
                        raise
                    report['skipped']+=1
            else:
                report['skipped']+=1
            verify_remote(client,bucket,key,entry)
        return report

    @contextmanager
    def selected(self,client,bucket,patient_ids,*,parent=None,scans=True):
        if not patient_ids or len(set(patient_ids))!=len(patient_ids) or any(p not in self.held_out_ids for p in patient_ids):
            raise StorageError('Selection must contain only unique held-out patient IDs')
        selected=set(patient_ids)
        names=[name for name in self.files if name in STATIC or (scans and PurePosixPath(name).parts[1] in selected)]
        with TemporaryDirectory(prefix='mini-nota-assets-',dir=parent) as temporary:
            root=Path(temporary)
            for name in names:
                target=root/name; target.parent.mkdir(parents=True,exist_ok=True)
                partial=target.with_name(target.name+'.part')
                with partial.open('xb') as output:
                    verify_remote(client,bucket,self.key(name),self.files[name],output)
                partial.replace(target)
            yield root
