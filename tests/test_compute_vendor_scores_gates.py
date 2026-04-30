"""Tests for parser gate behavior in vendor score computation."""

from __future__ import annotations

import pandas as pd

from analysis.feature_engineering import compute_vendor_scores
from config import app_config


def _base_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Vendor": ["v1", "v2", "v3"],
            "Enrichment Score": [10.0, 9.0, 8.0],
            "Family Match Accuracy (%)": [12.0, 9.0, 6.0],
            "Detection Diversity": [30, 25, 20],
            "Unknown Parsed (%)": [5.0, 5.0, 5.0],
            "Unique Labels": [10, 10, 10],
            "Generic Family Ratio": [0.2, 0.2, 0.2],
            "Avg Genericity Score": [20.0, 20.0, 20.0],
            "Final ML Score": [0.2, 0.1, 0.05],
        }
    )


def test_apply_parser_quality_gates_relaxes_mapped_threshold_when_needed(monkeypatch) -> None:
    """Non-strict mode should relax mapped gate to preserve minimum vendor width."""
    monkeypatch.setattr(app_config, "PARSER_UNKNOWN_EXCLUDE_THRESHOLD", 0.70, raising=False)
    monkeypatch.setattr(app_config, "PARSER_MAPPED_MIN_THRESHOLD", 0.30, raising=False)
    monkeypatch.setattr(app_config, "PARSER_MIN_INCLUDED_VENDORS", 2, raising=False)
    monkeypatch.setattr(app_config, "PARSER_ALLOW_RELAXED_MAPPED_GATE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)

    out = compute_vendor_scores.apply_parser_quality_gates(_base_df())
    assert int(out["included_in_model"].sum()) >= 2
    assert "parser_mapped_cut_effective" in out.columns
    assert float(out["parser_mapped_cut_effective"].iloc[0]) < 0.30
    assert (
        out["parser_gate_status"].astype(str).str.contains("included_relaxed_mapped").any()
    )


def test_apply_parser_quality_gates_does_not_relax_in_strict_evidence_mode(monkeypatch) -> None:
    """Strict evidence mode should keep original mapped cutoff behavior."""
    monkeypatch.setattr(app_config, "PARSER_UNKNOWN_EXCLUDE_THRESHOLD", 0.70, raising=False)
    monkeypatch.setattr(app_config, "PARSER_MAPPED_MIN_THRESHOLD", 0.30, raising=False)
    monkeypatch.setattr(app_config, "PARSER_MIN_INCLUDED_VENDORS", 2, raising=False)
    monkeypatch.setattr(app_config, "PARSER_ALLOW_RELAXED_MAPPED_GATE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)

    out = compute_vendor_scores.apply_parser_quality_gates(_base_df())
    assert int(out["included_in_model"].sum()) == 0
    assert float(out["parser_mapped_cut_effective"].iloc[0]) == 0.30
