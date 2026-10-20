"""Offline P0-1 fixtures: real export adapter and generic fitting boundary."""
from dataclasses import replace
import hashlib
import copy
import json

import numpy as np
import pandas as pd
import pytest

from config import app_config
from obsidiandroid.modeling import experiment_split as es
from obsidiandroid.modeling import model_trainer_factory as factory
from obsidiandroid.modeling import pipeline_core
from obsidiandroid.orchestration import permission_v2_export as v2
from obsidiandroid.pipeline import stage_feature_enrichment as enrichment


TARGETS = ['family_id', 'type_slug', 'family_within_type']


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    runtime_before = {k: copy.deepcopy(v) for k, v in vars(app_config).items() if k.startswith('RUNTIME_')}
    for name, value in {
        'AUTO_ADJUST_TRAIN_TEST_SPLIT': False, 'ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT': False,
        'RUNTIME_ABLATION_ACTIVE': False, 'TRAIN_TEST_SPLIT': .25, 'RANDOM_STATE': 42,
        'RUNTIME_PROFILE_ID': 'synthetic', 'RUNTIME_RUN_ID': 'synthetic',
        'PERMISSION_MIN_SUPPORT': 1, 'ENABLE_CROSS_VALIDATION': False,
        'ENABLE_SMOTE_OVERSAMPLING': False, 'ENABLE_RF_GRID_SEARCH': False,
        'RUNTIME_DIAGNOSTICS_DIR': str(tmp_path/'diagnostics'),
        'ENABLE_FEATURE_CONTRACT_EXPORT': False, 'ENABLE_LEAKAGE_ASSESSMENT_EXPORT': False,
        'ENABLE_AGGRESSIVE_LEAKAGE_PRUNING': False,
    }.items():
        monkeypatch.setattr(app_config, name, value, raising=False)
    factory.reset_runtime_training_caches()
    samples = pd.DataFrame({'sample_id': list(range(1, 19)),
                            'sha256': [f'{i:064x}' for i in range(1, 19)],
                            'family_id': [1]*8 + [2]*8 + [-1, 3],
                            'family_canonical': ['Anubis']*8 + ['Cerberus']*8 + ['unknown', 'FluBot'],
                            'family_name': ['Anubis']*8 + ['Cerberus']*8 + ['unknown', 'FluBot'],
                            'type_slug': ['banker']*8 + ['rat']*8 + ['banker', 'rat']})
    export = {'format': v2.EXPORT_FORMAT, 'manifest_sha256': v2.FROZEN_MANIFEST_SHA256,
              'source_commit': 'c'*40, 'source_authority_digest': 'd'*64,
              'projection_policy_version': 'fixture-v2', 'interpretation_release': 'unresolved-v1',
              'feature_contract': v2.CONTRACT_VERSION, 'completeness': 'COMPLETE',
              'samples': [{'sample_id': i, 'sha256': f'{i:064x}',
                           'source_snapshot_digest': 'e'*64,
                           'evidence_state': 'PROVIDER_REPORTED_UNRESOLVED',
                           'members': [{'raw_token': 'common', 'projected_token': 'common'},
                                       {'raw_token': f'unique-{i}', 'projected_token': f'unique-{i}'}]}
                          for i in range(1, 19)]}
    data = json.dumps(export, sort_keys=True).encode(); path = tmp_path/'export.json'; path.write_bytes(data)
    anchor = {'format': v2.ANCHOR_FORMAT, 'approved_export_sha256': hashlib.sha256(data).hexdigest(),
              **{k: export[k] for k in v2._BOUND_FIELDS}}
    anchor_bytes = json.dumps(anchor, sort_keys=True).encode()
    monkeypatch.setattr(v2, 'FROZEN_SAMPLE_COUNT', 18)
    monkeypatch.setattr(v2, '_trusted_anchor_bytes', lambda: anchor_bytes)
    # Only this test fixture grants a synthetic fit. Production has no allow flag.
    def synthetic_authority(plan, export_path):
        actual_data, actual_anchor, _ = v2._checked_export(export_path)
        if (hashlib.sha256(actual_data).hexdigest(), hashlib.sha256(actual_anchor).hexdigest()) != (
                plan.source_digest, plan.approval_digest):
            raise es.ExperimentIntegrityError('synthetic authority changed')
    monkeypatch.setattr(es, 'assert_training_authorized', synthetic_authority)
    profile = {'profile_id': 'synthetic', 'training_label_field': 'family_id',
               'cohort_gates': {'min_samples_per_family': 2},
               'feature_flags': {'permission_feature_contract_version': v2.CONTRACT_VERSION,
                                 'permission_v2_export_path': str(path),
                                 'enable_permission_features': True,
                                 'enable_sample_metadata_features': False}}
    calls = []
    class Spy:
        def fit(self, x, y):
            calls.append((x.copy(), np.array(y).copy()))
            return self
    def trainer(**kwargs):
        return Spy().fit(kwargs['X_train'], kwargs['y_train']), {}
    monkeypatch.setattr(factory, 'get_model_trainer', lambda name: trainer)
    monkeypatch.setattr(factory, '_export_split_audit', lambda **kwargs: None)
    try:
        with es.experiment_scope():
            yield samples, profile, calls
    finally:
        monkeypatch.undo()
        for name in list(vars(app_config)):
            if name.startswith('RUNTIME_'):
                delattr(app_config, name)
        for name, value in runtime_before.items():
            setattr(app_config, name, value)


