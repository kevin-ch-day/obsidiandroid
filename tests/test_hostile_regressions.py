"""Regression tests for hostile-audit failure paths."""

import numpy as np
import pandas as pd
from zipfile import BadZipFile

from config import app_config
from obsidiandroid.modeling import training_helpers
from obsidiandroid.reporting import export_manager


def test_workbook_corruption_detector_catches_crc_error() -> None:
    """CRC workbook errors should be recognized as corruption."""
    assert export_manager._is_workbook_corruption_error(  # pylint: disable=protected-access
        BadZipFile("Bad CRC-32 for file 'docProps/core.xml'")
    )


def test_cv_rebalancing_rare_class_uses_safe_path(monkeypatch) -> None:
    """CV should not crash for rare-class splits when rebalancing is enabled."""
    monkeypatch.setattr(app_config, "CV_FOLDS", 5)
    monkeypatch.setattr(app_config, "CV_REPEATS", 1)
    monkeypatch.setattr(app_config, "ENABLE_CV_REBALANCING", True)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True)

    # Class 0 appears twice -> folds collapse to 2 and train-fold minimum can be 1.
    y = np.array([0, 0] + [1] * 10 + [2] * 10)
    X = pd.DataFrame(
        {
            "f1": np.linspace(0, 1, len(y)),
            "f2": np.linspace(1, 0, len(y)),
        }
    )

    scores = training_helpers.perform_cross_validation(
        X=X,
        y=y,
        model_type="random_forest",
        random_state=42,
    )
    assert scores is not None
    assert len(scores) >= 2
