"""Tests for startup menu maintenance helpers."""

from __future__ import annotations

from pathlib import Path
import json

from config import app_config

import obsidiandroid.cli.startup_menu as startup_menu


def test_main_menu_clear_screen_option(monkeypatch) -> None:
    """Main menu clear option should call clear_screen and continue loop."""
    choices = iter([6, 0])
    clear_calls = {"count": 0}

    monkeypatch.setattr(startup_menu, "_print_startup_context", lambda: None)
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(startup_menu.du, "clear_console", lambda: clear_calls.__setitem__("count", clear_calls["count"] + 1))

    result = startup_menu.launch_startup_menu()

    assert result == 0
    assert clear_calls["count"] == 1


def test_main_menu_uses_concise_title_and_primary_workflow_order(monkeypatch) -> None:
    """Top-level menu should stay concise and ordered around the main workflow."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(startup_menu, "_print_startup_context", lambda: None)
    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    result = startup_menu.launch_startup_menu()

    assert result == 0
    assert captured["title"] == "Main menu"
    assert captured["labels"] == [
        "Run Analysis",
        "Run Status and History",
        "Research Reports",
        "Validation and Diagnostics",
        "Tools and Maintenance",
        "Clear Screen",
    ]


def test_run_analysis_menu_uses_operator_facing_actions(monkeypatch) -> None:
    """Run analysis submenu should list pipeline modes in operator order."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    result = startup_menu._launch_pipeline_actions_menu()  # pylint: disable=protected-access

    assert result == 0
    assert captured["title"] == "Pipeline run mode"
    assert captured["labels"] == [
        "Full pipeline",
        "Fast development",
        "Smoke test",
        "Single model only",
        "Stop after a stage",
        "Vendor extraction only",
        "Retrain from cached alignment",
    ]


def test_maintenance_menu_uses_operator_facing_actions(monkeypatch) -> None:
    """Maintenance submenu should use concise labels."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_maintenance_menu()  # pylint: disable=protected-access

    assert captured["title"] == "Maintenance tools"
    assert captured["labels"] == [
        "Engine Scoring Summary",
        "Parser Coverage Review",
        "Single Vendor Parser Diagnostic",
        "Parser Snapshot",
        "Run Health Check",
        "Structural Diagnostics",
        "Smart Output Cleanup",
        "Claim Artifact Map",
        "Evidence Bundle Checker",
    ]


def test_main_menu_submenu_back_does_not_warn_invalid(monkeypatch) -> None:
    """Returning from a submenu should not emit a false invalid-choice warning."""
    choices = iter([4, 0, 0])
    warnings: list[str] = []

    monkeypatch.setattr(startup_menu, "_print_startup_context", lambda: None)
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(startup_menu.du, "print_warning", lambda message: warnings.append(str(message)))

    result = startup_menu.launch_startup_menu()

    assert result == 0
    assert "[MENU] Invalid choice received." not in warnings


def test_validation_diagnostics_menu_uses_back_label(monkeypatch) -> None:
    """Submenus should present 0 as Back, not Exit."""
    captured: list[str] = []

    def _fake_display_menu(*_args, **kwargs):
        captured.append(str(kwargs.get("exit_label", "")))
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_validation_diagnostics_menu()  # pylint: disable=protected-access

    assert captured == ["Back"]


def test_read_latest_run_id_prefers_newest_run_scoped_manifest(monkeypatch, tmp_path: Path) -> None:
    """Latest run banner should prefer the newest run-scoped manifest over stale pointers."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    old_run = runs_dir / "20260307T213823Z__b74bdb"
    new_run = runs_dir / "20260321T134027Z__f39e96"
    old_run.mkdir(parents=True, exist_ok=True)
    new_run.mkdir(parents=True, exist_ok=True)
    (old_run / "run_manifest.json").write_text("{}", encoding="utf-8")
    (new_run / "run_manifest.json").write_text("{}", encoding="utf-8")

    promoted_dir = out_root / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    (promoted_dir / "latest_run.txt").write_text("20260307T213823Z__b74bdb", encoding="utf-8")

    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": "20260307T213823Z__b74bdb"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)

    assert startup_menu._read_latest_run_id() == "20260321T134027Z__f39e96"  # pylint: disable=protected-access


