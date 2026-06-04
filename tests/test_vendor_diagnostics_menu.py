"""Tests for vendor diagnostics menu fallback behavior."""

from __future__ import annotations

from pathlib import Path

import json
import pandas as pd
import pytest

from obsidiandroid.cli.menu import vendor_diagnostics
from obsidiandroid.cli.menu import vendor_diagnostics_actions
from obsidiandroid.cli.menu import vendor_parser_state

pytestmark = pytest.mark.integration


def _make_vendor_diag_run(make_run_diagnostics_layout, run_id: str) -> tuple[Path, Path]:
    out_root, run_diag, global_diag = make_run_diagnostics_layout(run_id)
    global_diag.mkdir(parents=True, exist_ok=True)
    return out_root, run_diag


def _write_latest_manifest(write_text_file, out_root: Path, payload: dict[str, object]) -> None:
    write_text_file(
        out_root / "diagnostics" / "run_manifest.latest.json",
        json.dumps(payload),
    )


def test_validate_parser_coverage_uses_csv_fallback_when_workbook_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Coverage menu should succeed from latest CSV snapshots without workbook exports."""
    out_dir = tmp_path / "output" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"vendor_column": "a", "coverage_pct": 95.0, "parser_mapped": 1, "is_dynamic_generic": 0},
            {"vendor_column": "b", "coverage_pct": 80.0, "parser_mapped": 0, "is_dynamic_generic": 0},
        ]
    ).to_csv(out_dir / "vendor_parser_coverage.latest.csv", index=False)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vendor_diagnostics_actions, "load_enriched_matrix_for_menu", lambda: None)

    result = vendor_diagnostics.validate_parser_columns_from_latest_export()
    assert result == 0


def test_validate_parser_coverage_fails_when_no_workbook_and_no_csv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Coverage menu should fail cleanly when neither workbook nor CSV snapshots exist."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vendor_diagnostics_actions, "load_enriched_matrix_for_menu", lambda: None)

    result = vendor_diagnostics.validate_parser_columns_from_latest_export()
    assert result == 1


def test_single_vendor_parser_check_reports_missing_enriched_matrix_requirement(
    monkeypatch,
) -> None:
    """Single-vendor diagnostics should explain that enriched matrix exports are required."""
    warnings: list[str] = []
    infos: list[str] = []

    monkeypatch.setattr(
        vendor_diagnostics_actions,
        "load_enriched_matrix_for_menu",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(vendor_diagnostics_actions.du, "print_warning", lambda message: warnings.append(str(message)))
    monkeypatch.setattr(vendor_diagnostics_actions.du, "print_info", lambda message: infos.append(str(message)))

    result = vendor_diagnostics.run_single_vendor_parser_check()

    assert result == 1
    assert any("Workbook drill-down unavailable" in message for message in warnings)
    assert any("latest diagnostics CSV exports" in message for message in infos)


def test_print_parser_diagnostics_state_reports_csv_vs_workbook_context(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, run_diag = _make_vendor_diag_run(make_run_diagnostics_layout, run_id)
    pd.DataFrame(
        [
            {"vendor_column": "a", "coverage_pct": 95.0, "parser_mapped": 1, "is_dynamic_generic": 0},
            {"vendor_column": "b", "coverage_pct": 80.0, "parser_mapped": 0, "is_dynamic_generic": 0},
        ]
    ).to_csv(run_diag / "vendor_parser_coverage.latest.csv", index=False)
    pd.DataFrame([{"engine_name": "a"}, {"engine_name": "b"}]).to_csv(
        run_diag / "engine_scoring_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {"vendor_key": "a", "drift_status": "metadata_and_verdict", "in_metadata_table": 1, "likely_current_vendor_key": "", "suggestion_basis": ""},
            {"vendor_key": "webrootd", "drift_status": "metadata_only", "in_metadata_table": 1, "likely_current_vendor_key": "webroot", "suggestion_basis": "legacy_metadata_alias_to_current_vt_prefix"},
            {"vendor_key": "nod32", "drift_status": "metadata_only", "in_metadata_table": 1, "likely_current_vendor_key": "nod32", "suggestion_basis": "current_vt_documented_prefix_without_verdict_column"},
            {"vendor_key": "mystery_only", "drift_status": "metadata_only", "in_metadata_table": 1, "likely_current_vendor_key": "", "suggestion_basis": ""},
        ]
    ).to_csv(run_diag / "engine_metadata_drift.csv", index=False)
    pd.DataFrame(
        [
            {"engine_name_canonical": "elastic", "near_miss_flag": 1, "coverage_pct": 99.0},
            {"engine_name_canonical": "gridinsoft", "near_miss_flag": 1, "coverage_pct": 95.0},
        ]
    ).to_csv(run_diag / f"engine_exclusion_audit_{run_id}.csv", index=False)
    _write_latest_manifest(
        write_text_file,
        out_root,
        {
            "run_id": run_id,
            "selected_vendor_count": 1,
            "engine_count_observed": 2,
            "engine_count_canonical": 2,
            "engine_count_included_after_gating": 1,
            "engine_count_requested_top_k": 8,
        },
    )

    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)
    monkeypatch.setattr(vendor_diagnostics_actions, "load_enriched_matrix_for_menu", lambda **_kwargs: None)

    vendor_diagnostics.print_parser_diagnostics_state()
    out = capsys.readouterr().out
    assert "[ENGINES] PARSER DIAGNOSTICS" in out
    assert "CSV snapshots" in out
    assert "Workbook drill-down" in out
    assert "Workbook drill-down is optional" in out
    assert "single-vendor" in out
    assert "debugging" in out
    assert "Observed vendor columns" in out
    assert "Cohort engines observed" in out
    assert "Post-score included engines" in out
    assert "Parser mapped vendors" in out
    assert "Onboarding queue" in out
    assert "Selected vendors for latest run" in out
    assert "DB verdict-table universe" in out
    assert "Metadata-only engine keys" in out
    assert "Metadata legacy-alias suggestions" in out
    assert "Current VT prefixes missing verdicts" in out
    assert "Unclear metadata-only keys" in out
    assert "Top metadata alias suggestions" in out
    assert "Excluded near-miss engines" in out
    assert "[ENGINES] Top near-miss engines" in out
    assert "[ACTION] Open first:" in out
    assert "[ACTION] Tune next:" in out


def test_single_vendor_parser_check_compact_blocked_message_without_reprinting_full_state(
    monkeypatch,
    capsys,
) -> None:
    """Blocked single-vendor drill-down should show compact workbook guidance only."""
    monkeypatch.setattr(
        vendor_diagnostics_actions,
        "load_enriched_matrix_for_menu",
        lambda **_kwargs: None,
    )

    result = vendor_diagnostics.run_single_vendor_parser_check()
    out = capsys.readouterr().out

    assert result == 1
    assert "Workbook drill-down" in out
    assert "CSV snapshots" in out
    assert "Onboarding queue" in out
    assert "PARSER DIAGNOSTICS STATE" not in out
    assert "WORKBOOK REQUIRED" not in out


def test_parser_summary_compact_focuses_on_status_and_next_actions(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, run_diag = _make_vendor_diag_run(make_run_diagnostics_layout, run_id)
    pd.DataFrame(
        [
            {"vendor_column": "crowdstrike", "coverage_pct": 100.0, "parser_mapped": 0, "is_dynamic_generic": 0},
            {"vendor_column": "kaspersky", "coverage_pct": 99.0, "parser_mapped": 1, "is_dynamic_generic": 0},
            {"vendor_column": "gdata", "coverage_pct": 98.0, "parser_mapped": 0, "is_dynamic_generic": 0},
        ]
    ).to_csv(run_diag / "vendor_parser_coverage.latest.csv", index=False)
    pd.DataFrame(
        [
            {"priority_rank": 1, "vendor_column": "crowdstrike", "coverage_pct": 100.0, "parser_mapped": 0, "is_dynamic_generic": 0, "onboarding_priority": "high_coverage_unmapped"},
            {"priority_rank": 2, "vendor_column": "gdata", "coverage_pct": 98.0, "parser_mapped": 0, "is_dynamic_generic": 0, "onboarding_priority": "high_coverage_unmapped"},
        ]
    ).to_csv(run_diag / "vendor_parser_coverage_candidates.latest.csv", index=False)
    pd.DataFrame(
        [{"Vendor": "tencent"}, {"Vendor": "lionic"}, {"Vendor": "alibaba"}]
    ).to_csv(run_diag / f"vendor_gate_top10_pre_gate_{run_id}.csv", index=False)
    _write_latest_manifest(write_text_file, out_root, {"run_id": run_id, "selected_vendor_count": 8})

    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)
    monkeypatch.setattr(vendor_diagnostics_actions, "load_enriched_matrix_for_menu", lambda **_kwargs: None)

    vendor_diagnostics.print_compact_vendor_coverage_snapshot()
    out = capsys.readouterr().out
    assert "[ENGINES] Parser summary" in out
    assert "Parser health" in out
    assert "Onboarding queue" in out
    assert "Observed engines are all vendor columns" in out
    assert "[ENGINES] Top onboarding candidates: crowdstrike, gdata" in out
    assert "[ENGINES] Top selected vendors: tencent, lionic, alibaba" in out
    assert "[ACTION] Open first:" in out
    assert "Source file" not in out


def test_parser_onboarding_queue_shows_top_10_and_tuning_columns(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, run_diag = _make_vendor_diag_run(make_run_diagnostics_layout, run_id)
    coverage_rows = []
    candidate_rows = []
    names = ["crowdstrike", "gdata", "k7antivirus", "microworld_escan", "paloalto", "superantispyware", "symantecmobileinsight", "tachyon", "trustlook", "virobot", "acronis"]
    for idx, name in enumerate(names, start=1):
        coverage_rows.append({"vendor_column": name, "coverage_pct": 100.0 - idx, "parser_mapped": 0, "is_dynamic_generic": 0})
        candidate_rows.append({"priority_rank": idx, "vendor_column": name, "coverage_pct": 100.0 - idx, "parser_mapped": 0, "is_dynamic_generic": 0, "onboarding_priority": "high_coverage_unmapped"})
    pd.DataFrame(coverage_rows).to_csv(run_diag / "vendor_parser_coverage.latest.csv", index=False)
    pd.DataFrame(candidate_rows).to_csv(run_diag / "vendor_parser_coverage_candidates.latest.csv", index=False)
    pd.DataFrame(
        [
            {"vendor": "crowdstrike", "inclusion_status": "exclude", "mapped_ratio": 0.0, "unknown_ratio": 0.8, "generic_ratio": 0.8, "trusted_vendor_flag": 0, "active_vendor_flag": 1, "strength_tags": "", "weakness_tags": "high_unknown"},
            {"vendor": "trustlook", "inclusion_status": "exclude", "mapped_ratio": 0.0, "unknown_ratio": 0.2, "generic_ratio": 0.2, "trusted_vendor_flag": 0, "active_vendor_flag": 1, "strength_tags": "", "weakness_tags": "coverage_only"},
        ]
    ).to_csv(run_diag / "vendor_parser_strengths_weaknesses.latest.csv", index=False)
    pd.DataFrame([{"Vendor": "trustlook", "Family Match Accuracy (%)": 15.0, "Vendor Category": "High Diversity", "rank": 1}]).to_csv(
        run_diag / f"vendor_gate_top10_pre_gate_{run_id}.csv",
        index=False,
    )
    _write_latest_manifest(write_text_file, out_root, {"run_id": run_id, "selected_vendor_count": 1})

    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    vendor_diagnostics.print_parser_onboarding_candidates()
    out = capsys.readouterr().out
    assert "Top 10 parser onboarding candidates" in out
    assert "selected_in_latest_run" in out
    assert "trusted_active" in out
    assert "priority_reason" in out
    assert "recommended_action" in out
    assert "acronis" not in out
