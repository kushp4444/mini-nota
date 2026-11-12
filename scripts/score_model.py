"""Score prepared held-out measurements without fitting or evaluating outcomes."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.frozen_model import FrozenModel


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--features',required=True,type=Path)
    parser.add_argument('--patient',action='append',help='Repeat for multiple held-out patients; defaults to all held-out')
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    model=FrozenModel(args.bundle)
    if hashlib.sha256(args.features.read_bytes()).hexdigest()!=model.bundle['provenance']['inputs']['features.csv']:
        raise ValueError('Prepared feature CSV provenance does not match the frozen bundle')
    features=pd.read_csv(args.features).set_index('patient_id',verify_integrity=True)
    if list(features.columns)!=model.bundle['feature_schema']:
        raise ValueError('Input CSV schema does not match frozen model')
    ids=args.patient or model.bundle['partition']['held_out']
    # This CLI is for the matching prepared CSV. Live tools require explicit feature_version.
    rows=[{'patient_id':pid,'feature_schema':model.bundle['feature_schema'],'feature_version':model.bundle['feature_version'],
           'values':features.loc[pid].to_dict()} for pid in ids]
    scored=model.score(rows,model.version)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'model':model.metadata(),'patients':scored},indent=2,allow_nan=False)+'\n')
    print(json.dumps({'model_version':model.version,'scored':len(scored),'output':str(args.output)}))

if __name__ == '__main__':main()
