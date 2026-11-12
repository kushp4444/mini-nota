"""Fixed-reference interpretation and observed-outcome evaluation; never fits a model."""
import bisect
import math
import numpy as np
from lifelines import KaplanMeierFitter
from lifelines.utils import concordance_index

PERCENTILE_RULE = '100 × count(development reference scores ≤ patient score) / reference count; ties use upper empirical rank'
C_INDEX_METHOD = 'Harrell concordance (lifelines); higher log-risk predicts shorter survival; tied risks receive half credit; censored pairs follow lifelines admissibility rules'


def risk_context(score, reference, median):
    return {'risk_percentile':100.*bisect.bisect_right(sorted(reference),float(score))/len(reference),
            'risk_group':'higher model risk' if score > median else 'lower model risk'}


def join_outcomes(patient_ids, outcomes):
    eligible, excluded = [], []
    for pid in patient_ids:
        matches = [r for r in outcomes if r.get('patient_id')==pid]
        code = 'missing_outcome' if not matches else 'invalid_outcome'
        valid = len(matches)==1
        if valid:
            try:
                duration,event=float(matches[0]['duration']),float(matches[0]['event'])
                valid=math.isfinite(duration) and duration>0 and event in (0.,1.) and matches[0].get('time_unit','days')=='days'
            except (TypeError,ValueError,KeyError):
                valid=False
        if valid:
            eligible.append({'patient_id':pid,'duration':duration,'event':int(event)})
        else:
            excluded.append({'patient_id':pid,'code':code,'message':('No recorded outcome' if code=='missing_outcome' else 'Outcome is duplicate or invalid')+'; risk scoring remains available'})
    return eligible,excluded


def _concordance(rows):
    if len(rows)<2:
        return None,'At least two patients with usable outcomes are required.'
    try:
        return float(concordance_index([r['duration'] for r in rows],[-r['risk_score'] for r in rows],[r['event'] for r in rows])),None
    except ZeroDivisionError:
        return None,'No comparable outcome pairs (recorded events and follow-up do not permit concordance).'


def evaluate_scores(scores, outcomes, *, bootstrap_samples=0, seed=1729):
    joined,excluded=join_outcomes([p['patient_id'] for p in scores],outcomes)
    by_id={p['patient_id']:p['values'] for p in scores}
    rows=[{**r,**by_id[r['patient_id']]} for r in joined]
    cindex,reason=_concordance(rows)
    curves=[]
    for group in ('lower model risk','higher model risk'):
        subset=[r for r in rows if r['risk_group']==group]
        if subset:
            km=KaplanMeierFitter().fit([r['duration'] for r in subset],[r['event'] for r in subset])
            curves.append({'group':group,'count':len(subset),'events':sum(r['event'] for r in subset),
                'points':[{'time':float(t),'survival':float(s)} for t,s in km.survival_function_.iloc[:,0].items()]})
    uncertainty={'context':'Finite held-out cohort; concordance is uncertain and does not establish clinical validity. Selected-cohort estimates are exploratory.', 'interval':None}
    if bootstrap_samples:
        rng=np.random.default_rng(seed);estimates=[]
        if cindex is not None:
            for _ in range(bootstrap_samples):
                value,_=_concordance([rows[i] for i in rng.integers(0,len(rows),size=len(rows))])
                if value is not None:estimates.append(value)
        uncertainty.update({'method':'patient-level nonparametric percentile bootstrap, 95% interval; NumPy default_rng PCG64; unestimable resamples omitted and counted; linear quantiles',
            'seed':seed,'requested_samples':bootstrap_samples,'estimable_samples':len(estimates),'unestimable_samples':bootstrap_samples-len(estimates),
            'interval':np.quantile(estimates,[.025,.975],method='linear').tolist() if len(estimates)>=2 else None})
    return {'scope':'selected cohort — exploratory','c_index':cindex,'unavailable_reason':reason,'method':C_INDEX_METHOD,
        'selected_count':len(scores),'evaluated_count':len(rows),'evaluated_patients':[r['patient_id'] for r in rows],
        'event_count':sum(r['event'] for r in rows),'censored_count':sum(1-r['event'] for r in rows),'exclusions':excluded,
        'time_unit':'days','curves':curves,'curve_context':('No usable recorded outcomes; observed-survival curves unavailable.' if not curves else 'Only one model-risk group is populated; a two-group comparison is unavailable.' if len(curves)==1 else 'Observed survival by fixed development-median model-risk group; separation is not guaranteed.'),
        'uncertainty':uncertainty}
