"""Tests for dynamic generic parser onboarding."""

import pandas as pd

from obsidiandroid.evaluation import vendor_parser_utils as vpu
from config import app_config


def test_dynamic_generic_onboarding_respects_coverage_threshold(monkeypatch) -> None:
    """Columns meeting minimum coverage should be onboarded."""
    monkeypatch.setattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", True, raising=False)
    av_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "KnownVendor": ["a", "b", None, ""],
            "SparseVendor": [None, None, None, "x"],
        }
    )
    existing = {
        "KnownVendor": {
            "type": "label",
            "func": lambda x, *_: x,
            "column_name": "KnownVendor",
        }
    }
    dynamic = vpu._build_dynamic_generic_parser_map(  # pylint: disable=protected-access
        av_df=av_df,
        existing_map=existing,
        verbose=False,
    )
    # With default min coverage 5%, SparseVendor is eligible (25%).
    assert "SparseVendor__generic" in dynamic
    assert dynamic["SparseVendor__generic"]["column_name"] == "SparseVendor"


def test_dynamic_generic_onboarding_excludes_non_vendor_columns() -> None:
    """Non-vendor bookkeeping fields should not be onboarded."""
    av_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_name": ["a", "b"],
            "family_id": [10, 11],
        }
    )
    dynamic = vpu._build_dynamic_generic_parser_map(  # pylint: disable=protected-access
        av_df=av_df,
        existing_map={},
        verbose=False,
    )
    assert dynamic == {}
