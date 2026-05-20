"""Tests for parser-quality diagnostics contract and coverage candidates export."""


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


def test_coverage_candidates_export_unmapped_high_coverage(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    """Unmapped high-coverage vendor candidates should be exported and prioritized."""
    output_root, diagnostics_dir, global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(vendor_parser_utils.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(vendor_parser_utils.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(vendor_parser_utils.app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    coverage_df = pd.DataFrame(
        {
            "vendor_column": ["v1", "v2", "v3"],
            "coverage_pct": [95.0, 82.0, 60.0],
            "parser_mapped": [0, 0, 1],
            "is_dynamic_generic": [0, 0, 1],
        }
    )

    vendor_parser_utils._export_unmapped_coverage_candidates(coverage_df, verbose=False)
    out_path = diagnostics_dir / "vendor_parser_coverage_candidates_rid.csv"
    assert out_path.exists()
    assert not (diagnostics_dir / "vendor_parser_coverage_candidates.latest.csv").exists()
    assert (global_diag / "vendor_parser_coverage_candidates.latest.csv").is_file()
    out_df = pd.read_csv(out_path)
    assert list(out_df["vendor_column"]) == ["v1", "v2"]
    assert list(out_df["priority_rank"]) == [1, 2]
    assert (out_df["onboarding_priority"] == "high_coverage_unmapped").all()


def test_parser_coverage_exports_run_scoped_named_files_without_local_latest_duplicates(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    _output_root, diagnostics_dir, global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(vendor_parser_utils.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(vendor_parser_utils.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(global_diag.parent), raising=False)
    monkeypatch.setattr(vendor_parser_utils.app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    coverage_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "vendor_a": ["fam.a", "fam.b"],
            "vendor_b": ["", ""],
        }
    )
    matched = {"vendor_a_parser": {"column_name": "vendor_a"}}

    vendor_parser_utils._export_parser_coverage_snapshot(coverage_df, matched, verbose=False)

    assert (diagnostics_dir / "vendor_parser_coverage_rid.csv").is_file()
    assert (diagnostics_dir / "vendor_parser_coverage_candidates_rid.csv").is_file()
    assert not (diagnostics_dir / "vendor_parser_coverage.latest.csv").exists()
    assert not (diagnostics_dir / "vendor_parser_coverage_candidates.latest.csv").exists()
    assert (global_diag / "vendor_parser_coverage.latest.csv").is_file()
    assert (global_diag / "vendor_parser_coverage_candidates.latest.csv").is_file()
