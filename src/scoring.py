"""Private model tools, operating only on supplied live measurements and static assets."""
import numpy as np
import pandas as pd
from .frozen_model import FrozenModel, ModelError


def run_model_tool(stage, rows, model_version, bundle_path, outcomes_path):
    model = FrozenModel(bundle_path)
    # Validate the exact same input before the approval decision and scoring.
    model.validate(rows,model_version)
    if stage == 'score':
        return {'stage':'score','schema_version':1,'status':'success','patients':model.score(rows,model_version),'errors':[], 'model':model.metadata()}
    if stage != 'eligibility':
        raise ModelError('Unknown model tool')
    outcomes = pd.read_csv(outcomes_path)
    eligible, excluded = [], []
    for row in rows:
        pid = row['patient_id']
        matches = outcomes[outcomes.patient_id == pid]
        if matches.empty:
            excluded.append({'patient_id':pid,'code':'missing_outcome','message':'No recorded outcome; risk scoring remains available'})
        elif (len(matches) != 1 or not np.isfinite(matches[['duration','event']].to_numpy(dtype=float)).all()
              or matches.iloc[0].duration <= 0 or matches.iloc[0].event not in (0,1)):
            excluded.append({'patient_id':pid,'code':'invalid_outcome','message':'Outcome is duplicate or invalid; risk scoring remains available'})
        else:
            eligible.append(pid)
    return {'stage':'eligibility','schema_version':1,'status':'success', 'model':model.metadata(),
        'scoring_eligible':[row['patient_id'] for row in rows], 'evaluation_eligible':eligible,'evaluation_exclusions':excluded}
