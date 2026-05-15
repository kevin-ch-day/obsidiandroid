"""Tests for the Review Latest Run operator flow."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config

from obsidiandroid.cli import startup_menu_review


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_compact_review_summary_includes_identity_health_and_tuning(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    _write(rdiag / "run_science_index.md", "# run science\n")
    _write(rdiag / "cohort_foundation.json", "{}")
    _write(rdiag / "diagnostic_provenance.json", '{"entries":[]}')
    _write(rdiag / "cohort_funnel.md", "# funnel\n")
    _write(rdiag / "feature_set_ablation_summary.md", "# ablation\n")
    _write(rdiag / "figure_validity_audit.md", "# figure audit\n")
    _write(
        rdiag / f"taxonomy_consistency_summary_{run_id}.json",
        json.dumps(
            {
                "taxonomy_mismatch_count": 278,
                "type_mismatch_count": 100,
                "type_noncanonical_count": 150,
                "type_missing_label_count": 28,
                "family_label_mismatch_count": 0,
            }
        ),
    )
    _write(
        rdiag / "modality_contribution_summary.json",
        json.dumps({"permission_signal_pct": 97.31}),
    )
    _write(
        out_root / "diagnostics" / "run_manifest.latest.json",
        json.dumps(
            {
                "run_id": run_id,
                "profile_params": {"profile_id": "research_all_malicious"},
                "publication_ready_status": "NOT_APPLICABLE",
            }
        ),
    )
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    assert summary["run_id"] == run_id
    assert summary["profile_id"] == "research_all_malicious"
    assert summary["run_class"] == "Exploratory"
    assert summary["cohort_lock_status"] == "unlocked"
    assert summary["publication_ready_status"] == "Not applicable — exploratory run"
    labels = {str(row["label"]): str(row["status"]) for row in summary["health_rows"]}
    assert labels["Cohort / labels"] == "GREEN"
    assert labels["Taxonomy consistency"] == "YELLOW"
    assert labels["Ablation / signal contribution"] == "GREEN"
    assert labels["Figure validity"] == "GREEN"
    assert any("278 mismatches" in warning for warning in summary["warnings"])
    assert any("Next:" in warning for warning in summary["warnings"])
    assert str(summary["open_first"][0]["label"]) == "Run science index"
    assert any("Review taxonomy type authority report" in action for action in summary["tuning_actions"])


def test_compact_review_screen_avoids_debug_path_dump(monkeypatch, tmp_path: Path, capsys) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    _write(rdiag / "run_science_index.md", "# run science\n")
    _write(rdiag / "cohort_foundation.json", "{}")
    _write(rdiag / "diagnostic_provenance.json", '{"entries":[]}')
    _write(out_root / "diagnostics" / "run_manifest.latest.json", json.dumps({"run_id": run_id, "profile_params": {"profile_id": "research_all_malicious"}}))
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.delenv("OBSIDIANDROID_DISPLAY_MODE", raising=False)
    monkeypatch.setattr(app_config, "DEBUG_MODE", False, raising=False)

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "REVIEW LATEST RUN" in out
    assert "Run science index" in out
    assert "Publication-ready" in out
    assert "unknown" not in out.lower()
    assert "Detailed paths" not in out
    assert "diagnostics_dir" not in out


def test_detailed_review_screen_can_show_deeper_paths(monkeypatch, tmp_path: Path, capsys) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    _write(rdiag / "run_science_index.md", "# run science\n")
    _write(rdiag / "cohort_foundation.json", "{}")
    _write(rdiag / "diagnostic_provenance.json", '{"entries":[]}')
    _write(out_root / "diagnostics" / "run_manifest.latest.json", json.dumps({"run_id": run_id, "profile_params": {"profile_id": "research_all_malicious"}}))
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setenv("OBSIDIANDROID_DISPLAY_MODE", "detailed")

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Detailed paths" in out
    assert "diagnostics dir" in out.lower()


def test_run_history_remains_reachable_from_review_menu(monkeypatch) -> None:
    choices = iter([9, 1, 0, 0])
    calls = {"history": 0, "compare": 0}
    monkeypatch.setattr(startup_menu_review, "print_compact_review_latest_run", lambda **_: None)
    monkeypatch.setattr(
        startup_menu_review,
        "build_review_latest_run_summary",
        lambda **_: {
            "run_id": "r1",
            "profile_id": "p1",
            "run_class": "Exploratory",
            "cohort_lock_status": "unlocked",
            "publication_ready_status": "Not applicable — exploratory run",
            "health_rows": [],
            "warnings": [],
            "open_first": [],
            "tuning_actions": [],
        },
    )
    monkeypatch.setattr(startup_menu_review.mu, "display_menu", lambda *_args, **_kwargs: next(choices))

    startup_menu_review.launch_review_latest_run_menu(
        read_latest_run_id=lambda: "r1",
        open_run_science_index_action=lambda: 0,
        launch_cohort_family_audit_action=lambda: None,
        launch_parser_vendor_coverage_action=lambda: None,
        launch_permission_intelligence_coverage_action=lambda: None,
        launch_feature_matrix_modality_action=lambda: None,
        launch_taxonomy_consistency_review_action=lambda: None,
        launch_run_overview_action=lambda: calls.__setitem__("history", calls["history"] + 1),
        launch_compare_runs_action=lambda: calls.__setitem__("compare", calls["compare"] + 1),
        launch_data_diagnostics_action=lambda: None,
        launch_reproducibility_action=lambda: None,
    )

    assert calls["history"] == 1
    assert calls["compare"] == 0


def test_vendor_parser_workbook_gap_is_warning_not_red(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    _write(rdiag / "run_science_index.md", "# run science\n")
    _write(rdiag / "cohort_foundation.json", "{}")
    _write(rdiag / "diagnostic_provenance.json", '{"entries":[]}')
    _write(out_root / "diagnostics" / "run_manifest.latest.json", json.dumps({"run_id": run_id, "profile_params": {"profile_id": "research_all_malicious"}, "publication_ready_status": "NOT_APPLICABLE"}))
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {"publication_ready_status": "NOT_APPLICABLE"},
            "profile_id": "research_all_malicious",
            "evidence_mode": False,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {
                "csv_ready": True,
                "workbook_ready": False,
                "needs_attention": "Workbook drill-down unavailable",
                "unmapped_vendors": 70,
            },
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "GREEN"},
                {"label": "Permission signal", "status": "GREEN"},
                {"label": "Vendor/parser coverage", "status": "YELLOW"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )
    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)
    labels = {str(row["label"]): str(row["status"]) for row in summary["health_rows"]}
    assert labels["Vendor/parser"] == "YELLOW"


def test_tune_next_changes_with_status_flags(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    _write(rdiag / "run_science_index.md", "# run science\n")
    _write(rdiag / "cohort_foundation.json", "{}")
    _write(rdiag / "diagnostic_provenance.json", '{"entries":[]}')
    _write(out_root / "diagnostics" / "run_manifest.latest.json", json.dumps({"run_id": run_id, "profile_params": {"profile_id": "research_all_malicious"}, "publication_ready_status": "NOT_APPLICABLE"}))
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {"publication_ready_status": "NOT_APPLICABLE"},
            "profile_id": "research_all_malicious",
            "evidence_mode": False,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {"csv_ready": True, "workbook_ready": True, "unmapped_vendors": 0},
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "YELLOW"},
                {"label": "Permission signal", "status": "RED"},
                {"label": "Vendor/parser coverage", "status": "GREEN"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )
    _write(rdiag / f"taxonomy_consistency_summary_{run_id}.json", json.dumps({"taxonomy_mismatch_count": 5, "type_mismatch_count": 5, "type_noncanonical_count": 0, "type_missing_label_count": 0, "family_label_mismatch_count": 0}))
    _write(rdiag / "modality_contribution_summary.json", json.dumps({"permission_signal_pct": 45.0}))
    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)
    assert any("taxonomy type authority report" in action.lower() for action in summary["tuning_actions"])
    assert any("permission signal" in action.lower() for action in summary["tuning_actions"])
