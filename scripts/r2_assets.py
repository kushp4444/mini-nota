"""Review or resume the frozen manifest's R2 bootstrap without copying source scans."""
import argparse
import json
import os
from pathlib import Path
from service.asset_storage import TrustedAssets
from service.object_storage import client_from_env


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--expected-sha256',required=True)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--root',type=Path,help='Existing packaged immutable asset tree')
    source.add_argument('--prepared',type=Path,help='Prepared library tree; requires --bundle')
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--upload',action='store_true',help='Otherwise validate sources and print dry run; no credentials required')
    parser.add_argument('--plan-output',type=Path,help='Optional reviewable versioned object-key plan')
    args=parser.parse_args()
    assets=TrustedAssets(args.manifest,args.expected_sha256)
    root=args.root
    if args.prepared:
        if not args.bundle: parser.error('--prepared requires --bundle')
        root={'raw':args.prepared/'raw','model.json':args.bundle,'evaluation.json':Path(__file__).resolve().parents[1]/'docs/held-out-evaluation-v1.json',
              **{name:args.prepared/name for name in ('catalog.json','outcomes.csv','partition.json')}}
    if args.plan_output:
        args.plan_output.write_text(json.dumps({'manifest_sha256':assets.digest,'objects':[
            {**entry,'key':assets.key(name)} for name,entry in sorted(assets.files.items())]},indent=2)+'\n')
    client=client_from_env('upload') if args.upload else None
    bucket=os.environ['R2_UPLOAD_BUCKET'] if args.upload else None
    print(json.dumps(assets.upload(client,bucket,root,dry_run=not args.upload)))


if __name__=='__main__':
    main()