def test_read_latest_run_id_ignores_invalid_test_run_ids(monkeypatch, tmp_path: Path) -> None:
    """Latest run banner should prefer valid timestamped runs over junk ids like r1."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    valid_run = runs_dir / "20260321T134027Z__f39e96"
    junk_run = runs_dir / "r1"
    valid_run.mkdir(parents=True, exist_ok=True)
    junk_run.mkdir(parents=True, exist_ok=True)
    (valid_run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260321T134027Z__f39e96",
                "timestamp_utc": "2026-03-21T13:40:27.139708+00:00",
            }
        ),
        encoding="utf-8",
    )
    (junk_run / "run_manifest.json").write_text(
        json.dumps({"run_id": "r1", "timestamp_utc": "t1"}),
        encoding="utf-8",
    )

    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": "r1"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)

    assert startup_menu._read_latest_run_id() == "20260321T134027Z__f39e96"  # pylint: disable=protected-access


def test_quick_health_check_passes_with_complete_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Quick health check should pass when required latest artifacts are present."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    run_id = "20260303T000000Z__abc123"
    run_root = out_root / "runs" / run_id
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)

    split_path = diagnostics_dir / f"split_freeze_audit_{run_id}.csv"
    model_config_path = diagnostics_dir / f"model_config_snapshot_{run_id}.json"
    vendor_gate_path = diagnostics_dir / f"vendor_gate_debug_{run_id}.csv"
    run_paths_manifest_path = diagnostics_dir / f"run_paths_manifest_{run_id}.json"
    split_path.write_text("sample_id,fold\n1,0\n", encoding="utf-8")
    model_config_path.write_text("{}", encoding="utf-8")
    vendor_gate_path.write_text("vendor,ok\nv,1\n", encoding="utf-8")
    run_paths_manifest_path.write_text("{}", encoding="utf-8")
    (diagnostics_dir / "parser_quality.latest.csv").write_text("vendor,parser_mapped\nv,1\n", encoding="utf-8")
    (diagnostics_dir / "vendor_parser_coverage.latest.csv").write_text(
        "vendor,parser_mapped\nv,1\n",
        encoding="utf-8",
    )

    manifest_payload = {
        "run_id": run_id,
        "timestamp_utc": "2026-03-03T00:00:00Z",
        "split": {"split_audit_path": str(split_path)},
        "model_config_snapshot_path": str(model_config_path),
        "vendor_gate_debug_path": str(vendor_gate_path),
        "profile_params": {"profile_id": "dev_fast"},
        "artifact_list": [],
    }
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps(manifest_payload),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_quick_health_check()  # pylint: disable=protected-access
    assert result == 0


def test_quick_health_check_fails_when_pointer_manifest_has_no_canonical(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Quick health check should fail for pointer manifest without canonical run manifest."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    pointer_payload = {
        "run_id": "20260303T000000Z__abc123",
        "created_at_utc": "2026-03-03T00:00:00Z",
        "run_root": str(out_root / "runs" / "20260303T000000Z__abc123"),
    }
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps(pointer_payload),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_quick_health_check()  # pylint: disable=protected-access
    assert result == 1


def test_quick_health_check_warns_but_passes_without_optional_diagnostics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Quick health check should return success when only non-fatal checks are missing."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    run_id = "20260303T000000Z__abc123"
    run_root = out_root / "runs" / run_id
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)

    split_path = diagnostics_dir / f"split_freeze_audit_{run_id}.csv"
    model_config_path = diagnostics_dir / f"model_config_snapshot_{run_id}.json"
    split_path.write_text("sample_id,fold\n1,0\n", encoding="utf-8")
    model_config_path.write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "timestamp_utc": "2026-03-03T00:00:00Z",
                "split": {"split_audit_path": str(split_path)},
                "model_config_snapshot_path": str(model_config_path),
                "profile_params": {"profile_id": "dev_fast"},
                "artifact_list": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_quick_health_check()  # pylint: disable=protected-access
    assert result == 0


def test_run_specific_health_check_writes_json_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Run-specific health check should emit a run-scoped JSON report."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    run_id = "20260303T010000Z__def456"
    run_root = out_root / "runs" / run_id
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)

    split_path = diagnostics_dir / f"split_freeze_audit_{run_id}.csv"
    model_config_path = diagnostics_dir / f"model_config_snapshot_{run_id}.json"
    split_path.write_text("sample_id,fold\n1,0\n", encoding="utf-8")
    model_config_path.write_text("{}", encoding="utf-8")
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "timestamp_utc": "2026-03-03T01:00:00Z",
                "split": {"split_audit_path": str(split_path)},
                "model_config_snapshot_path": str(model_config_path),
                "profile_params": {"profile_id": "paper2_primary"},
                "artifact_list": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_health_check(run_id=run_id)  # pylint: disable=protected-access

    assert result == 0
    report_path = diagnostics_dir / f"quick_health_check_{run_id}.json"
    assert report_path.exists()


def test_recent_runs_overview_returns_warning_when_empty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Recent runs overview should return non-zero when no run manifests exist."""
    out_root = tmp_path / "output"
    (out_root / "runs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)

    result = startup_menu._show_recent_runs_overview()  # pylint: disable=protected-access
    assert result == 1


def test_recent_runs_overview_reads_run_scoped_manifests(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Recent runs overview should succeed when run-scoped manifests are present."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    run_a = runs_dir / "20260303T020000Z__aaa111"
    run_b = runs_dir / "20260303T030000Z__bbb222"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)

    (run_a / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260303T020000Z__aaa111",
                "timestamp_utc": "2026-03-03T02:00:00Z",
                "cohort_size": 1200,
                "profile_params": {"profile_id": "all_malicious"},
                "model_summary": {"top_model": "random_forest", "top_macro_f1": 0.71},
            }
        ),
        encoding="utf-8",
    )
    (run_b / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260303T030000Z__bbb222",
                "timestamp_utc": "2026-03-03T03:00:00Z",
                "cohort_size": 1300,
                "profile_params": {"profile_id": "dev_fast"},
                "model_summary": {"top_model": "logistic_regression", "top_macro_f1": 0.80},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access
    assert result == 0


def test_recent_runs_overview_demotes_invalid_run_ids(monkeypatch, tmp_path: Path) -> None:
    """Recent runs table should hide junk ids like r1 from the default operator view."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    valid_run = runs_dir / "20260321T161433Z__fdaeb0"
    junk_run = runs_dir / "r1"
    valid_run.mkdir(parents=True, exist_ok=True)
    junk_run.mkdir(parents=True, exist_ok=True)

    (valid_run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260321T161433Z__fdaeb0",
                "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
                "profile_params": {"profile_id": "research_all_malicious"},
            }
        ),
        encoding="utf-8",
    )
    (junk_run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "timestamp_utc": "t1",
                "profile_params": {"profile_id": "test"},
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_print_table(rows, *_, **__):
        captured["rows"] = rows

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(startup_menu.du, "print_table", _fake_print_table)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert [row["run_id"] for row in captured["rows"]] == ["20260321T161433Z__fdaeb0"]


def test_recent_runs_overview_can_include_noncanonical_runs(monkeypatch, tmp_path: Path) -> None:
    """Advanced history view should include non-canonical run folders when requested."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    valid_run = runs_dir / "20260321T161433Z__fdaeb0"
    junk_run = runs_dir / "r1"
    valid_run.mkdir(parents=True, exist_ok=True)
    junk_run.mkdir(parents=True, exist_ok=True)

    (valid_run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260321T161433Z__fdaeb0",
                "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
                "profile_params": {"profile_id": "research_all_malicious"},
            }
        ),
        encoding="utf-8",
    )
    (junk_run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "timestamp_utc": "t1",
                "profile_params": {"profile_id": "test"},
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_print_table(rows, *_, **__):
        captured["rows"] = rows

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(startup_menu.du, "print_table", _fake_print_table)

    result = startup_menu._show_recent_runs_overview(limit=5, include_noncanonical=True)  # pylint: disable=protected-access

    assert result == 0
    assert [row["run_id"] for row in captured["rows"]] == [
        "20260321T161433Z__fdaeb0",
        "r1",
    ]


def test_recent_runs_overview_uses_runtime_and_model_fallbacks(monkeypatch, tmp_path: Path) -> None:
    """Recent run history should use run-scoped fallbacks when manifest fields are missing."""
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
                "cohort_size": 1226,
                "profile_params": {"profile_id": "research_all_malicious"},
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"pipeline_stage_timings_{run_id}.csv").write_text(
        "stage,duration_sec,run_id,timestamp_utc\n"
        f"samples,1.2,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"training,3.4,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"manifest,0.4,{run_id},2026-03-21T16:17:41.213765+00:00\n",
        encoding="utf-8",
    )
    (diagnostics_dir / f"model_comparison_summary_{run_id}.csv").write_text(
        "Model,Macro F1-Score,Rank,Top\n"
        "random_forest,0.9530,1,*\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_print_table(rows, *_, **__):
        captured["rows"] = rows

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(startup_menu.du, "print_table", _fake_print_table)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert captured["rows"][0]["top_model"] == "random_forest"
    assert captured["rows"][0]["top_macro_f1"] == "0.9530"
    assert captured["rows"][0]["runtime_sec"] == "5.00"


def test_recent_runs_overview_prefers_canonical_run_summary(monkeypatch, tmp_path: Path) -> None:
    """Recent run history should use run_summary.json when manifest fields are thin."""
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
                "profile_params": {"profile_id": "research_all_malicious"},
            }
        ),
        encoding="utf-8",
    )
    (run_root / "run_summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": "research_all_malicious",
                "cohort_size": 1226,
                "top_model": "xgboost",
                "top_macro_f1": 0.9444,
                "pipeline_runtime_sec": 42.5,
                "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_print_table(rows, *_, **__):
        captured["rows"] = rows

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(startup_menu.du, "print_table", _fake_print_table)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert captured["rows"][0]["top_model"] == "xgboost"
    assert captured["rows"][0]["top_macro_f1"] == "0.9444"
    assert captured["rows"][0]["runtime_sec"] == 42.5


def test_run_status_history_menu_includes_advanced_history_option(monkeypatch) -> None:
    """Run status menu should expose an explicit advanced history option."""
    captured: list[str] = []

    def _fake_display_menu(options, *_, **__):
        captured.extend(list(options))
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_run_overview_menu()  # pylint: disable=protected-access

    assert captured == [
        "Current Run Summary",
        "Recent Run History",
        "Session and Output Details",
        "Full Run Folder History (Advanced)",
    ]


def test_current_run_summary_uses_status_aware_fallbacks(monkeypatch, tmp_path: Path) -> None:
    """Current run summary should use stage/model exports when manifest fields are thin."""
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)

    (out_root / "diagnostics" / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id}),
        encoding="utf-8",
    )
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
                "cohort_size": 1226,
                "selected_vendor_count": 8,
                "vendor_constrained_run_flag": False,
                "profile_params": {"profile_id": "research_all_malicious"},
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"pipeline_stage_timings_{run_id}.csv").write_text(
        "stage,duration_sec,run_id,timestamp_utc\n"
        f"samples,1.2,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"training,3.4,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"manifest,0.4,{run_id},2026-03-21T16:17:41.213765+00:00\n",
        encoding="utf-8",
    )
    (diagnostics_dir / f"model_comparison_summary_{run_id}.csv").write_text(
        "Model,Macro F1-Score,Rank,Top\n"
        "random_forest,0.9530,1,*\n"
        "xgboost,0.9412,2,\n",
        encoding="utf-8",
    )

    captured: list[tuple[str, object]] = []

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(startup_menu.du, "print_stat", lambda label, value, *args, **kwargs: captured.append((str(label), value)))

    result = startup_menu._show_latest_run_snapshot()  # pylint: disable=protected-access

    values = {label: value for label, value in captured}
    assert result == 0
    assert values["Run Status"] == "Complete"
    assert values["Completed Through Stage"] == "Manifest Finalization"
    assert values["Top Model"] == "random_forest"
    assert values["Top Macro F1"] == "0.9530"


