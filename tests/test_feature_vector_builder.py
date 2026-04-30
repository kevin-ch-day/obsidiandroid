"""Tests for vendor feature vector builder helper behaviors."""

from __future__ import annotations

import pandas as pd

from ml_classification.vectorization import feature_vector_builder
from config import app_config


def test_filter_vendors_with_parsed_data_keeps_available_only() -> None:
    """Helper should keep only vendors present in parsed vendor payload."""
    parsed = {"lionic": {}, "tencent": {}, "drweb": {}}
    selected = ["lionic", "missing_vendor", "drweb"]
    filtered = feature_vector_builder._filter_vendors_with_parsed_data(  # pylint: disable=protected-access
        parsed_vendor_data=parsed,
        vendor_list=selected,
        verbose=False,
    )
    assert filtered == ["lionic", "drweb"]


def test_filter_vendors_with_parsed_data_handles_empty() -> None:
    """Helper should return empty list for empty/invalid parsed data."""
    filtered = feature_vector_builder._filter_vendors_with_parsed_data(  # pylint: disable=protected-access
        parsed_vendor_data={},
        vendor_list=["a", "b"],
        verbose=False,
    )
    assert filtered == []


def test_ensure_min_vendor_selection_no_fallback_in_paper_mode(monkeypatch) -> None:
    """Paper mode must not widen vendor set via fallback selection."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    result = feature_vector_builder._ensure_min_vendor_selection(  # pylint: disable=protected-access
        weights_df=None,
        selected_vendors=["a", "b"],
        min_required=4,
        top_k=8,
        score_preference="Leakage Safe Score",
        exclude_categories=[],
        verbose=False,
    )
    assert result == ["a", "b"]


def test_ensure_min_vendor_selection_requires_explicit_fallback(monkeypatch) -> None:
    """Non-paper runs should not widen vendor selection unless fallback is explicitly enabled."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", False, raising=False)
    result = feature_vector_builder._ensure_min_vendor_selection(  # pylint: disable=protected-access
        weights_df=pd.DataFrame({"Vendor": ["a", "b"], "Leakage Safe Score": [0.9, 0.8]}),
        selected_vendors=["a"],
        min_required=3,
        top_k=5,
        score_preference="Leakage Safe Score",
        exclude_categories=[],
        verbose=False,
    )
    assert result == ["a"]


def test_build_feature_vector_recovers_when_parser_gating_selects_zero(monkeypatch) -> None:
    """Builder should attempt fallback recovery when initial gated selection is empty."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", True, raising=False)
    monkeypatch.setattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_ADAPTIVE_TOP_K", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_OVERRIDE_USED", False, raising=False)

    monkeypatch.setattr(
        feature_vector_builder,
        "_select_top_vendors",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        feature_vector_builder,
        "_ensure_min_vendor_selection",
        lambda **kwargs: ["lionic"],
    )
    monkeypatch.setattr(
        feature_vector_builder,
        "_prepare_vendor_features",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "sample_id": [1, 2],
                "lionic__Parsed Family": ["a", "b"],
            }
        ),
    )
    monkeypatch.setattr(
        feature_vector_builder,
        "encode_features",
        lambda *args, **kwargs: pd.DataFrame({"feat": [1, 0]}, index=[1, 2]),
    )

    out = feature_vector_builder.build_feature_vector(
        weights_df=pd.DataFrame(
            {
                "Vendor": ["lionic"],
                "Leakage Safe Score": [0.1],
                "included_in_model": [0],
            }
        ),
        parsed_vendor_data={"lionic": {"dummy": "x"}},
        top_k=8,
        score_preference="Leakage Safe Score",
        verbose=False,
    )

    assert not out.empty
    assert bool(out.attrs.get("vendor_fallback_used", False)) is True
    assert str(out.attrs.get("vendor_selection_policy", "")) == "explicit_widening"
