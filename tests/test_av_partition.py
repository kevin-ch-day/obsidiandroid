from dataclasses import replace
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from config import app_config
from obsidiandroid.modeling.av_partition import AVPartition, frame_digest
from obsidiandroid.modeling import model_trainer_factory as factory


def inputs():
    x = pd.DataFrame(np.random.default_rng(1337).integers(0, 2, (100, 8)),
                     index=range(1, 101), columns=[f'avdet__engine_{i}' for i in range(8)])
    y = pd.Series(np.arange(100) % 2, index=x.index, name='family_id').astype(str)
    plan = AVPartition('a'*64, frame_digest(x), frame_digest(y), tuple(range(1, 76)),
                       tuple(range(76, 101)), tuple((i, i) for i in x.index))
    return x, y, plan


@pytest.mark.parametrize('mutation', ['features', 'labels', 'overlap', 'group', 'support', 'source'])
def test_fixed_av_plan_rejects_drift_before_fit(monkeypatch, mutation):
    x, y, plan = inputs()
    if mutation == 'features': x.iloc[0, 0] = 1-x.iloc[0, 0]
    elif mutation == 'labels': y.iloc[0] = 'other'
    elif mutation == 'overlap': plan = replace(plan, test_ids=(1, *plan.test_ids))
    elif mutation == 'group': plan = replace(plan, groups=tuple((i, 1) for i in x.index))
    elif mutation == 'support': plan = replace(plan, train_ids=tuple(range(1, 96)), test_ids=tuple(range(96, 101)))
    else: plan = replace(plan, source_sha256='unverified')
    trainer = Mock(side_effect=AssertionError('must not fit'))
    monkeypatch.setattr(factory, 'get_model_trainer', trainer)
    for key in ('ENABLE_CROSS_VALIDATION', 'ENABLE_LR_GRID_SEARCH', 'ENABLE_RF_GRID_SEARCH',
                'ENABLE_XGB_GRID_SEARCH', 'ENABLE_SVM_GRID_SEARCH'):
        monkeypatch.setattr(app_config, key, False, raising=False)
    with pytest.raises(ValueError):
        factory.train_model_factory(x, y, av_partition=plan, use_smote=False)
    trainer.assert_not_called()


def test_fixed_av_plan_reaches_actual_lr_with_exact_membership(monkeypatch):
    x, y, plan = inputs()
    for key in ('ENABLE_CROSS_VALIDATION', 'ENABLE_LR_GRID_SEARCH', 'ENABLE_RF_GRID_SEARCH',
                'ENABLE_XGB_GRID_SEARCH', 'ENABLE_SVM_GRID_SEARCH', 'ENABLE_PROBABILITY_CALIBRATION'):
        monkeypatch.setattr(app_config, key, False, raising=False)
    monkeypatch.setattr(app_config, 'RUNTIME_QUIET_TRAINING', True, raising=False)
    result = factory.train_model_factory(x, y, model_type='logistic_regression',
                                         av_partition=plan, use_smote=False)
    assert tuple(result['sample_ids_train']) == plan.train_ids
    assert tuple(result['sample_ids_test']) == plan.test_ids
    assert result['feature_selection_contract']['fit_sample_count'] == 75
    assert len(result['model'].predict(result['X_test'])) == 25
