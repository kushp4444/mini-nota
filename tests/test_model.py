"""Frozen model public numerical boundary; explicitly synthetic survival data."""
import csv
import io
import json
import numpy as np
import pandas as pd
import pytest
from src.frozen_model import train_model, FrozenModel, ModelError


def fixture_library(tmp_path):
    rng = np.random.default_rng(91)
    ids = [f'FIXTURE-{i:03}' for i in range(70)]
    x = rng.normal(size=70)
    pd.DataFrame({'patient_id': ids, 'signal': x, 'noise': rng.normal(size=70), 'constant': 1}).to_csv(tmp_path/'features.csv', index=False)
    pd.DataFrame({'patient_id': ids, 'duration': np.exp(-x)*100+1, 'event': 1, 'time_unit':'days'}).to_csv(tmp_path/'outcomes.csv', index=False)
    (tmp_path/'feature_schema.json').write_text(json.dumps(['signal','noise','constant']))
    (tmp_path/'partition.json').write_text(json.dumps({'development':ids[:60], 'held_out':ids[60:]}))
    return ids


def test_training_freezes_development_pipeline_and_roundtrips_independent_scores(tmp_path):
    ids = fixture_library(tmp_path)
    bundle = train_model(tmp_path, tmp_path/'model.json', folds=3)
    model = FrozenModel(tmp_path/'model.json')
    rows = [{'patient_id':ids[60], 'feature_version':model.bundle['feature_version'], 'feature_schema':['signal','noise','constant'], 'values':{'signal':2.,'noise':0.,'constant':1.}},
            {'patient_id':ids[61], 'feature_version':model.bundle['feature_version'], 'feature_schema':['signal','noise','constant'], 'values':{'signal':-2.,'noise':0.,'constant':1.}}]
    scored = model.score(rows, model.version)
    assert scored[0]['values']['risk_score'] > scored[1]['values']['risk_score']
    assert model.score(rows[:1], model.version)[0] == scored[0]
    assert FrozenModel(tmp_path/'model.json').score(rows, model.version) == scored
    assert bundle['partition']['development'] == ids[:60]
    assert len(bundle['reference_scores']) == 60
    assert 'constant' not in bundle['pipeline']['features']
    # Held-out measurements/outcomes cannot change any fitted parameter or CV decision.
    development_inputs = {name: (tmp_path/name).read_bytes().splitlines(keepends=True)[:61]
                          for name in ("features.csv", "outcomes.csv")}
    development_frames = {name: pd.read_csv(tmp_path/name).iloc[:60]
                          for name in development_inputs}
    # Re-serializing the whole frame would round-trip development floats too.
    # Preserve every untouched CSV line verbatim and edit only held-out cells.
    held_out = set(ids[60:])
    for name, column, value in [('features.csv', 'signal', ''), ('outcomes.csv', 'duration', '-999')]:
        path = tmp_path/name
        lines = path.read_bytes().splitlines(keepends=True)
        column_index = next(csv.reader([lines[0].decode()])).index(column)
        for index, line in enumerate(lines[1:], 1):
            row = next(csv.reader([line.decode()]))
            if row[0] in held_out:
                row[column_index] = value
                encoded = io.StringIO(newline='')
                csv.writer(encoded, lineterminator='\n').writerow(row)
                lines[index] = encoded.getvalue().encode()
        path.write_bytes(b''.join(lines))
    assert pd.read_csv(tmp_path/'features.csv').loc[60:, 'signal'].isna().all()
    assert pd.read_csv(tmp_path/'outcomes.csv').loc[60:, 'duration'].eq(-999).all()
    for name, original in development_inputs.items():
        assert (tmp_path/name).read_bytes().splitlines(keepends=True)[:61] == original, f'{name}: development input bytes changed'
        pd.testing.assert_frame_equal(pd.read_csv(tmp_path/name).iloc[:60], development_frames[name], check_exact=True)
    changed = train_model(tmp_path, tmp_path/'second.json',folds=3)
    assert changed['pipeline'] == bundle['pipeline']
    assert changed['training'] == bundle['training']


def test_scoring_rejects_feature_and_model_incompatibility_and_development_ids(tmp_path):
    ids = fixture_library(tmp_path)
    train_model(tmp_path,tmp_path/'model.json',folds=3)
    model = FrozenModel(tmp_path/'model.json')
    row = {'patient_id':ids[60],'feature_version':model.bundle['feature_version'], 'feature_schema':['signal','noise','constant'],'values':{'signal':1.,'noise':0.,'constant':1.}}
    for bad in ({**row,'patient_id':ids[0]}, {**row,'feature_schema':['noise','signal','constant']},
                {**row,'values':{'signal':float('nan'),'noise':0.,'constant':1.}},
                {**row,'feature_version':'incompatible'}):
        with pytest.raises(ModelError): model.score([bad],model.version)
    with pytest.raises(ModelError): model.score([row],'other-model')
    bundle = json.loads((tmp_path/'model.json').read_text());bundle['reference_median']=999
    (tmp_path/'model.json').write_text(json.dumps(bundle))
    with pytest.raises(ModelError): FrozenModel(tmp_path/'model.json')


def test_wide_measurements_are_bitwise_independent_of_batch_size_and_order(tmp_path):
    ids=fixture_library(tmp_path)
    rng=np.random.default_rng(319)
    names=[f'feature_{i:02}' for i in range(72)]
    features=pd.DataFrame(rng.normal(size=(70,72)),columns=names);features.insert(0,'patient_id',ids)
    features.to_csv(tmp_path/'features.csv',index=False)
    (tmp_path/'feature_schema.json').write_text(json.dumps(names))
    train_model(tmp_path,tmp_path/'model.json',folds=3,penalties=(1.,))
    model=FrozenModel(tmp_path/'model.json')
    rows=[{'patient_id':pid,'feature_schema':names,'feature_version':model.bundle['feature_version'],
           'values':features.set_index('patient_id').loc[pid].to_dict()} for pid in ids[60:]]
    scores=model.score(rows,model.version)
    for row,score in zip(rows,scores): assert model.score([row],model.version)[0]==score
    assert model.score(list(reversed(rows)),model.version)==list(reversed(scores))


def test_bundle_refuses_features_prepared_with_changed_extraction_settings(tmp_path):
    fixture_library(tmp_path)
    from src.feature_contract import extraction_contract
    contract=extraction_contract()
    (tmp_path/'provenance.json').write_text(json.dumps({'radiomics_config_sha256':'changed', 'dependencies':contract['dependencies'],
      'engine_source_sha256':contract['source_sha256']}))
    with pytest.raises(ModelError,match='incompatible pipeline'):
        train_model(tmp_path,tmp_path/'model.json',folds=3)


def test_prepared_csv_scoring_cli_checks_its_frozen_input_provenance(tmp_path):
    import subprocess
    import sys
    fixture_library(tmp_path)
    train_model(tmp_path,tmp_path/'model.json',folds=3)
    command=[sys.executable,'-m','scripts.score_model','--bundle',str(tmp_path/'model.json'),
             '--features',str(tmp_path/'features.csv'),'--output',str(tmp_path/'scores.json')]
    assert subprocess.run(command,capture_output=True).returncode==0
    assert len(json.loads((tmp_path/'scores.json').read_text())['patients'])==10
    frame=pd.read_csv(tmp_path/'features.csv');frame.loc[60,'signal']=1000
    frame.to_csv(tmp_path/'features.csv',index=False)
    rejected=subprocess.run(command,capture_output=True,text=True)
    assert rejected.returncode!=0
    assert 'provenance' in rejected.stderr.lower()
