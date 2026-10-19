"""Non-PI training must enforce requested isolation before any estimator fit."""
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from config import app_config
from obsidiandroid.modeling import model_trainer_factory as factory


def test_non_pi_group_split_cannot_fall_back(monkeypatch):
    x = pd.DataFrame({'signal': np.arange(40)}, index=np.arange(1, 41))
    y = pd.Series(np.arange(40) % 2, index=x.index)
    monkeypatch.setattr(app_config, 'ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT', True)
    monkeypatch.setattr(app_config, 'AUTO_ADJUST_TRAIN_TEST_SPLIT', False)
    monkeypatch.setattr(app_config, 'RUNTIME_ABLATION_ACTIVE', False, raising=False)
    monkeypatch.setattr(factory, '_runtime_training_state', lambda: {})
    monkeypatch.setattr(factory, '_runtime_sample_metadata', lambda: pd.DataFrame())
    monkeypatch.setattr(factory, '_temporal_holdout_requested', lambda: False)
    trainer = Mock(side_effect=AssertionError('must not reach fitting'))
    monkeypatch.setattr(factory, 'get_model_trainer', trainer)
    with pytest.raises(ValueError, match='Mandatory group evidence unavailable'):
        factory.train_model_factory(x, y, use_smote=False)
    trainer.assert_not_called()


def test_non_pi_labels_cannot_be_positionally_reassigned(monkeypatch):
    x = pd.DataFrame({'signal': [0, 1, 0, 1]}, index=[1, 2, 3, 4])
    y = pd.Series([0, 1, 0, 1], index=[4, 3, 2, 1])
    split = Mock(side_effect=AssertionError('must not partition mislabeled data'))
    monkeypatch.setattr(factory, 'resolve_training_partition', split)
    with pytest.raises(ValueError, match='Label sample IDs'):
        factory.train_model_factory(x, y, use_smote=False)
    split.assert_not_called()


def test_non_pi_temporal_split_cannot_fall_back(monkeypatch):
    x = pd.DataFrame({'signal': np.arange(40)}, index=np.arange(1, 41))
    y = pd.Series(np.arange(40) % 2, index=x.index)
    monkeypatch.setattr(app_config, 'ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT', False)
    monkeypatch.setattr(app_config, 'AUTO_ADJUST_TRAIN_TEST_SPLIT', False)
    monkeypatch.setattr(factory, '_runtime_training_state', lambda: {})
    monkeypatch.setattr(factory, '_runtime_sample_metadata', lambda: pd.DataFrame())
    monkeypatch.setattr(factory, '_temporal_holdout_requested', lambda: True)
    monkeypatch.setattr(factory, '_build_temporal_holdout_split', lambda *a, **k: None)
    trainer = Mock(side_effect=AssertionError('must not reach fitting'))
    monkeypatch.setattr(factory, 'get_model_trainer', trainer)
    with pytest.raises(ValueError, match='Mandatory temporal partition unavailable'):
        factory.train_model_factory(x, y, use_smote=False)
    trainer.assert_not_called()
