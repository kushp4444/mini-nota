"""Model tools consume live feature records, with explicit outcome accounting."""
import json
import pandas as pd
from test_model import fixture_library
from src.frozen_model import train_model, FrozenModel
from src.scoring import run_model_tool


def test_missing_outcome_is_named_without_removing_scoreable_patient(tmp_path):
    ids = fixture_library(tmp_path)
    train_model(tmp_path,tmp_path/'model.json',folds=3)
    model = FrozenModel(tmp_path/'model.json')
    outcomes = pd.read_csv(tmp_path/'outcomes.csv');outcomes=outcomes[outcomes.patient_id!=ids[60]]
    outcomes.to_csv(tmp_path/'outcomes.csv',index=False)
    row = {'patient_id':ids[60], 'feature_version':model.bundle['feature_version'], 'feature_schema':['signal','noise','constant'], 'values':{'signal':1.,'noise':0.,'constant':1.}}
    report = run_model_tool('eligibility',[row],model.version,tmp_path/'model.json',tmp_path/'outcomes.csv')
    assert report['scoring_eligible']==[ids[60]]
    assert report['evaluation_eligible']==[]
    assert report['evaluation_exclusions']==[{'patient_id':ids[60],'code':'missing_outcome','message':'No recorded outcome; risk scoring remains available'}]
    scored = run_model_tool('score',[row],model.version,tmp_path/'model.json',tmp_path/'outcomes.csv')
    assert scored['patients'][0]['patient_id']==ids[60]
    assert scored['patients'][0]['status']=='success'


def test_score_rejects_changed_outcome_disclosure_before_computing_scores(tmp_path):
    import pytest
    from src.frozen_model import ModelError
    ids=fixture_library(tmp_path)
    train_model(tmp_path,tmp_path/'model.json',folds=3)
    model=FrozenModel(tmp_path/'model.json')
    row={'patient_id':ids[60],'feature_version':model.bundle['feature_version'],'feature_schema':['signal','noise','constant'],'values':{'signal':1.,'noise':0.,'constant':1.}}
    report=run_model_tool('eligibility',[row],model.version,tmp_path/'model.json',tmp_path/'outcomes.csv')
    outcomes=pd.read_csv(tmp_path/'outcomes.csv')
    outcomes[outcomes.patient_id!=ids[60]].to_csv(tmp_path/'outcomes.csv',index=False)
    with pytest.raises(ModelError,match='Eligibility changed'):
        run_model_tool('score',[row],model.version,tmp_path/'model.json',tmp_path/'outcomes.csv',expected_eligibility=report)
