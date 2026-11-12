"""Create/verify an immutable held-out-only deployment file manifest. No visitor data."""
import argparse
import hashlib
import json
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def create(prepared, bundle, output, destination=None):
    expected = json.loads((REPOSITORY/'docs/model-v1-manifest.json').read_text())
    if digest(bundle) != expected['bundle_file_sha256'] or digest(prepared/'partition.json') != expected['partition_sha256']:
        raise ValueError('Release model/partition differs from the frozen model')
    partition = json.loads((prepared/'partition.json').read_text())
    sources = {'model.json':bundle,'outcomes.csv':prepared/'outcomes.csv','partition.json':prepared/'partition.json',
               'catalog.json':prepared/'catalog.json','evaluation.json':REPOSITORY/'docs/held-out-evaluation-v1.json'}
    for patient in partition['held_out']:
        patient_root = prepared/'raw'/patient
        if not patient_root.is_dir() or patient_root.is_symlink():
            raise ValueError('Missing or unsafe held-out patient directory')
        for path in patient_root.rglob('*'):
            if path.is_symlink():
                raise ValueError('Release assets must be real files, never symlinks')
            if path.is_file():
                sources[str(Path('raw')/path.relative_to(prepared/'raw'))] = path
    if destination is not None:
        import shutil
        destination.mkdir(parents=True, exist_ok=False)
        for name,path in sources.items():
            target=destination/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target)
    entries = [{'path':name,'size_bytes':path.stat().st_size,'sha256':digest(path)} for name,path in sorted(sources.items())]
    value = {'schema_version':1,'model_version':expected['model_version'],'held_out_ids':sorted(partition['held_out']),
             'partition_sha256':expected['partition_sha256'],'files':entries,
             'raw_file_count':sum(e['path'].startswith('raw/') for e in entries),
             'raw_bytes':sum(e['size_bytes'] for e in entries if e['path'].startswith('raw/'))}
    output.write_text(json.dumps(value,indent=2)+'\n')
    return {'manifest_sha256':digest(output),'held_out_count':len(partition['held_out']), 'raw_file_count':value['raw_file_count'],'raw_bytes':value['raw_bytes']}


def verify(root, manifest, expected_sha256):
    if len(expected_sha256)!=64 or digest(manifest)!=expected_sha256:
        raise ValueError('Immutable manifest digest mismatch')
    value=json.loads(manifest.read_text())
    expected=json.loads((REPOSITORY/'docs/model-v1-manifest.json').read_text())
    if value.get('schema_version')!=1 or value.get('model_version')!=expected['model_version'] or value.get('partition_sha256')!=expected['partition_sha256']:
        raise ValueError('Incompatible release manifest')
    paths=set()
    for entry in value['files']:
        relative=Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or entry['path'] in paths:
            raise ValueError('Unsafe or repeated immutable asset path')
        paths.add(entry['path'])
        path=root/relative
        if any((root/Path(*relative.parts[:i])).is_symlink() for i in range(1,len(relative.parts)+1)):
            raise ValueError('Symlink in immutable assets')
        if not path.is_file() or path.stat().st_size!=entry['size_bytes'] or digest(path)!=entry['sha256']:
            raise ValueError(f'Immutable asset integrity mismatch: {relative}')
    partition=json.loads((root/'partition.json').read_text())
    if digest(root/'model.json')!=expected['bundle_file_sha256'] or digest(root/'partition.json')!=expected['partition_sha256']:
        raise ValueError('Frozen release model/partition mismatch')
    if sorted(value['held_out_ids'])!=sorted(partition['held_out']) or sorted(p.name for p in (root/'raw').iterdir())!=sorted(partition['held_out']):
        raise ValueError('Release raw library must contain exactly held-out membership')
    actual={str(p.relative_to(root)) for p in (root/'raw').rglob('*') if p.is_file()}
    if actual!={p for p in paths if p.startswith('raw/')}:
        raise ValueError('Unmanifested raw file')
    return {'verified_files':len(paths),'held_out_count':len(partition['held_out'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    make=commands.add_parser('create');make.add_argument('--prepared',type=Path,required=True);make.add_argument('--bundle',type=Path,required=True);make.add_argument('--output',type=Path,required=True);make.add_argument('--destination',type=Path)
    check=commands.add_parser('verify');check.add_argument('--root',type=Path,required=True);check.add_argument('--manifest',type=Path,required=True);check.add_argument('--expected-sha256',required=True)
    args=parser.parse_args()
    result=create(args.prepared,args.bundle,args.output,args.destination) if args.command=='create' else verify(args.root,args.manifest,args.expected_sha256)
    print(json.dumps(result))


if __name__=='__main__':
    main()
