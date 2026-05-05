"""Tests for vendor metadata pipeline diagnostics export helpers."""

import pandas as pd

from obsidiandroid.pipeline import vendor_metadata_pipeline


def test_build_parser_quality_export_df_adds_stable_columns() -> None:
    """Parser quality export should include governance-stable snake_case fields."""
    scorecard_df = pd.DataFrame(
        {
            "Vendor": ["Tencent", "Lionic"],
            "Samples Evaluated": [100, 100],
            "Unknown Parsed (%)": [20.0, 10.0],
            "Generic Family Ratio": [0.25, 0.12],
            "Family Match Accuracy (%)": [40.0, 50.0],
            "parser_gate_status": ["include", "downweight"],
            "included_in_model": [1, 1],
            "Trusted": [1, 0],
            "Active": [1, 1],
        }
    )

    export_df = vendor_metadata_pipeline._build_parser_quality_export_df(scorecard_df)  # pylint: disable=protected-access
    assert not export_df.empty
    for col in [
        "vendor_id",
        "total_rows",
        "mapped_ratio",
        "unknown_ratio",
        "generic_ratio",
        "inclusion_status",
        "trusted_vendor_flag",
        "active_vendor_flag",
    ]:
        assert col in export_df.columns
    assert export_df.loc[0, "vendor_id"] == "tencent"
    assert export_df.loc[0, "total_rows"] == 100
    assert export_df.loc[0, "mapped_ratio"] == 0.4
    assert export_df.loc[0, "unknown_ratio"] == 0.2
    assert export_df.loc[1, "inclusion_status"] == "downweight"
    assert export_df.loc[0, "trusted_vendor_flag"] == 1
    assert export_df.loc[1, "trusted_vendor_flag"] == 0


def test_parser_quality_auxiliary_diagnostics_export(monkeypatch, tmp_path) -> None:
    """Stress-test and strengths diagnostics should be exported from parser quality frame."""
    scorecard_df = pd.DataFrame(
        {
            "Vendor": ["vendor_a", "vendor_b", "vendor_c"],
            "Samples Evaluated": [100, 100, 100],
            "Unknown Parsed (%)": [10.0, 75.0, 20.0],
            "Generic Family Ratio": [0.10, 0.20, 0.80],
            "Family Match Accuracy (%)": [70.0, 20.0, 65.0],
            "Trusted": [1, 0, 1],
            "Active": [1, 1, 1],
        }
    )
    monkeypatch.chdir(tmp_path)

    export_df = vendor_metadata_pipeline._build_parser_quality_export_df(scorecard_df)  # pylint: disable=protected-access
    vendor_metadata_pipeline._export_parser_stress_test(export_df)  # pylint: disable=protected-access
    vendor_metadata_pipeline._export_parser_strengths_weaknesses(export_df)  # pylint: disable=protected-access

    stress_path = tmp_path / "output" / "diagnostics" / "vendor_parser_stress_test.latest.csv"
    strength_path = tmp_path / "output" / "diagnostics" / "vendor_parser_strengths_weaknesses.latest.csv"
    assert stress_path.exists()
    assert strength_path.exists()


def test_build_parser_quality_export_df_uses_include_flag_for_status() -> None:
    """Rows excluded from model should be marked with exclusion status."""
    scorecard_df = pd.DataFrame(
        {
            "Vendor": ["ExampleVendor"],
            "Samples Evaluated": [50],
            "Unknown Parsed (%)": [90.0],
            "Generic Family Ratio": [0.8],
            "Family Match Accuracy (%)": [5.0],
            "included_in_model": [0],
        }
    )
    export_df = vendor_metadata_pipeline._build_parser_quality_export_df(scorecard_df)  # pylint: disable=protected-access
    assert export_df.loc[0, "inclusion_status"] == "exclude"


def test_build_parser_quality_export_df_missing_include_flag_uses_unknown_status() -> None:
    """Rows without explicit include/gate columns should be marked unknown."""
    scorecard_df = pd.DataFrame(
        {
            "Vendor": ["ExampleVendor"],
            "Samples Evaluated": [50],
            "Unknown Parsed (%)": [40.0],
            "Generic Family Ratio": [0.2],
            "Family Match Accuracy (%)": [55.0],
        }
    )
    export_df = vendor_metadata_pipeline._build_parser_quality_export_df(scorecard_df)  # pylint: disable=protected-access
    assert export_df.loc[0, "inclusion_status"] == "unknown"


def test_build_parser_quality_export_df_treats_included_relaxed_status_as_included() -> None:
    """Included-relaxed parser statuses should still be included in model flags."""
    scorecard_df = pd.DataFrame(
        {
            "Vendor": ["ExampleVendor"],
            "Samples Evaluated": [50],
            "Unknown Parsed (%)": [20.0],
            "Generic Family Ratio": [0.2],
            "Family Match Accuracy (%)": [8.0],
            "parser_gate_status": ["included_relaxed_mapped"],
        }
    )
    export_df = vendor_metadata_pipeline._build_parser_quality_export_df(scorecard_df)  # pylint: disable=protected-access
    assert int(export_df.loc[0, "included_in_model"]) == 1
    assert export_df.loc[0, "inclusion_status"] == "include"
