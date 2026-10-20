import gzip,hashlib,json
import pytest
from obsidiandroid.modeling.full_catalog_av import global_lineage, reviewed, _decode_chunk


def test_unlabeled_sample_bridges_labeled_components():
    rows=[{'sample_id':1,'package':'pkg.a'},
          {'sample_id':2,'package':'pkg.a','signer_sha1':'shared'},
          {'sample_id':3,'package':'pkg.b','signer_sha1':'shared'},
          {'sample_id':4,'package':'isolated'}]
    linked=global_lineage(rows)
    assert linked[1]==linked[2]==linked[3]
    assert linked[4]!=linked[1]


def test_identifier_types_do_not_collide_and_missing_is_not_a_group():
    rows=[{'sample_id':1,'package':'same'},{'sample_id':2,'vhash':'same'},
          {'sample_id':3,'package':''},{'sample_id':4}]
    assert len(set(global_lineage(rows).values()))==4
    with pytest.raises(ValueError,match='Duplicate'):
        global_lineage(rows+[rows[0]])


def test_unknown_or_disagreeing_authority_is_not_training_eligible():
    member={'review_status':'reviewed','authority_id':1,'recorded_family_id':2,
            'authority_version':'fixture','authority_basis':'fixture','package_group':'pkg',
            'governed_family_name':'family','effective_family_name':'family','recorded_family':'family'}
    assert reviewed(member)
    assert not reviewed({**member,'recorded_family':'unknown'})
    assert not reviewed({**member,'authority_id':True})
    assert not reviewed({**member,'effective_family_name':'different'})


def test_chunk_digest_and_path_are_enforced(tmp_path):
    blob=json.dumps({'members':[],'reports':[]}).encode();compressed=gzip.compress(blob)
    (tmp_path/'chunk.gz').write_bytes(compressed)
    entry={'path':'chunk.gz','sha256':hashlib.sha256(compressed).hexdigest(),'json_bytes':len(blob)}
    assert _decode_chunk(tmp_path,entry)=={'members':[],'reports':[]}
    with pytest.raises(ValueError,match='digest'):
        _decode_chunk(tmp_path,{**entry,'sha256':'0'*64})
    with pytest.raises(ValueError,match='escapes'):
        _decode_chunk(tmp_path,{**entry,'path':'../chunk.gz'})


def test_all_models_share_folds_and_train_only_vocabulary(tmp_path):
    import joblib
    import pandas as pd
    from obsidiandroid.modeling.expanded_av_experiment import plan_population
    from obsidiandroid.modeling.full_catalog_av import compare_models
    metadata=pd.DataFrame([{'sample_id':sid,'recorded_family':f'family{(sid-1)//25}',
                            'lineage_component':sid} for sid in range(1,76)])
    selected,folds,_=plan_population(metadata,[1])
    rows=pd.DataFrame([{'sample_id':sid,'engine_name':engine,'status':status,'report_id':f'event{sid}'}
                       for sid in range(1,76)
                       for engine,status in [(f'unique{sid}','malicious'),('common','malicious' if sid%2 else 'undetected')]])
    summary=compare_models(rows,selected,folds,tmp_path,'a'*64)
    assert set(summary)=={'logistic_regression','random_forest','xgboost'}
    ledger=json.loads((tmp_path/'FOLDS.json').read_text())
    for fold in ledger:
        for sid in fold['validation_ids']:
            assert f'avdet__unique{sid}' not in fold['features']
        model=joblib.load(tmp_path/f"fold_{fold['fold']}"/'logistic_regression.joblib')['model']
        assert model[1].n_samples_seen_==len(fold['train_ids'])
    for name in summary:
        predictions=pd.read_csv(tmp_path/f'{name}_OOF.csv')
        assert predictions.sample_id.is_unique
        assert set(predictions.sample_id)==set(selected.sample_id)
