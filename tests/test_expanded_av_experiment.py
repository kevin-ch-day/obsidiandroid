import pandas as pd
import pytest
from obsidiandroid.modeling.expanded_av_experiment import plan_population, execute


def population():
    return pd.DataFrame([{'sample_id':i,'recorded_family':str(i//25),'lineage_component':i} for i in range(75)])


def test_prior_holdout_connected_group_is_excluded_from_every_fold():
    meta=population()
    meta.loc[meta.sample_id==1,'lineage_component']=0
    selected,folds,blocked=plan_population(meta,[0])
    assert blocked=={0}
    assert not {0,1}&set(selected.sample_id)
    observed=[]
    for train,valid in folds:
        assert not set(selected.iloc[train].lineage_component)&set(selected.iloc[valid].lineage_component)
        observed.extend(selected.iloc[valid].sample_id)
    assert len(observed)==len(set(observed))==len(selected)


def test_no_fallback_for_infeasible_groups():
    meta=population();meta['lineage_component']=meta.recorded_family.astype(int)
    with pytest.raises(ValueError,match='three eligible families'):
        plan_population(meta,[0])


def test_unknown_consumed_identity_rejected():
    with pytest.raises(ValueError,match='absent or incomplete'):
        plan_population(population(),[999])


def test_existing_output_rejected_before_source_access(tmp_path):
    with pytest.raises(ValueError,match='new external'):
        execute(tmp_path/'absent','a'*64,tmp_path/'old','b'*64,tmp_path,train=True)


def test_real_cv_fits_vocabulary_and_scaler_inside_each_fold(tmp_path):
    import hashlib,json,joblib
    members,reports=[],[]
    for sid in range(1,76):
        family=f'family{(sid-1)//25}';sha=hashlib.sha256(str(sid).encode()).hexdigest()
        members.append({'sample_id':sid,'sha256':sha,'package_group':f'pkg.{sid}',
                        'recorded_family':family,'recorded_family_id':(sid-1)//25+1,
                        'review_status':'reviewed','authority_id':sid,'authority_version':'fixture',
                        'authority_basis':'fixture','governed_family_name':family,'effective_family_name':family})
        payload=json.dumps({'data':{'id':sha,'attributes':{'sha256':sha,'last_analysis_results':{
            f'unique{sid}':{'category':'malicious'},'common':{'category':'malicious' if sid%2 else 'undetected'}}}}})
        reports.append({'sha256':sha,'http_status':200,'event_id':sid,'payload_json':payload,
                        'payload_hash':hashlib.sha256(payload.encode()).hexdigest()})
    source=tmp_path/'source.json';source.write_text(json.dumps({'format':'obsidiandroid-retained-av-development-v1','members':members,'reports':reports}))
    prior=tmp_path/'prior.json';prior.write_text(json.dumps({'test_ids':[1]}))
    output=tmp_path/'result'
    result=execute(source,hashlib.sha256(source.read_bytes()).hexdigest(),prior,hashlib.sha256(prior.read_bytes()).hexdigest(),output,train=True)
    assert result['status']=='DEVELOPMENT_CV_COMPLETE'
    for fold in result['folds']:
        saved=joblib.load(output/f"fold_{fold['fold']}"/'MODEL.joblib')
        assert saved['model'][1].n_samples_seen_==len(fold['train_ids'])
        for sid in fold['validation_ids']:
            assert f'avdet__unique{sid}' not in fold['features']
    assert len(pd.read_csv(output/'OOF_PREDICTIONS.csv'))==74
