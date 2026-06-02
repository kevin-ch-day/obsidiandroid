"""Tests for AV engine scoring export behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.pipeline import score_av_engines


def test_run_av_engine_scoring_writes_run_scoped_engine_lifecycle_without_local_latest(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(score_av_engines, "export_matrix", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        score_av_engines,
        "fetch_engine_metadata",
        lambda *args, **kwargs: {"engine_a": {"is_trusted_vendor": 1, "is_engine_active": 1}},
    )
    monkeypatch.setattr(
        score_av_engines.phase_score_engines,
        "score_av_engines_from_matrix",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "Engine Name": "engine_a",
                    "ML Weight Score": 42.0,
                    "Included": True,
                    "Exclusion Reason": "included",
                    "Detection Tier": "Tier 1 (High)",
                    "Coverage %": 100.0,
                    "Detection %": 50.0,
                }
            ]
        ),
    )

    matrix_df = pd.DataFrame({"sample_id": [1, 2], "engine_a": [1, 0]})
    matrix_df.attrs["engine_scan_counts"] = {"engine_a": 2}

    result = score_av_engines.run_av_engine_scoring(
        matrix_df,
        config={"run_id": "rid", "profile_context": "dev_fast"},
        verbose=False,
    )

    assert not result.empty
    run_scoped = diagnostics_dir / "engine_lifecycle_rid.csv"
    assert run_scoped.is_file()
    assert not (diagnostics_dir / "engine_lifecycle.latest.csv").exists()
    assert (output_root / "diagnostics" / "engine_lifecycle.latest.csv").is_file()
    assert isinstance(result.attrs.get("engine_lifecycle"), pd.DataFrame)
    lifecycle_df = result.attrs["engine_lifecycle"]
    assert {
        "samples_scanned",
        "malicious_flags",
        "coverage_pct",
        "detection_pct",
        "trusted_vendor_flag",
        "active_vendor_flag",
        "raw_exclusion_reason",
        "threshold_fail_count",
        "threshold_failed_checks",
        "near_miss_flag",
        "min_samples_scanned_threshold",
        "min_coverage_pct_threshold",
        "min_positive_flags_threshold",
        "min_detection_pct_threshold",
    }.issubset(lifecycle_df.columns)
    assert not (diagnostics_dir / "engine_exclusion_audit_rid.csv").exists()


def test_lifecycle_path_uses_global_named_target_when_runtime_dir_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    diagnostics_root = output_root / "diagnostics"
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    assert score_av_engines._lifecycle_path() == diagnostics_root / "engine_lifecycle_rid.csv"  # pylint: disable=protected-access


def test_run_av_engine_scoring_writes_run_scoped_lifecycle_even_when_global_latest_exists(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, global_diag = make_run_diagnostics_layout("rid")
    (global_diag / "engine_lifecycle.latest.csv").write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(score_av_engines, "export_matrix", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        score_av_engines,
        "fetch_engine_metadata",
        lambda *args, **kwargs: {"engine_a": {"is_trusted_vendor": 1, "is_engine_active": 1}},
    )
    monkeypatch.setattr(
        score_av_engines.phase_score_engines,
        "score_av_engines_from_matrix",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "Engine Name": "engine_a",
                    "ML Weight Score": 42.0,
                    "Included": True,
                    "Exclusion Reason": "included",
                    "Detection Tier": "Tier 1 (High)",
                    "Coverage %": 100.0,
                    "Detection %": 50.0,
                    "Samples Scanned": 2,
                    "Malicious Flags": 1,
                    "Trusted": 1,
                    "Active": 1,
                }
            ]
        ),
    )

    matrix_df = pd.DataFrame({"sample_id": [1, 2], "engine_a": [1, 0]})
    matrix_df.attrs["engine_scan_counts"] = {"engine_a": 2}

    result = score_av_engines.run_av_engine_scoring(
        matrix_df,
        config={"run_id": "rid", "profile_context": "dev_fast"},
        verbose=False,
    )

    assert not result.empty
    assert (diagnostics_dir / "engine_lifecycle_rid.csv").is_file()


def test_run_av_engine_scoring_marks_threshold_near_miss_and_exports_audit(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(score_av_engines, "export_matrix", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        score_av_engines,
        "fetch_engine_metadata",
        lambda *args, **kwargs: {"engine_a": {"is_trusted_vendor": 1, "is_engine_active": 1}},
    )
    monkeypatch.setattr(
        score_av_engines.phase_score_engines,
        "score_av_engines_from_matrix",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "Engine Name": "engine_a",
                    "ML Weight Score": 42.0,
                    "Included": True,
                    "Exclusion Reason": "included",
                    "Detection Tier": "Tier 1 (High)",
                    "Coverage %": 100.0,
                    "Detection %": 60.0,
                    "Samples Scanned": 5,
                    "Malicious Flags": 3,
                    "Trusted": 1,
                    "Active": 1,
                    "Threshold Fail Count": 0,
                    "Threshold Failed Checks": "",
                    "Near Miss": False,
                },
                {
                    "Engine Name": "engine_b",
                    "ML Weight Score": 0.0,
                    "Included": False,
                    "Exclusion Reason": "low_positive_flags",
                    "Detection Tier": "Excluded",
                    "Coverage %": 100.0,
                    "Detection %": 40.0,
                    "Samples Scanned": 5,
                    "Malicious Flags": 4,
                    "Trusted": 1,
                    "Active": 1,
                    "Threshold Fail Count": 1,
                    "Threshold Failed Checks": "positive_flags",
                    "Near Miss": True,
                }
            ]
        ),
    )

    matrix_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "engine_a": [1, 1, 1, 0, 0],
            "engine_b": [1, 1, 1, 1, 0],
        }
    )
    matrix_df.attrs["engine_scan_counts"] = {"engine_a": 5, "engine_b": 5}

    result = score_av_engines.run_av_engine_scoring(
        matrix_df,
        config={"run_id": "rid", "profile_context": "dev_fast"},
        verbose=False,
    )

    assert not result.empty
    lifecycle_df = result.attrs["engine_lifecycle"]
    assert int(result.attrs.get("engine_near_miss_count", 0)) == 1
    excluded_row = lifecycle_df[lifecycle_df["included_in_model_flag"].fillna(False).astype(bool) == False].iloc[0]  # noqa: E712
    assert bool(excluded_row["near_miss_flag"]) is True
    assert excluded_row["threshold_failed_checks"] == "positive_flags"
    audit_df = pd.read_csv(diagnostics_dir / "engine_exclusion_audit_rid.csv")
    assert int(audit_df["near_miss_flag"].fillna(False).astype(bool).sum()) == 1


def test_run_av_engine_scoring_resolves_duplicate_canonical_aliases_without_failing(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(score_av_engines, "export_matrix", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        score_av_engines.engine_normalization,
        "load_engine_aliases",
        lambda: {"engine_a_2": "engine_a"},
    )
    monkeypatch.setattr(
        score_av_engines,
        "fetch_engine_metadata",
        lambda *args, **kwargs: {"engine_a": {"is_trusted_vendor": 1, "is_engine_active": 1}},
    )
    monkeypatch.setattr(
        score_av_engines.phase_score_engines,
        "score_av_engines_from_matrix",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "Engine Name": "engine_a",
                    "ML Weight Score": 42.0,
                    "Included": True,
                    "Exclusion Reason": "included",
                    "Detection Tier": "Tier 1 (High)",
                    "Coverage %": 100.0,
                    "Detection %": 50.0,
                    "Samples Scanned": 2,
                    "Malicious Flags": 1,
                    "Trusted": 1,
                    "Active": 1,
                }
            ]
        ),
    )

    matrix_df = pd.DataFrame(
        {"sample_id": [1, 2], "engine_a": [1, 0], "engine_a_2": [1, 0]}
    )
    matrix_df.attrs["engine_scan_counts"] = {"engine_a": 2, "engine_a_2": 2}

    result = score_av_engines.run_av_engine_scoring(
        matrix_df,
        config={"run_id": "rid", "profile_context": "dev_fast"},
        verbose=False,
    )

    assert not result.empty
    assert int(result.attrs.get("engine_observed_count", 0)) == 2
    assert int(result.attrs.get("engine_canonical_count", 0)) == 1
    lifecycle_df = result.attrs["engine_lifecycle"]
    assert int((lifecycle_df["exclusion_stage"] == "excluded_prescore").sum()) == 1


def test_run_av_engine_scoring_canonical_count_excludes_invalid_raw_names(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(score_av_engines, "export_matrix", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        score_av_engines,
        "fetch_engine_metadata",
        lambda *args, **kwargs: {"engine_a": {"is_trusted_vendor": 1, "is_engine_active": 1}},
    )
    monkeypatch.setattr(
        score_av_engines.phase_score_engines,
        "score_av_engines_from_matrix",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "Engine Name": "engine_a",
                    "ML Weight Score": 42.0,
                    "Included": True,
                    "Exclusion Reason": "included",
                    "Detection Tier": "Tier 1 (High)",
                    "Coverage %": 100.0,
                    "Detection %": 50.0,
                    "Samples Scanned": 2,
                    "Malicious Flags": 1,
                    "Trusted": 1,
                    "Active": 1,
                }
            ]
        ),
    )

    matrix_df = pd.DataFrame({"sample_id": [1, 2], "engine_a": [1, 0], "!!!": [0, 0]})
    matrix_df.attrs["engine_scan_counts"] = {"engine_a": 2, "!!!": 2}

    result = score_av_engines.run_av_engine_scoring(
        matrix_df,
        config={"run_id": "rid", "profile_context": "dev_fast"},
        verbose=False,
    )

    assert not result.empty
    assert int(result.attrs.get("engine_observed_count", 0)) == 2
    assert int(result.attrs.get("engine_canonical_count", 0)) == 1
