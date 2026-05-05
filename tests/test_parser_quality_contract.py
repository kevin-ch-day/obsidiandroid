"""Tests for parser-quality diagnostics contract and coverage candidates export."""

from pathlib import Path

import pandas as pd

from obsidiandroid.evaluation import vendor_parser_utils
from obsidiandroid.pipeline import vendor_metadata_pipeline

_build_parser_quality_export_df = vendor_metadata_pipeline._build_parser_quality_export_df


def test_parser_quality_inclusion_status_has_no_unknown() -> None:
    """inclusion_status should always resolve to include/downweight/exclude."""
    scorecard_df = pd.DataFrame(
        {
            "Vendor": ["a", "b", "c"],
            "Samples Evaluated": [100, 100, 100],
            "Unknown Parsed (%)": [80.0, 10.0, 10.0],
            "Family Match Accuracy (%)": [90.0, 10.0, 90.0],
            "Generic Family Ratio": [0.1, 0.1, 0.9],
        }
    )

    out_df = _build_parser_quality_export_df(scorecard_df)
    assert not out_df.empty
    assert "inclusion_status" in out_df.columns
    assert set(out_df["inclusion_status"].unique()) <= {"include", "downweight", "exclude"}
    assert "unknown" not in set(out_df["inclusion_status"].unique())


def test_coverage_candidates_export_unmapped_high_coverage(monkeypatch, tmp_path: Path) -> None:
    """Unmapped high-coverage vendor candidates should be exported and prioritized."""
    out_path = tmp_path / "vendor_parser_coverage_candidates.latest.csv"
    monkeypatch.setattr(vendor_parser_utils, "PARSER_CANDIDATES_EXPORT", out_path)

    coverage_df = pd.DataFrame(
        {
            "vendor_column": ["v1", "v2", "v3"],
            "coverage_pct": [95.0, 82.0, 60.0],
            "parser_mapped": [0, 0, 1],
            "is_dynamic_generic": [0, 0, 1],
        }
    )

    vendor_parser_utils._export_unmapped_coverage_candidates(coverage_df, verbose=False)
    assert out_path.exists()
    out_df = pd.read_csv(out_path)
    assert list(out_df["vendor_column"]) == ["v1", "v2"]
    assert list(out_df["priority_rank"]) == [1, 2]
    assert (out_df["onboarding_priority"] == "high_coverage_unmapped").all()