def test_within_cross_type_error_snapshot_reads_bundle_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Within-vs-cross snapshot should load bundle artifact and render summary."""
    out_root = tmp_path / "output"
    run_id = "20260305T055230Z__f3e105"
    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id}),
        encoding="utf-8",
    )
    confusion_path = (
        out_root
        / "runs"
        / run_id
        / "bundles"
        / "permission_trends"
        / "tables"
        / "confusion_within_vs_cross_type.latest.csv"
    )
    confusion_path.parent.mkdir(parents=True, exist_ok=True)
    confusion_path.write_text(
        "run_id,error_type,count\n"
        f"{run_id},within_type_error,41\n"
        f"{run_id},cross_type_error,39\n"
        f"{run_id},total_error,80\n"
        f"{run_id},within_type_error_ratio,0.5125\n"
        f"{run_id},cross_type_error_ratio,0.4875\n"
        f"{run_id},total_predictions,1286\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._show_within_cross_type_error_snapshot()  # pylint: disable=protected-access
    assert result == 0


def test_within_cross_type_error_snapshot_fails_on_missing_schema(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Within-vs-cross snapshot should fail if required columns are missing."""
    out_root = tmp_path / "output"
    confusion_path = (
        out_root
        / "bundles"
        / "latest"
        / "permission_trends"
        / "tables"
        / "confusion_within_vs_cross_type.latest.csv"
    )
    confusion_path.parent.mkdir(parents=True, exist_ok=True)
    confusion_path.write_text("run_id,bad_col\nr1,1\n", encoding="utf-8")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._show_within_cross_type_error_snapshot()  # pylint: disable=protected-access
    assert result == 1


