"""Offline penalized Cox development and portable, fit-free JSON scoring.

The score is log partial hazard, centered on the fitted development cohort.
JSON contains numeric coefficients, never executable serialized Python objects.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.utils import concordance_index
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from .feature_contract import extraction_contract, feature_version


class ModelError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _fit(x, y, penalty):
    # Every learned transformation is derived solely from this training fold.
    names = list(x.columns[x.std(ddof=0) > 1e-12])
    if not names:
        raise ModelError('No variable training features')
    scaler = StandardScaler().fit(x[names])
    frame = pd.DataFrame(scaler.transform(x[names]), columns=names, index=x.index)
    frame['duration'], frame['event'] = y['duration'], y['event']
    model = CoxPHFitter(penalizer=penalty)
    model.fit(frame, 'duration', 'event')
    return {'features':names, 'mean':scaler.mean_.tolist(), 'scale':scaler.scale_.tolist(),
            'coefficients':model.params_.tolist(), 'center':model._norm_mean.tolist()}


def _predict(pipeline, frame):
    x = frame[pipeline['features']].to_numpy(dtype=float)
    standardized = (x - pipeline['mean']) / pipeline['scale']
    return np.sum(np.ascontiguousarray((standardized - pipeline['center']) * np.asarray(pipeline['coefficients'])), axis=1)


def train_model(prepared, destination, *, folds=5, penalties=(.01,.1,1.,10.), seed=1729):
    prepared = Path(prepared)
    partition = json.loads((prepared/'partition.json').read_text())
    dev, held = partition['development'], partition['held_out']
    if not dev or not held or len(set(dev+held)) != len(dev+held):
        raise ModelError('Partition must contain unique disjoint development and held-out patients')
    schema = json.loads((prepared/'feature_schema.json').read_text())
    extraction = extraction_contract()
    source_provenance = json.loads((prepared/'provenance.json').read_text()) if (prepared/'provenance.json').exists() else None
    if source_provenance:
        if source_provenance['radiomics_config_sha256'] != extraction['radiomics_config_sha256'] or source_provenance['dependencies'] != extraction['dependencies'] or any(source_provenance['engine_source_sha256'][name] != sha for name,sha in extraction['source_sha256'].items()):
            raise ModelError('Prepared features were extracted with an incompatible pipeline')
    features = pd.read_csv(prepared/'features.csv').set_index('patient_id',verify_integrity=True)
    outcomes = pd.read_csv(prepared/'outcomes.csv').set_index('patient_id',verify_integrity=True)
    if list(features.columns) != schema or len(schema) != len(set(schema)):
        raise ModelError('Prepared feature schema mismatch')
    # Select membership before checking values: held-out data never influences training.
    x, y = features.loc[dev, schema], outcomes.loc[dev, ['duration','event']]
    if not np.isfinite(x.to_numpy()).all() or not np.isfinite(y.to_numpy()).all() or (y.duration <= 0).any() or not y.event.isin([0,1]).all():
        raise ModelError('Invalid development measurements or outcomes')
    splits = list(StratifiedKFold(folds, shuffle=True, random_state=seed).split(x,y.event))
    trials = []
    for penalty in penalties:
        scores = []
        for train, validate in splits:
            pipeline = _fit(x.iloc[train], y.iloc[train], penalty)
            scores.append(float(concordance_index(y.iloc[validate].duration, -_predict(pipeline,x.iloc[validate]),y.iloc[validate].event)))
        trials.append({'penalizer':penalty,'fold_c_indices':scores,'mean_c_index':float(np.mean(scores))})
    chosen = max(trials,key=lambda trial:trial['mean_c_index'])['penalizer']
    pipeline = _fit(x,y,chosen)
    reference = sorted(_predict(pipeline,x).tolist())
    bundle = {'bundle_schema_version':1, 'feature_schema':schema, 'feature_version':feature_version(schema,extraction), 'extraction_contract':extraction,
        'partition':partition, 'pipeline':pipeline,'reference_scores':reference,
        'reference_median':float(np.median(reference)), 'score_definition':'log partial hazard relative to development center',
        'training':{'method':'penalized Cox proportional hazards; L2', 'folds':folds,'seed':seed,'candidates':trials,'chosen_penalizer':chosen,
                    'fold_membership':[{'training':[dev[i] for i in tr],'validation':[dev[i] for i in va]} for tr,va in splits]},
        'provenance':{'preparation':source_provenance, 'inputs':{name:hashlib.sha256((prepared/name).read_bytes()).hexdigest() for name in ('partition.json','feature_schema.json','features.csv','outcomes.csv')},
                      'libraries':{name:importlib.metadata.version(name) for name in ('lifelines','numpy','pandas','scikit-learn')}},
        'evaluation':{'status':'not_evaluated','reason':'Held-out performance evaluation belongs to the separate evaluation stage'}}
    bundle['model_version'] = 'cox-v1-' + digest(bundle)[:20]
    bundle['bundle_sha256'] = digest(bundle)
    destination = Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(bundle,sort_keys=True,indent=2,allow_nan=False)+'\n')
    return bundle


class FrozenModel:
    def __init__(self, path):
        self.bundle = json.loads(Path(path).read_text())
        content = {k:v for k,v in self.bundle.items() if k != 'bundle_sha256'}
        if self.bundle.get('bundle_schema_version') != 1 or digest(content) != self.bundle.get('bundle_sha256'):
            raise ModelError('Incompatible or corrupted model bundle')
        self.version = self.bundle['model_version']

    def metadata(self):
        b = self.bundle
        return {'model_version':self.version,'feature_version':b['feature_version'], 'feature_schema':b['feature_schema'],
            'development_count':len(b['partition']['development']), 'held_out_count':len(b['partition']['held_out']),
            'partition_sha256':b['provenance']['inputs']['partition.json'], 'reference_count':len(b['reference_scores']),
            'reference_median':b['reference_median'],'score_definition':b['score_definition'],'evaluation':b['evaluation']}

    def validate(self, rows, model_version):
        if model_version != self.version:
            raise ModelError('Model version mismatch')
        if not rows or len({r['patient_id'] for r in rows}) != len(rows):
            raise ModelError('Select distinct held-out feature rows')
        b = self.bundle
        for row in rows:
            if row['patient_id'] not in b['partition']['held_out']:
                raise ModelError('Scoring is restricted to frozen held-out membership')
            if row.get('feature_schema') != b['feature_schema'] or list(row['values']) != b['feature_schema'] or row.get('feature_version') != b['feature_version']:
                raise ModelError('Incompatible feature schema or version')
        frame = pd.DataFrame([r['values'] for r in rows])
        if not np.isfinite(frame.to_numpy(dtype=float)).all():
            raise ModelError('Feature measurements must be finite')
        return frame

    def score(self, rows, model_version):
        frame = self.validate(rows,model_version)
        b = self.bundle
        scores = _predict(b['pipeline'],frame)
        return [{'patient_id':row['patient_id'],'status':'success', 'values':{'risk_score':float(score),
            'model_version':self.version, 'feature_version':b['feature_version'], 'score_definition':b['score_definition']},
            'artifacts':[], 'errors':[]} for row,score in zip(rows,scores)]
