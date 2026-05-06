"""Tests for vendor engine selection fallback behavior."""

import pandas as pd
from config import app_config

from obsidiandroid.features.feature_engine_selection import get_top_engines_by_score


def test_get_top_engines_enforce_included_filter() -> None:
    """Selection should honor included_in_model when enforcement is enabled."""
    weights_df = pd.DataFrame(
        {
            "Vendor": ["a", "b", "c"],
            "Leakage Safe Score": [0.9, 0.8, 0.7],
            "included_in_model": [1, 0, 0],
        }
    )

    selected = get_top_engines_by_score(
        weights_df=weights_df,
        top_k=3,
        score_preference="Leakage Safe Score",
        enforce_included_in_model=True,
        verbose=False,
    )

    assert selected == ["a"]


def test_get_top_engines_can_disable_included_filter_for_backfill() -> None:
    """Fallback selection should be able to ignore included_in_model gate."""
    weights_df = pd.DataFrame(
        {
            "Vendor": ["a", "b", "c"],
            "Leakage Safe Score": [0.9, 0.8, 0.7],
            "included_in_model": [1, 0, 0],
        }
    )

    selected = get_top_engines_by_score(
        weights_df=weights_df,
        top_k=3,
        score_preference="Leakage Safe Score",
        enforce_included_in_model=False,
        verbose=False,
    )

    assert selected == ["a", "b", "c"]


def test_get_top_engines_can_enforce_trusted_vendor(monkeypatch) -> None:
    """Trusted-vendor filter should retain only trusted entries when enabled."""
    weights_df = pd.DataFrame(
        {
            "Vendor": ["a", "b", "c"],
            "Leakage Safe Score": [0.9, 0.8, 0.7],
            "included_in_model": [1, 1, 1],
            "trusted_vendor_flag": [1, 0, 1],
        }
    )
    monkeypatch.setattr(app_config, "FEATURE_ENFORCE_TRUSTED_VENDOR", True, raising=False)

    selected = get_top_engines_by_score(
        weights_df=weights_df,
        top_k=3,
        score_preference="Leakage Safe Score",
        enforce_included_in_model=True,
        verbose=False,
    )

    assert selected == ["a", "c"]