def prepare(fixture, target):
    samples, profile, calls = fixture
    profile['training_label_field'] = target
    binding = es.prepare_experiment(samples, profile, 'synthetic-experiment')
    frame = enrichment.build_permission_enrichment_frame(samples, profile['feature_flags'])
    frame['vendor_signal'] = np.arange(len(frame)) % 5
    features, labels = pipeline_core.align_data(frame, samples, forced_label_column=target)
    return binding, features, labels


@pytest.mark.parametrize('target', TARGETS)
def test_positive_target_plan_and_heldout_vocabulary(fixture, target):
    binding, x, y = prepare(fixture, target)
    result = factory.train_model_factory(x, y, use_smote=False)
    assert len(fixture[2]) == 1
    assert result['sample_ids_train'] == list(binding.plan.train_ids)
    assert result['experiment_split_receipt']['vocabulary_fit_ids'] == result['sample_ids_train']
    for sid in binding.plan.test_ids:
        assert 'perm_provider_unresolved__'+hashlib.sha256(f'unique-{sid}'.encode()).hexdigest() not in x
    assert es.ExperimentPlan.from_json(binding.plan.to_json(), binding.plan.sha256) == binding.plan
    if target != 'type_slug':
        assert {17, 18} <= set(binding.plan.excluded_ids)
    else:
        assert 17 not in binding.plan.excluded_ids


@pytest.mark.parametrize('target', TARGETS)
@pytest.mark.parametrize('mutation', ['missing', 'additional', 'sha', 'duplicate', 'stale',
                                    'misaligned', 'labels', 'missing_receipt', 'corrupt_receipt',
                                    'heldout_fit', 'plan', 'feature_rows', 'policy', 'selection'])
def test_rejects_before_estimator_fit(fixture, target, mutation):
    binding, x, y = prepare(fixture, target)
    if mutation == 'missing': x=x.drop(binding.plan.train_ids[0]); y=y.drop(binding.plan.train_ids[0])
    elif mutation == 'additional':
        x.loc[999]=x.iloc[0]; y.loc[999]=y.iloc[0]
    elif mutation == 'sha': binding.samples.loc[0, 'sha256']='f'*64
    elif mutation == 'duplicate': x=pd.concat([x,x.iloc[:1]]); y=pd.concat([y,y.iloc[:1]])
    elif mutation == 'stale':
        factory._runtime_training_state()['split_cache'][('experiment', binding.plan.sha256)] = {'train_index': [999]}
    elif mutation == 'misaligned': y=y.iloc[::-1]
    elif mutation == 'labels': y=y.copy(); y.iloc[0]='other'
    elif mutation == 'missing_receipt': binding.permission_frame=None
    elif mutation == 'corrupt_receipt': binding.permission_frame.attrs.pop('permission_v2_seal')
    elif mutation == 'heldout_fit':
        binding.permission_frame = v2.build_v2_unresolved_features(
            binding.samples,binding.export_path,training_sample_ids=binding.plan.test_ids,min_support=1)
    elif mutation == 'plan': binding.plan=replace(binding.plan, target='type_slug' if target != 'type_slug' else 'family_id')
    elif mutation == 'feature_rows':
        cols=[c for c in x if c.startswith('perm_provider_unresolved__')]
        x.loc[:,cols]=x[cols].iloc[::-1].to_numpy()
    elif mutation == 'policy': app_config.RANDOM_STATE=43
    elif mutation == 'selection':
        key=(('experiment',binding.plan.sha256),factory.hash_payload(list(x.columns)))
        factory._runtime_training_state()['feature_selection_cache'][key]={'fit_sample_id_hash':'bad'}
    with pytest.raises((ValueError, RuntimeError)):
        factory.train_model_factory(x,y,use_smote=False)
    assert fixture[2] == []


@pytest.mark.parametrize('target', TARGETS)
def test_partition_overlap_and_missing_provenance(fixture, target):
    binding, x, y=prepare(fixture,target)
    with pytest.raises(ValueError, match='overlaps'):
        replace(binding.plan, test_ids=binding.plan.train_ids)
    with pytest.raises(ValueError, match='provenance'):
        replace(binding.plan, source_digest='')
    with pytest.raises(ValueError, match='Serialized'):
        es.ExperimentPlan.from_json(binding.plan.to_json()+' ',binding.plan.sha256)
    with es.experiment_scope():
        with pytest.raises(ValueError,match='runner-owned'):
            factory.train_model_factory(x,y)
    assert fixture[2] == []


def test_incompatible_acceptance_split_rejected(fixture):
    fixture[1]['feature_flags']['permission_training_sample_ids']=[1,2]
    with pytest.raises(ValueError,match='acceptance split'):
        es.prepare_experiment(fixture[0],fixture[1],'synthetic')


