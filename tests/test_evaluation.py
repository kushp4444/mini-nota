"""Worked numerical examples through the public evaluation boundary."""
from src.evaluation import evaluate_scores, risk_context


def test_fixed_reference_ties_and_median_boundary():
    assert risk_context(2., [1.,2.,2.,3.], 2.) == {'risk_percentile':75., 'risk_group':'lower model risk'}
    assert risk_context(3., [1.,2.,2.,3.], 2.) == {'risk_percentile':100., 'risk_group':'higher model risk'}


def test_concordance_direction_and_observed_survival():
    scores = [{'patient_id':str(i),'values':{'risk_score':s,'risk_group':'higher model risk'}} for i,s in enumerate([3.,2.,1.])]
    result = evaluate_scores(scores,[{'patient_id':str(i),'duration':t,'event':1} for i,t in enumerate([1.,2.,3.])])
    assert result['c_index']==1.
    assert result['evaluated_count']==3
    assert result['curves'][0]['points']==[{'time':0.,'survival':1.},{'time':1.,'survival':2/3},{'time':2.,'survival':1/3},{'time':3.,'survival':0.}]
    assert 'one model-risk group' in result['curve_context']


def test_unavailable_pairs_and_named_exclusions_preserve_scores():
    scores=[{'patient_id':str(i),'values':{'risk_score':1.,'risk_group':'lower model risk'}} for i in range(3)]
    result=evaluate_scores(scores,[{'patient_id':'0','duration':10,'event':0},{'patient_id':'1','duration':20,'event':0}])
    assert result['c_index'] is None and 'No comparable' in result['unavailable_reason']
    assert result['evaluated_count']==2 and result['exclusions'][0]['patient_id']=='2'
    assert evaluate_scores(scores[:1],[{'patient_id':'0','duration':10,'event':1}])['c_index'] is None
    assert evaluate_scores(scores,[])['curves']==[]


def test_bootstrap_counts_unestimable_resamples_and_is_reproducible():
    scores=[{'patient_id':'early','values':{'risk_score':2.,'risk_group':'higher model risk'}},
            {'patient_id':'late','values':{'risk_score':1.,'risk_group':'lower model risk'}}]
    outcomes=[{'patient_id':'early','duration':1,'event':1},{'patient_id':'late','duration':2,'event':0}]
    result=evaluate_scores(scores,outcomes,bootstrap_samples=100,seed=1729)
    assert result['c_index']==1.
    interval=result['uncertainty']
    assert interval['interval']==[1.,1.]
    assert 0<interval['unestimable_samples']<100
    assert interval['unestimable_samples']+interval['estimable_samples']==100
    assert evaluate_scores(scores,outcomes,bootstrap_samples=100,seed=1729)==result


def test_outcomes_with_unknown_units_are_explicitly_excluded():
    scores=[{'patient_id':'fixture','values':{'risk_score':1.,'risk_group':'lower model risk'}}]
    result=evaluate_scores(scores,[{'patient_id':'fixture','duration':2,'event':1,'time_unit':'months'}])
    assert result['evaluated_count']==0
    assert result['exclusions'][0]['code']=='invalid_outcome'