def test_handle_confusion_matrix_export_blocks_multi_model_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Confusion export should not copy a primary matrix when multiple model matrices exist."""
    out_root = tmp_path / "output"
    run_id = "20260305T101010Z__abc123"
    diagnostics_dir = out_root / "diagnostics"
    run_root = out_root / "runs" / run_id
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id, "run_root": str(run_root)}),
        encoding="utf-8",
    )
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "model_summary": {"top_model": "logistic_regression"}}),
        encoding="utf-8",
    )
    (conf_dir / "confusion_matrix_logistic_regression.png").write_text("a", encoding="utf-8")
    (conf_dir / "confusion_matrix_random_forest.png").write_text("b", encoding="utf-8")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._handle_confusion_matrix_export()  # pylint: disable=protected-access

    assert result == 0
    assert not (run_root / "paper2_pack" / "confusion_matrix_primary.png").exists()


def test_handle_confusion_matrix_export_copies_single_model_matrix(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Confusion export should copy the only model matrix into paper2 pack."""
    out_root = tmp_path / "output"
    run_id = "20260305T111111Z__def456"
    diagnostics_dir = out_root / "diagnostics"
    run_root = out_root / "runs" / run_id
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id, "run_root": str(run_root)}),
        encoding="utf-8",
    )
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "model_summary": {"top_model": "logistic_regression"}}),
        encoding="utf-8",
    )
    source = conf_dir / "confusion_matrix_logistic_regression.png"
    source.write_text("matrix", encoding="utf-8")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._handle_confusion_matrix_export()  # pylint: disable=protected-access

    target = run_root / "paper2_pack" / "confusion_matrix_primary.png"
    assert result == 0
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "matrix"