def test_current_approval_does_not_authorize_training(fixture, monkeypatch):
    binding, _, _=prepare(fixture,'family_id')
    # Load the unpatched function, without a real anchor or real export.
    import runpy
    namespace=runpy.run_path(es.__file__)
    with pytest.raises(ValueError,match='feature acceptance'):
        namespace['assert_training_authorized'](binding.plan,binding.export_path)
    assert fixture[2] == []


@pytest.mark.parametrize('target',TARGETS)
def test_resampling_retains_physical_identity_and_rejects_reordering(fixture,target,monkeypatch):
    binding,x,y=prepare(fixture,target)
    def augment(a,b,seed):
        app_config.RUNTIME_SMOTE_AUDIT_LAST={'original_train_n':len(a),'post_resample_train_n':len(a)+1,'method':'ROS_rare_class_replication'}
        return pd.concat([a,a.iloc[:1]],ignore_index=True),np.append(b,b[0])
    monkeypatch.setattr(factory,'apply_smote',augment)
    result=factory.train_model_factory(x,y,use_smote=True)
    assert result['experiment_split_receipt']['additional_training_rows']==1
    assert result['sample_ids_train']==list(binding.plan.train_ids)
    fixture[2].clear()
    monkeypatch.setattr(factory,'apply_smote',lambda a,b,seed:(a.iloc[::-1],b))
    with pytest.raises(ValueError,match='Augmentation changed'):
        factory.train_model_factory(x,y,use_smote=True)
    assert fixture[2]==[]


@pytest.mark.parametrize('mode',['group','temporal'])
def test_mandatory_partition_never_downgrades(fixture,monkeypatch,mode):
    if mode=='group':
        monkeypatch.setattr(app_config,'ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT',True)
        monkeypatch.setattr(app_config,'AUTO_ADJUST_TRAIN_TEST_SPLIT',True)
    else:
        monkeypatch.setattr(app_config,'RUNTIME_PROFILE_ID','malicious_temporal_fixture')
    with pytest.raises(ValueError,match='Mandatory'):
        es.prepare_experiment(fixture[0],fixture[1],'synthetic')
    assert fixture[2]==[]


def test_exact_identity_and_policy_fail_at_planning(fixture):
    samples, profile, calls=fixture
    with pytest.raises(ValueError,match='duplicated'):
        es.prepare_experiment(pd.concat([samples,samples.iloc[:1]]),profile,'synthetic')
    changed=samples.copy(); changed.loc[0,'sha256']='f'*64
    with pytest.raises(ValueError,match='coverage'):
        es.prepare_experiment(changed,profile,'synthetic')
    assert calls==[]


@pytest.mark.parametrize('target',TARGETS)
def test_plan_deterministic_and_eligibility_changes_rejected(fixture,target):
    binding,x,y=prepare(fixture,target)
    replay=es.prepare_experiment(fixture[0],fixture[1],'synthetic-experiment')
    assert replay.plan.to_json()==binding.plan.to_json()
    changed=fixture[0].copy()
    changed.loc[0, 'type_slug' if target == 'type_slug' else 'family_canonical']='unknown'
    with pytest.raises(ValueError,match='eligibility'):
        replay.align(x.reset_index(),changed)
    assert fixture[2]==[]


@pytest.mark.parametrize('target',TARGETS)
def test_synthetic_estimator_fit(fixture,target,monkeypatch):
    from sklearn.tree import DecisionTreeClassifier
    binding,x,y=prepare(fixture,target)
    fitted=[]
    def trainer(**kwargs):
        model=DecisionTreeClassifier(max_depth=2,random_state=42)
        model.fit(kwargs['X_train'],kwargs['y_train'])
        fitted.append(model)
        return model,{}
    monkeypatch.setattr(factory,'get_model_trainer',lambda name:trainer)
    result=factory.train_model_factory(x,y,use_smote=False)
    assert len(fitted)==1
    assert result['experiment_split_receipt']['source_train_ids']==list(binding.plan.train_ids)


def test_missing_augmentation_receipt_blocks_cv_and_fit(fixture,monkeypatch):
    _,x,y=prepare(fixture,'family_id')
    monkeypatch.setattr(factory,'apply_smote',lambda a,b,seed:(a,b))
    cv=[]
    monkeypatch.setattr(factory,'perform_cross_validation',lambda *args:cv.append(True))
    with pytest.raises(ValueError,match='augmentation provenance'):
        factory.train_model_factory(x,y,use_smote=True,cross_validate=True)
    assert not cv and not fixture[2]


def test_stratification_does_not_fallback_for_singleton(fixture,monkeypatch):
    monkeypatch.setattr(app_config,'RUNTIME_SUPPORT_FLOOR_MODE','diagnostic_only',raising=False)
    with pytest.raises(ValueError,match='Mandatory stratification'):
        es.prepare_experiment(fixture[0],fixture[1],'synthetic')
    assert not fixture[2]
