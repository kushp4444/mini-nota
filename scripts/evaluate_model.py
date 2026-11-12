"""Evaluate the frozen full held-out partition once; never fits or selects a model."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.frozen_model import FrozenModel, digest
from src.evaluation import evaluate_scores


def evaluate_model(bundle, prepared, output, *, bootstrap_samples=2000):
    model=FrozenModel(bundle);prepared=Path(prepared)
    for name in ('features.csv','outcomes.csv','partition.json'):
        if hashlib.sha256((prepared/name).read_bytes()).hexdigest()!=model.bundle['provenance']['inputs'][name]:
            raise ValueError('Prepared evaluation provenance mismatch: '+name)
    features=pd.read_csv(prepared/'features.csv').set_index('patient_id',verify_integrity=True)
    if list(features.columns)!=model.bundle['feature_schema']:raise ValueError('Feature schema mismatch')
    ids=model.bundle['partition']['held_out']
    rows=[{'patient_id':pid,'feature_version':model.bundle['feature_version'],'feature_schema':model.bundle['feature_schema'],
           'values':features.loc[pid].to_dict()} for pid in ids]
    evaluation=evaluate_scores(model.score(rows,model.version),pd.read_csv(prepared/'outcomes.csv').to_dict('records'),bootstrap_samples=bootstrap_samples)
    evaluation.update({'scope':'full frozen held-out cohort','schema_version':1,'model_version':model.version,
        'bundle_sha256':model.bundle['bundle_sha256'],'partition_sha256':model.bundle['provenance']['inputs']['partition.json'],
        'outcomes_sha256':model.bundle['provenance']['inputs']['outcomes.csv'], 'features_sha256':model.bundle['provenance']['inputs']['features.csv'],
        'processing_exclusions':[], 'held_out_count':len(ids), 'reference_count':len(model.bundle['reference_scores']),
        'context':'Prepared imaging-eligible Lung1 cohort, partition reserved before development; frozen model and split were not tuned after evaluation.'})
    evaluation['evaluation_version']='held-out-v1-'+digest(evaluation)[:20]
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(evaluation,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if output.exists() and output.read_text()!=content:raise ValueError('Evaluation asset is immutable; use a new versioned path')
    output.write_text(content)
    return evaluation


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True);p.add_argument('--prepared',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();result=evaluate_model(a.bundle,a.prepared,a.output)
    print(json.dumps({k:result[k] for k in ('evaluation_version','model_version','evaluated_count','event_count','censored_count','c_index','uncertainty','exclusions')}))

if __name__=='__main__':main()
