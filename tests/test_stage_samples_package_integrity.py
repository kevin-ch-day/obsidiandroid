"""Tests for package-name integrity gate behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.pipeline import stage_samples


def test_package_integrity_respects_profile_threshold_in_strict_mode(monkeypatch) -> None:
    """Strict mode should honor profile threshold when missing package is allowed."""
    monkeypatch.setattr(stage_samples.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EVIDENCE_HARD_FAIL_MISSING_PACKAGE", True, raising=False)
    df = pd.DataFrame(
        {
            "android_package_name": ["pkg.a", "", "pkg.b", ""],
        }
    )
    # Missing rate = 50%; threshold=60 -> should pass.
    stage_samples._assert_package_name_integrity(  # pylint: disable=protected-access
        samples_df=df,
        gates={"allow_missing_package_name": True, "max_missing_package_pct": 60.0},
    )


def test_package_integrity_hard_fails_when_missing_not_allowed_in_strict_mode(monkeypatch) -> None:
    """Strict mode should enforce 0% when missing package names are disallowed."""
    monkeypatch.setattr(stage_samples.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EVIDENCE_HARD_FAIL_MISSING_PACKAGE", True, raising=False)
    df = pd.DataFrame(
        {
            "android_package_name": ["pkg.a", ""],
        }
    )
    with pytest.raises(ValueError, match="Missing package rate"):
        stage_samples._assert_package_name_integrity(  # pylint: disable=protected-access
            samples_df=df,
            gates={"allow_missing_package_name": False, "max_missing_package_pct": 100.0},
        )
