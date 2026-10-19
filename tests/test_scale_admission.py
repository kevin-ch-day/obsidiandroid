import pandas as pd
import pytest
from obsidiandroid.modeling.scale_admission import preview_scale, ScaleDesign


def source(giant=False):
    rows=[]
    for sid in range(1,1102):
        family='large' if sid<=1040 else 'small'
        group=1 if giant and sid<=1037 else sid
        rows.append({'sample_id':sid,'sha256':f'{sid:064x}','recorded_family':family,
                     'lineage_component':group,'reviewed_label':True,'av_state':'VALIDATED_RETAINED_REPORT'})
    return pd.DataFrame(rows)


def test_over_1000_candidates_do_not_pass_infeasible_class_support():
    plan=preview_scale(source(giant=True),[1101])
    assert plan['candidate_samples']==1100
    assert plan['status']=='NO_GO' and plan['actual_fitted_samples']==0
    assert any('large' in b for b in plan['blockers'])


def test_feasible_preview_is_never_reported_as_fit():
    plan=preview_scale(source(),[1101])
    assert plan['status']=='PLAN_FEASIBLE_NOT_FITTED'
    assert plan['actual_fitted_samples']==0
    assert all(1101 not in f['train_ids']+f['validation_ids'] for f in plan['folds'])


def test_scale_floor_and_source_identity_cannot_silently_change():
    with pytest.raises(ValueError,match='floor'):
        preview_scale(source(),[1101],ScaleDesign(minimum_final_fit_samples=999))
    rows=source();rows.loc[0,'sha256']=rows.loc[1,'sha256']
    with pytest.raises(ValueError,match='duplicated'):
        preview_scale(rows,[1101])
