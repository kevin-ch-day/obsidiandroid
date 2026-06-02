"""Tests for parser diagnostics state helpers."""

from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from obsidiandroid.cli.menu import vendor_parser_state


def test_resolve_vendor_parser_coverage_csv_prefers_run_scoped_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Run-scoped parser coverage should win over the global latest mirror."""
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    (run_diag / f"vendor_parser_coverage_{run_id}.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (global_diag / "vendor_parser_coverage.latest.csv").write_text("a,b\n3,4\n", encoding="utf-8")

    monkeypatch.setattr(vendor_parser_state.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    resolved = vendor_parser_state.resolve_vendor_parser_coverage_csv()

    assert resolved == run_diag / f"vendor_parser_coverage_{run_id}.csv"


def test_build_parser_diagnostics_state_returns_compact_counts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Parser diagnostics state should return stable summary counts and paths."""
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"vendor_column": "a", "coverage_pct": 95.0, "parser_mapped": 1},
            {"vendor_column": "b", "coverage_pct": 80.0, "parser_mapped": 0},
        ]
    ).to_csv(run_diag / f"vendor_parser_coverage_{run_id}.csv", index=False)
    pd.DataFrame([{"engine_name": "a"}, {"engine_name": "b"}]).to_csv(
        run_diag / "engine_scoring_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {"vendor_key": "a", "drift_status": "metadata_and_verdict", "in_metadata_table": 1, "likely_current_vendor_key": "", "suggestion_basis": ""},
            {"vendor_key": "b", "drift_status": "verdict_only", "in_metadata_table": 0, "likely_current_vendor_key": "", "suggestion_basis": ""},
            {"vendor_key": "webrootd", "drift_status": "metadata_only", "in_metadata_table": 1, "likely_current_vendor_key": "webroot", "suggestion_basis": "legacy_metadata_alias_to_current_vt_prefix"},
            {"vendor_key": "nod32", "drift_status": "metadata_only", "in_metadata_table": 1, "likely_current_vendor_key": "nod32", "suggestion_basis": "current_vt_documented_prefix_without_verdict_column"},
            {"vendor_key": "mystery_key", "drift_status": "metadata_only", "in_metadata_table": 1, "likely_current_vendor_key": "", "suggestion_basis": ""},
        ]
    ).to_csv(run_diag / "engine_metadata_drift.csv", index=False)
    pd.DataFrame(
        [
            {"engine_name_canonical": "elastic", "near_miss_flag": 1, "coverage_pct": 99.0},
            {"engine_name_canonical": "gridinsoft", "near_miss_flag": 1, "coverage_pct": 95.0},
            {"engine_name_canonical": "bytehero", "near_miss_flag": 0, "coverage_pct": 10.0},
        ]
    ).to_csv(run_diag / f"engine_exclusion_audit_{run_id}.csv", index=False)
    (global_diag / "run_manifest.latest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "selected_vendor_count": 8,
                "engine_count_observed": 2,
                "engine_count_canonical": 2,
                "engine_count_included_after_gating": 1,
                "engine_count_requested_top_k": 8,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(vendor_parser_state.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    state = vendor_parser_state.build_parser_diagnostics_state(
        workbook_loader=lambda **_kwargs: None
    )

    assert state["csv_ready"] is True
    assert state["workbook_ready"] is False
    assert state["observed_engines"] == 2
    assert state["parser_mapped_vendors"] == 1
    assert state["unmapped_vendors"] == 1
    assert state["selected_vendors"] == 8
    assert state["engine_scoring_universe"] == 2
    assert state["cohort_engines_observed"] == 2
    assert state["cohort_engines_canonical"] == 2
    assert state["post_score_engines_included"] == 1
    assert state["requested_parser_top_k"] == 8
    assert state["engine_metadata_table_universe"] == 4
    assert state["engine_metadata_only_count"] == 3
    assert state["engine_verdict_only_count"] == 1
    assert state["engine_metadata_alias_suggestion_count"] == 1
    assert state["engine_metadata_current_prefix_missing_verdict_count"] == 1
    assert state["engine_metadata_unclear_count"] == 1
    assert state["top_metadata_alias_preview"] == ["webrootd->webroot"]
    assert state["engine_exclusion_audit_rows"] == 3
    assert state["engine_near_miss_count"] == 2
    assert state["top_near_miss_preview"] == ["elastic", "gridinsoft"]
    assert state["source_run_id"] == run_id
    assert state["coverage_from_latest_run"] is True
    assert state["selected_vendor_data_present"] is False


def test_build_parser_diagnostics_state_parses_string_near_miss_flags(
    monkeypatch,
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"vendor_column": "a", "coverage_pct": 95.0, "parser_mapped": 1}]
    ).to_csv(run_diag / f"vendor_parser_coverage_{run_id}.csv", index=False)
    pd.DataFrame([{"engine_name": "a"}]).to_csv(
        run_diag / "engine_scoring_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {"vendor_key": "a", "drift_status": "metadata_and_verdict", "in_metadata_table": 1, "likely_current_vendor_key": "", "suggestion_basis": ""},
        ]
    ).to_csv(run_diag / "engine_metadata_drift.csv", index=False)
    pd.DataFrame(
        [
            {"engine_name_canonical": "elastic", "near_miss_flag": "True", "coverage_pct": 99.0},
            {"engine_name_canonical": "bytehero", "near_miss_flag": "False", "coverage_pct": 10.0},
        ]
    ).to_csv(run_diag / f"engine_exclusion_audit_{run_id}.csv", index=False)
    (global_diag / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id, "selected_vendor_count": 1}),
        encoding="utf-8",
    )

    monkeypatch.setattr(vendor_parser_state.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    state = vendor_parser_state.build_parser_diagnostics_state(
        workbook_loader=lambda **_kwargs: None
    )

    assert state["engine_exclusion_audit_rows"] == 2
    assert state["engine_near_miss_count"] == 1
    assert state["top_near_miss_preview"] == ["elastic"]


def test_resolve_vendor_gate_pre_gate_and_candidates_prefer_run_scoped_named_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    (run_diag / f"vendor_parser_coverage_candidates_{run_id}.csv").write_text(
        "vendor_column,coverage_pct\nv,99\n",
        encoding="utf-8",
    )
    (run_diag / f"vendor_gate_top10_pre_gate_{run_id}.csv").write_text(
        "Vendor\nv\n",
        encoding="utf-8",
    )
    (global_diag / "vendor_parser_coverage_candidates.latest.csv").write_text(
        "vendor_column,coverage_pct\nx,88\n",
        encoding="utf-8",
    )
    (global_diag / "vendor_gate_top10_pre_gate.latest.csv").write_text(
        "Vendor\nx\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(vendor_parser_state.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    assert (
        vendor_parser_state.resolve_vendor_parser_coverage_candidates_csv()
        == run_diag / f"vendor_parser_coverage_candidates_{run_id}.csv"
    )
    assert (
        vendor_parser_state.resolve_vendor_gate_pre_gate_csv()
        == run_diag / f"vendor_gate_top10_pre_gate_{run_id}.csv"
    )


def test_resolve_vendor_parser_strengths_and_stress_prefer_run_scoped_named_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    (run_diag / f"vendor_parser_stress_test_{run_id}.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (run_diag / f"vendor_parser_strengths_weaknesses_{run_id}.csv").write_text(
        "vendor,inclusion_status\nv,include\n", encoding="utf-8"
    )
    (global_diag / "vendor_parser_stress_test.latest.csv").write_text("a,b\n3,4\n", encoding="utf-8")
    (global_diag / "vendor_parser_strengths_weaknesses.latest.csv").write_text(
        "vendor,inclusion_status\nx,exclude\n", encoding="utf-8"
    )

    monkeypatch.setattr(vendor_parser_state.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    assert vendor_parser_state.resolve_vendor_stress_test_csv() == run_diag / f"vendor_parser_stress_test_{run_id}.csv"
    assert (
        vendor_parser_state.resolve_vendor_strengths_weaknesses_csv()
        == run_diag / f"vendor_parser_strengths_weaknesses_{run_id}.csv"
    )
