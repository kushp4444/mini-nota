"""Private model tools, operating only on supplied live measurements and static assets."""
import pandas as pd
from .frozen_model import FrozenModel, ModelError
from .evaluation import evaluate_scores, join_outcomes


def run_model_tool(stage, rows, model_version, bundle_path, outcomes_path, expected_eligibility=None):
    model = FrozenModel(bundle_path)
    # Validate the exact same input before the approval decision and scoring.
    model.validate(rows,model_version)
    outcomes = pd.read_csv(outcomes_path).to_dict('records')
    eligible,excluded=join_outcomes([row['patient_id'] for row in rows],outcomes)
    report = {'scoring_eligible':[row['patient_id'] for row in rows],
              'evaluation_eligible':[r['patient_id'] for r in eligible],'evaluation_exclusions':excluded}
    if expected_eligibility is not None and any(expected_eligibility.get(key)!=value for key,value in report.items()):
        raise ModelError('Eligibility changed after disclosure')
    if stage == 'score':
        patients = model.score(rows,model_version)
        return {'stage':'score','schema_version':1,'status':'success','patients':patients,'errors':[], 'model':model.metadata(),
                'evaluation':evaluate_scores(patients,outcomes)}
    if stage != 'eligibility':
        raise ModelError('Unknown model tool')
    return {'stage':'eligibility','schema_version':1,'status':'success', 'model':model.metadata(),
        **report}
