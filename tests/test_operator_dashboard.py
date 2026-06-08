"""Focused tests for operator dashboard issue surfacing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from config import app_config
from obsidiandroid.reporting import operator_dashboard

pytestmark = pytest.mark.integration


def test_classification_report_family_insights_uses_label_name_map(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_labels"
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    (diagnostics_dir / f"label_name_map_{run_id}.json").write_text(
        json.dumps({"label_name_map": {"17": "Godfather", "44": "Irata"}}),
        encoding="utf-8",
    )

    got = operator_dashboard._classification_report_family_insights(  # pylint: disable=protected-access
        {
            "random_forest": {
                "metadata": {
                    "classification_report": {
                        "17": {"precision": 1.0, "recall": 0.5, "f1-score": 0.66, "support": 6},
                        "44": {"precision": 1.0, "recall": 1.0, "f1-score": 1.0, "support": 10},
                    }
                }
            }
        },
        "random_forest",
    )

    assert got["lowest_recall"][0][0] == "Godfather"


def test_emit_research_operator_report_surfaces_runtime_caveats(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """End-of-run ISSUES FOUND should reflect major runtime caveats, not claim none exist."""
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run1"
    (diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "taxonomy_mismatch_count": 377,
                "paper_facing_taxonomy_mismatch_count": 0,
                "mismatch_reason_counts": [
                    {"mismatch_reason": "type_mapping_conflict", "count": 310},
                    {"mismatch_reason": "missing_type_token", "count": 64},
                    {"mismatch_reason": "noncanonical_type_token", "count": 3},
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": []},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        operator_dashboard,
        "_read_run_taxonomy_summary",
        lambda _diagnostics_dir, _run_id: {
            "taxonomy_mismatch_count": 377,
            "paper_facing_taxonomy_mismatch_count": 0,
            "mismatch_reason_counts": [
                {"mismatch_reason": "type_mapping_conflict", "count": 310},
                {"mismatch_reason": "missing_type_token", "count": 64},
                {"mismatch_reason": "noncanonical_type_token", "count": 3},
            ],
        },
    )
    monkeypatch.setattr(
        operator_dashboard,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {},
            "taxonomy_signals": {
                "missing_primary_label_samples": 153,
                "unresolved_family_samples": 76,
                "policy_held_family_samples": 44,
                "family_type_conflict_count": 12,
                "high_priority_conflict_count": 9,
                "family_type_conflict_action_counts": {
                    "review_db_type_mapping": 7,
                    "add_db_family_mapping": 3,
                    "replace_unknown_db_type": 2,
                },
                "family_type_conflict_issue_counts": {
                    "type_mismatch": 7,
                    "db_family_missing": 3,
                    "type_unknown": 2,
                },
            },
        },
    )
    monkeypatch.setattr(
        operator_dashboard,
        "read_false_positive_triage_snapshot",
        lambda **_kwargs: {
            "row_count": 1,
            "freshness": "current",
            "top_lane": "real_malware_family_or_class_review",
            "top_lane_count": 1,
            "lane_counts": {"real_malware_family_or_class_review": 1},
        },
    )
    monkeypatch.setattr(
        operator_dashboard,
        "read_android_missing_resolution_snapshot",
        lambda **_kwargs: {
            "row_count": 3,
            "freshness": "current",
            "top_lane": "blank_package_review",
            "top_lane_count": 2,
            "lane_counts": {"blank_package_review": 2, "package_cluster_review": 1},
        },
    )
    captured: list[str] = []
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda title, *_args, **_kwargs: captured.append(str(title)))
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    operator_dashboard.clear_operator_state()
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SMOTE_WARNING_LAST",
        "Synthetic oversampling is enabled in evidence/paper mode.",
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_PROFILE_ID",
        "malicious_temporal_stability_locked",
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_LAST_SPLIT_ALGORITHM",
        "stratified_seeded",
        raising=False,
    )

    captured: list[str] = []
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="malicious_temporal_stability_locked",
        manifest_context={
            "paper_cohort_contract": {
                "validation": {"status": "degraded_live_db_drift"},
                "sample_id_lock": {
                    "runtime_db_drift": {
                        "lock_sample_count": 1226,
                        "matched_sample_count": 1187,
                        "missing_from_db_count": 39,
                    }
                },
            },
        },
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["fam_a", "fam_b"],
                "type_slug": ["banker", "banker"],
            }
        ),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "(No structured governance issues queued" not in text
    assert "Locked cohort drift downgraded to count-only semantics" in text
    assert "SMOTE remained enabled in evidence/publication mode" in text
    assert "Temporal profile used a non-temporal holdout policy" in text
    assert "stratified_seeded" in text
    assert "Taxonomy split issues present" in text
    assert "Family taxonomy curation discipline required" in text
    assert "Taxonomy mismatches: total=377; claim-facing=0." in text
    assert "policy-held generic/coarse token residue" in text
    assert "Taxonomy curation discipline: high-priority conflicts=9/12; dominant action=review_db_type_mapping (7); dominant issue=type_mismatch (7)." in text
    assert "Focus area: Android missing-resolution backlog (3 row(s))" in text
    assert "Source: live DB current-state view, not frozen run snapshot" in text
    assert "Focus detail: freshness=current; top_lane=blank_package_review" in text
    assert "Missing primary labels: 153" in text
    assert "Priority queue: True unresolved family debt" not in text
    assert "Priority queue: Android missing-resolution triage [freshness=current]" in text
    assert f"backlog_debt_summary_{run_id}.md" in text
    backlog_md = diagnostics_dir / f"backlog_debt_summary_{run_id}.md"
    assert backlog_md.is_file()
    backlog_text = backlog_md.read_text(encoding="utf-8")
    assert "**Source:** live DB current-state view, not frozen run snapshot" in backlog_text


def test_emit_research_operator_report_prints_compact_diagnostics_pointer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_diag_ptr"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": []},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(operator_dashboard, "_read_run_taxonomy_summary", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(operator_dashboard, "get_cohort_readiness_snapshot", lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {}})
    monkeypatch.setattr(operator_dashboard, "read_false_positive_triage_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(operator_dashboard, "read_android_missing_resolution_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.format_console_path",
        lambda path: (
            "obsidiandroid/output/runs/run_diag_ptr/diagnostics/index.md"
            if str(path).endswith("index.md")
            else "obsidiandroid/output/runs/run_diag_ptr"
        ),
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_RUN_ROOT",
        "/tmp/work/obsidiandroid/output/runs/run_diag_ptr",
        raising=False,
    )

    captured: list[str] = []
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_major_families",
        manifest_context={},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    assert "[Diagnostics] obsidiandroid/output/runs/run_diag_ptr/diagnostics/index.md" in captured
    assert "[Run] obsidiandroid/output/runs/run_diag_ptr" in captured


def test_emit_research_operator_report_surfaces_dl_seed_handoff_for_canonical_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_dl_seed"
    dataset_hash = "abc123deadbeefcafe00"
    for filename in (
        f"v3_label_contract_{run_id}.json",
        f"permission_pattern_contract_{run_id}.json",
        f"ml_sample_label_fact_{run_id}.csv",
        f"ml_permission_vocabulary_{run_id}.json",
    ):
        (diagnostics_dir / filename).write_text("{}" if filename.endswith(".json") else "sample_id\n1\n", encoding="utf-8")
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(
            {
                "dataset_hash": dataset_hash,
                "vocabulary_entry_count": 42,
                "sample_label_rows": 1,
                "seed_artifact_refs": {
                    "v3_label_contract": f"v3_label_contract_{run_id}.json",
                    "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
                    "ml_sample_label_fact": f"ml_sample_label_fact_{run_id}.csv",
                    "ml_permission_vocabulary": f"ml_permission_vocabulary_{run_id}.json",
                },
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"v3_dl_handoff_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "dl_seed_status": "ready",
                "dataset_hash": dataset_hash,
                "vocabulary_entry_count": 42,
                "sample_label_rows": 1,
                "missing_seed_refs": [],
                "caveats": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": []},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(operator_dashboard, "_read_run_taxonomy_summary", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(operator_dashboard, "get_cohort_readiness_snapshot", lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {}})
    monkeypatch.setattr(operator_dashboard, "read_false_positive_triage_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(operator_dashboard, "read_android_missing_resolution_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    captured: list[str] = []
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_major_families",
        manifest_context={"cohort_persistence_source": "runtime_frame", "dataset_hash": dataset_hash},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    joined = "\n".join(captured)
    assert "DL seed handoff                 : ready" in joined
    assert dataset_hash in joined
    assert "Cohort persistence source       : runtime_frame" in joined
    assert "ML permission vocabulary        : 42 entries" in joined
    assert f"v3_dl_handoff_summary_{run_id}.json" in joined


def test_emit_research_operator_report_surfaces_dl_seed_caveats_when_incomplete(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_dl_caveats"
    (diagnostics_dir / f"v3_dl_handoff_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "dl_seed_status": "incomplete",
                "dataset_hash": None,
                "vocabulary_entry_count": 0,
                "sample_label_rows": 0,
                "missing_seed_refs": ["ml_permission_vocabulary"],
                "caveats": ["dataset_hash missing", "ml_permission_vocabulary entry_count is zero"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": []},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(operator_dashboard, "_read_run_taxonomy_summary", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(operator_dashboard, "get_cohort_readiness_snapshot", lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {}})
    monkeypatch.setattr(operator_dashboard, "read_false_positive_triage_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(operator_dashboard, "read_android_missing_resolution_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    captured: list[str] = []
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_major_families",
        manifest_context={},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    joined = "\n".join(captured)
    assert "DL seed handoff                 : incomplete" in joined
    assert "DL seed caveats                 : dataset_hash missing" in joined


def test_emit_research_operator_report_flags_disabled_label_resolution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_label_off"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": [], "q1": {"label_strategy": {}}},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    captured: list[str] = []
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda title, *_args, **_kwargs: captured.append(str(title)))
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        manifest_context={"label_resolution_enabled": False},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Label resolution stage was disabled" in text
    assert "family/type guard telemetry were not exercised" in text
    assert "Type-guard suppressions: unavailable for this run because structured label resolution was disabled." in text


def test_emit_research_operator_report_surfaces_type_guard_suppression_count(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_type_guard"
    (diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "taxonomy_mismatch_count": 0,
                "paper_facing_taxonomy_mismatch_count": 0,
                "type_guard_family_suppressed_count": 4,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": [], "q1": {"label_strategy": {}}},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    captured: list[str] = []
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda title, *_args, **_kwargs: captured.append(str(title)))
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    captured: list[str] = []
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        manifest_context={"label_resolution_enabled": True},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Type-guard suppressions: 4 structured family prediction(s) were demoted for cross-type incompatibility." in text
    assert "Type guard suppressed cross-type family predictions" in text
    assert "demoted 4 known-family prediction(s)" in text


def test_queue_runtime_operator_issues_surfaces_taxonomy_label_drift(tmp_path: Path) -> None:
    """Taxonomy-only drift should be an operator issue without implying sample membership loss."""
    operator_dashboard.clear_operator_state()
    operator_dashboard._queue_runtime_operator_issues(  # pylint: disable=protected-access
        diagnostics_dir=tmp_path,
        manifest_context={
            "paper_cohort_contract": {
                "validation": {"status": "degraded_taxonomy_label_drift"},
                "sample_id_lock": {
                    "taxonomy_label_drift": {
                        "matched_sample_count": 1187,
                        "expected_family_count": 35,
                        "observed_family_count": 40,
                        "expected_type_count": 3,
                        "observed_type_count": 4,
                        "family_delta": 5,
                        "type_delta": 1,
                        "drift_class": "taxonomy_expansion",
                        "recommended_action": "Review newly split families/types inside the locked sample set.",
                    }
                },
            }
        },
    )

    issues = getattr(app_config, "RUNTIME_OPERATOR_ISSUES", [])
    assert issues
    text = "\n".join(str(line) for issue in issues for line in [issue["title"], *issue["lines"]])
    assert "Locked cohort membership preserved but taxonomy labels drifted" in text
    assert "families 40 vs expected 35" in text
    assert "types 4 vs expected 3" in text
    assert "Taxonomy drift class=taxonomy_expansion" in text
    assert "family_delta=+5" in text
    assert "sample-id membership" in text


def test_emit_research_operator_report_flags_temporal_holdout_future_only_drop(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "taxonomy_consistency_summary_run.json").write_text(
        json.dumps({"taxonomy_mismatch_count": 0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.operator_dashboard.oh.resolve_taxonomy_consistency_summary_path",
        lambda _diagnostics_dir, _run_id: diagnostics_dir / "taxonomy_consistency_summary_run.json",
    )
    monkeypatch.setattr(app_config, "RUNTIME_PROFILE_ID", "malicious_temporal_stability_locked", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", "temporal_year_holdout_v1", raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TEMPORAL_SPLIT_SUMMARY",
        {
            "test_year_floor": 2024,
            "observed_year_min": 2020,
            "observed_year_max": 2025,
            "test_rows_dropped_unseen_train_classes": 219,
        },
        raising=False,
    )

    captured: list[str] = []
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id="run",
        profile_id="malicious_temporal_stability_locked",
        manifest_context={},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["A"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Temporal holdout excluded future-only family rows" in text
    assert "Dropped 219 newer-row sample(s)" in text


def test_clear_operator_state_resets_stale_smote_runtime_state(monkeypatch) -> None:
    """New runs should not inherit SMOTE warning/audit state from earlier runs."""
    monkeypatch.setattr(app_config, "RUNTIME_OPERATOR_ISSUES", [{"tag": "X"}], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", {"diag": 2}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "stale warning", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SMOTE_AUDIT_LAST", {"rows_after": 10}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SMOTE_AUDIT_BY_MODEL", {"rf": {"rows_after": 10}}, raising=False)

    operator_dashboard.clear_operator_state()

    assert getattr(app_config, "RUNTIME_OPERATOR_ISSUES", None) == []
    assert getattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", None) == {}
    assert getattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", None) == ""
    assert getattr(app_config, "RUNTIME_SMOTE_AUDIT_LAST", "sentinel") is None
    assert getattr(app_config, "RUNTIME_SMOTE_AUDIT_BY_MODEL", None) == {}
    assert getattr(app_config, "RUNTIME_TEMPORAL_SPLIT_SUMMARY", "sentinel") is None


def test_emit_research_operator_report_uses_global_feature_survival_mirror(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    """Operator summary should still find feature-column survival after local `.latest` pruning."""
    output_root, diagnostics_dir, global_diag = make_run_diagnostics_layout("run2")
    (global_diag / "feature_column_survival.latest.csv").write_text(
        "feature_name,nonzero_count_final_training\n"
        "perm__android_CAMERA,9\n"
        "perm__android_SMS,7\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": []},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    captured: list[str] = []
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda title, *_args, **_kwargs: captured.append(str(title)))
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    captured: list[str] = []
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id="run2",
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["fam_a", "fam_a"],
                "type_slug": ["banker", "banker"],
            }
        ),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Top permission columns by training nonzero: perm__android_CAMERA(9), perm__android_SMS(7)" in text


def test_emit_research_operator_report_uses_compact_artifact_pointer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_art"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": []},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    captured: list[str] = []
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda title, *_args, **_kwargs: captured.append(str(title)))
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    captured: list[str] = []
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Start here" in text
    assert "Operator debt" in text
    assert "Skeptic audits" in text
    assert f"backlog_debt_summary_{run_id}.md" in text
    assert "Grouped artifact writes (estimated)" not in text
    assert f"headline_vs_ablation_contract_comparison_{run_id}.md" not in text


def test_emit_research_operator_report_surfaces_label_strategy_guidance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_labels"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    captured: list[str] = []
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_section",
        lambda title, *_args, **_kwargs: captured.append(str(title)),
    )
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_stat",
        lambda key, value, *_args, **_kwargs: captured.append(f"{key}: {value}"),
    )

    def _fake_rq(**_kwargs):
        return {
            "_written_paths": [],
            "benchmark_support_floor": 3,
            "benchmark_support_excluded_sample_count": 2,
            "benchmark_support_excluded_family_count": 2,
            "q1": {
                "governed_samples": 317,
                "aligned_supervised_samples": 317,
                "trainable_after_support_filter": 301,
                "families_represented": 42,
                "malware_types_represented": 6,
                "concentration": {
                    "top_family": "SpyNote",
                    "top_family_count": 44,
                    "top_family_share_pct": 13.88,
                    "top3_share_pct": 31.0,
                    "top5_share_pct": 46.0,
                },
                "quality_gates": {},
                "supervised_family_claims_suitable": False,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                    "avoid_for_primary_claims": ["category_primary"],
                    "alignment_interpretation": "Raw subtype aligns materially better than raw primary.",
                },
            },
            "q2": {},
            "q3": {},
            "concentration_warn": False,
        }

    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        _fake_rq,
    )

    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]})
    samples_df.attrs["support_floor_mode"] = "benchmark_eligibility"
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_fast",
        manifest_context={"label_authority": {"active_training_classes": 30}},
        samples_df=samples_df,
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "BENCHMARK CLAIM READINESS" in text
    assert "Claim status" in text
    assert "Claim surface" in text
    assert "Support-gated benchmark cohort" in text
    assert "Benchmark support rule          : n >= 3 per family" in text
    assert "SUPPORTED CLAIMS" in text
    assert "NOT SUPPORTED BY THIS RUN" in text
    assert "Family classification can be reported on the support-gated benchmark surface." in text
    assert "Family/type targets are governed: `family_id` for family claims, `type_slug` for type claims." in text
    assert "Avoid primary scientific claims on raw surfaces: category_primary." in text
    assert "Details                         : diagnostics/benchmark_claim_audit.md" in text
    claim_path = diagnostics_dir / f"claim_readiness_summary_{run_id}.json"
    assert claim_path.is_file()
    payload = json.loads(claim_path.read_text(encoding="utf-8"))
    assert payload["primary_surface"] == "major_family_benchmark"
    assert payload["benchmark_family_support_floor"] == 3
    assert payload["family_claim_surface"] == "family_id"
    assert payload["type_claim_surface"] == "type_slug"
    assert payload["details_artifact"] == "benchmark_claim_audit.md"
    assert payload["supported_claims"]
    assert payload["unsupported_claims"]


def test_emit_research_operator_report_marks_all_current_as_diagnostic_surface(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_all_current"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {
            "_written_paths": [],
            "benchmark_support_floor": 3,
            "benchmark_support_excluded_sample_count": 0,
            "benchmark_support_excluded_family_count": 1,
            "q1": {
                "governed_samples": 3644,
                "aligned_supervised_samples": 3433,
                "trainable_after_support_filter": 3433,
                "families_represented": 115,
                "malware_types_represented": 6,
                "concentration": {
                    "top_family": "BankBot",
                    "top_family_count": 2400,
                    "top_family_share_pct": 69.98,
                    "top3_share_pct": 82.0,
                    "top5_share_pct": 89.0,
                },
                "quality_gates": {},
                "supervised_family_claims_suitable": False,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                },
            },
            "q2": {},
            "q3": {},
            "concentration_warn": True,
        },
    )

    captured: list[str] = []
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_section",
        lambda title, *_args, **_kwargs: captured.append(str(title)),
    )
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_stat",
        lambda key, value, *_args, **_kwargs: captured.append(f"{key}: {value}"),
    )

    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]})
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_all_current",
        manifest_context={"label_authority": {"active_training_classes": 114}},
        samples_df=samples_df,
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "RESEARCH CLAIM READINESS" in text
    assert "Current-corpus diagnostic surface" in text
    assert "This run describes current governed Android malware corpus health." in text
    assert "Family/type models are diagnostic because the current corpus is concentration-heavy." in text
    assert "Visible governed families       : 115" in text
    assert "Modeled family classes          : 115" in text
    assert "Excluded / non-claim families   : 1" in text
    assert "Use benchmark profiles for stronger family-classification claims." in text
    assert "NOT SUPPORTED BY THIS RUN" in text
    assert "research_claim_audit.md" in text


def test_emit_research_operator_report_uses_publication_heading_for_locked_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_locked_pub"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {
            "_written_paths": [],
            "benchmark_support_floor": 20,
            "benchmark_support_excluded_sample_count": 0,
            "benchmark_support_excluded_family_count": 0,
            "q1": {
                "families_represented": 39,
                "supervised_family_claims_suitable": True,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                },
            },
            "q2": {},
            "q3": {},
        },
    )

    captured: list[str] = []
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_section",
        lambda title, *_args, **_kwargs: captured.append(str(title)),
    )

    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]})
    samples_df.attrs["support_floor_mode"] = "benchmark_eligibility"
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="malicious_temporal_stability_locked",
        manifest_context={
            "publication_ready_mode": True,
            "evidence_mode": True,
            "label_authority": {"active_training_classes": 39},
        },
        samples_df=samples_df,
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "PUBLICATION CLAIM READINESS" in text
    assert "Locked publication cohort" in text
    assert "diagnostics/publication_claim_audit.md" in text


def test_emit_research_operator_report_major_family_benchmark_does_not_use_publication_heading(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_major_benchmark"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {
            "_written_paths": [],
            "benchmark_support_floor": 20,
            "benchmark_support_excluded_sample_count": 14,
            "benchmark_support_excluded_family_count": 2,
            "q1": {
                "families_represented": 36,
                "supervised_family_claims_suitable": True,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                },
            },
            "q2": {},
            "q3": {},
        },
    )

    captured: list[str] = []
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_section",
        lambda title, *_args, **_kwargs: captured.append(str(title)),
    )

    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]})
    samples_df.attrs["support_floor_mode"] = "benchmark_eligibility"
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_major_families",
        manifest_context={
            "publication_ready_mode": True,
            "evidence_mode": False,
            "paper_mode": False,
            "run_mode": "benchmark",
            "label_authority": {"active_training_classes": 34},
        },
        samples_df=samples_df,
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "BENCHMARK CLAIM READINESS" in text
    assert "Support-gated benchmark cohort" in text
    assert "Family classification can be reported on the support-gated benchmark surface." in text
    assert "PUBLICATION CLAIM READINESS" not in text
    assert "Locked publication cohort" not in text
    assert "diagnostics/benchmark_claim_audit.md" in text


def test_emit_research_operator_report_uses_benchmark_heading_for_type_taxonomy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_type_tax"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {
            "_written_paths": [],
            "q1": {
                "families_represented": 20,
                "supervised_family_claims_suitable": True,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                },
            },
            "q2": {},
            "q3": {},
        },
    )

    captured: list[str] = []
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_section",
        lambda title, *_args, **_kwargs: captured.append(str(title)),
    )

    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]})
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_type_taxonomy",
        manifest_context={},
        samples_df=samples_df,
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "BENCHMARK CLAIM READINESS" in text
    assert "Type taxonomy benchmark" in text
    assert "diagnostics/benchmark_claim_audit.md" in text


def test_emit_research_operator_report_marks_expanded_families_as_exploratory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_expanded_exploratory"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {
            "_written_paths": [],
            "benchmark_support_floor": 3,
            "q1": {
                "families_represented": 48,
                "supervised_family_claims_suitable": False,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                },
            },
            "q2": {},
            "q3": {},
        },
    )

    captured: list[str] = []
    monkeypatch.setattr(
        "obsidiandroid.cli.ui.display.print_section",
        lambda title, *_args, **_kwargs: captured.append(str(title)),
    )

    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]})
    samples_df.attrs["support_floor_mode"] = "benchmark_eligibility"
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_expanded_families",
        manifest_context={},
        samples_df=samples_df,
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "RESEARCH CLAIM READINESS" in text
    assert "Expanded-family exploratory cohort" in text
    assert "diagnostics/research_claim_audit.md" in text


def test_emit_research_operator_report_preserves_claim_readiness_line_breaks(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_pub_render"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_authority_split_reports",
        lambda *_args, **_kwargs: (None, None, None, None, None),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {
            "_written_paths": [],
            "benchmark_support_floor": 20,
            "benchmark_support_excluded_sample_count": 2,
            "benchmark_support_excluded_family_count": 2,
            "q1": {
                "families_represented": 36,
                "supervised_family_claims_suitable": True,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                },
            },
            "q2": {},
            "q3": {},
        },
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.ml_tuning_recommendations.write_ml_tuning_recommendations",
        lambda **_kwargs: (
            diagnostics_dir / f"ml_tuning_recommendations_{run_id}.md",
            diagnostics_dir / f"ml_tuning_recommendations_{run_id}.csv",
            diagnostics_dir / f"ml_tuning_recommendations_{run_id}.json",
            {"recommendations": []},
        ),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.data_problem_quantification.write_data_problem_quantification",
        lambda **_kwargs: (
            diagnostics_dir / f"data_problem_quantification_{run_id}.md",
            diagnostics_dir / f"data_problem_quantification_{run_id}.csv",
            diagnostics_dir / f"data_problem_quantification_{run_id}.json",
            {},
        ),
    )

    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]})
    samples_df.attrs["support_floor_mode"] = "benchmark_eligibility"
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="malicious_temporal_stability_locked",
        manifest_context={
            "publication_ready_mode": True,
            "evidence_mode": True,
            "label_authority": {"active_training_classes": 34},
        },
        samples_df=samples_df,
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=None,
    )

    out = capsys.readouterr().out
    assert "PUBLICATION CLAIM READINESS" in out
    assert "\nSUPPORTED CLAIMS\n" in out
    assert "\nCLAIM LIMITS\n" in out
    assert "\nNOT SUPPORTED BY THIS RUN\n" in out
    assert "\nNEXT REVIEW\n" in out
    assert "\nDetails                         : diagnostics/publication_claim_audit.md\n" in out
    assert "[INFO] Claim status" not in out
    assert "Claim status                    :" in out
    assert "Claim surface                   : Locked publication cohort" in out
    assert "Claim status                    :" in out.split("SUPPORTED CLAIMS", maxsplit=1)[0]
    assert "SUPPORTED CLAIMS" not in next(
        line for line in out.splitlines() if "Claim status                    :" in line
    )


def test_emit_research_operator_report_surfaces_support_threshold_tracks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_support_tracks"

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_authority_split_reports",
        lambda *_args, **_kwargs: (None, None, None, None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        lambda **_kwargs: {"_written_paths": [], "q1": {}, "q2": {}, "q3": {}},
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.ml_tuning_recommendations.write_ml_tuning_recommendations",
        lambda **_kwargs: (
            diagnostics_dir / f"ml_tuning_recommendations_{run_id}.md",
            diagnostics_dir / f"ml_tuning_recommendations_{run_id}.csv",
            diagnostics_dir / f"ml_tuning_recommendations_{run_id}.json",
            {"recommendations": []},
        ),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.data_problem_quantification.write_data_problem_quantification",
        lambda **_kwargs: (
            diagnostics_dir / f"data_problem_quantification_{run_id}.md",
            diagnostics_dir / f"data_problem_quantification_{run_id}.csv",
            diagnostics_dir / f"data_problem_quantification_{run_id}.json",
            {
                "priority_score": {"composite_problem_score_0_100": 72.5},
                "support_gap": {
                    "families_with_gap_le_5": 1,
                    "samples_needed_to_make_all_families_trainable": 96,
                },
                "support_threshold_curve": {
                    "threshold_20": {
                        "threshold": 20,
                        "trainable_classes": 17,
                        "retained_rows": 957,
                        "dropped_rows": 230,
                    },
                    "recommended_exploratory_threshold": {
                        "threshold": 10,
                        "trainable_classes": 31,
                        "retained_rows": 1168,
                        "dropped_rows": 19,
                    },
                },
                "training_policy_recommendations": {
                    "tracks": [
                        {
                            "track": "exploratory_expanded_class_threshold",
                            "recommended_action": "Run this as a separate exploratory track.",
                        }
                    ]
                },
                "issue_flags": [
                    {
                        "severity": "medium",
                        "issue": "dual_support_threshold_track",
                        "value": 10,
                        "threshold": "retains >=90%",
                        "recommended_action": "Keep threshold 20 for evidence claims.",
                    }
                ],
            },
        ),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "_build_reporting_backlog_summary",
        lambda **_kwargs: ({}, None, None, {}),
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)

    captured: list[str] = []
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_fast",
        manifest_context={},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Conservative support track: threshold=20 classes=17 retained=957 dropped=230." in text
    assert "Exploratory expanded-class track: threshold=10 classes=31 retained=1168 dropped=19" in text
    assert "Training policy `exploratory_expanded_class_threshold`" in text


def test_write_diagnostics_index_surfaces_backlog_section(tmp_path: Path) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_idx"
    for name in (
        f"backlog_debt_summary_{run_id}.md",
        "android_missing_resolution_triage_latest.csv",
        "android_missing_resolution_vt_tail_latest.csv",
        "missing_primary_label_triage_latest.csv",
        "blank_resolved_family_triage_latest.csv",
        "blank_resolved_singleton_provenance_latest.csv",
        "profile_family_mapping_debt_latest.csv",
        "vt_false_positive_review_triage_latest.csv",
        "android_policy_held_token_risk_latest.csv",
        "vendor_verdict_debt_summary_latest.csv",
    ):
        (diagnostics_dir / name).write_text("placeholder\n", encoding="utf-8")

    out_path = operator_dashboard.write_diagnostics_index_md(
        diagnostics_dir,
        run_id=run_id,
        artifact_list=[str(diagnostics_dir / f"backlog_debt_summary_{run_id}.md")],
    )

    assert out_path is not None
    text = out_path.read_text(encoding="utf-8")
    assert "Backlog and review queues" in text
    assert f"`backlog_debt_summary_{run_id}.md`" in text
    assert "`android_missing_resolution_triage_latest.csv`" in text
    assert "`android_missing_resolution_vt_tail_latest.csv`" in text
    assert "`missing_primary_label_triage_latest.csv`" in text
    assert "`blank_resolved_family_triage_latest.csv`" in text
    assert "`blank_resolved_singleton_provenance_latest.csv`" in text
    assert "`profile_family_mapping_debt_latest.csv`" in text
    assert "`vt_false_positive_review_triage_latest.csv`" in text
    assert "`android_policy_held_token_risk_latest.csv`" in text
    assert "`vendor_verdict_debt_summary_latest.csv`" in text


def test_emit_research_operator_report_downgrades_claim_readiness_for_weak_family_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_claims"
    (diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps({"taxonomy_mismatch_count": 0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_headline_vs_ablation_contract_reports",
        lambda **_kwargs: (None, None, {}),
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.contract_and_taxonomy_reports.write_taxonomy_type_authority_reports",
        lambda *_args, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.print_research_questions_terminal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        operator_dashboard,
        "write_diagnostics_index_md",
        lambda *_args, **_kwargs: diagnostics_dir / "index.md",
    )
    monkeypatch.setattr(
        operator_dashboard,
        "_read_run_taxonomy_summary",
        lambda _diagnostics_dir, _run_id: {"taxonomy_mismatch_count": 0},
    )
    monkeypatch.setattr(
        operator_dashboard,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {}},
    )
    monkeypatch.setattr(
        operator_dashboard,
        "read_false_positive_triage_snapshot",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        operator_dashboard,
        "read_android_missing_resolution_snapshot",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)
    def _fake_rq(**_kwargs):
        return {
            "_written_paths": [],
            "macro_f1": 0.3261,
            "wf1": 0.5890,
            "q1": {
                "supervised_family_claims_suitable": False,
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                },
            },
        }

    monkeypatch.setattr(
        "obsidiandroid.reporting.research_three_questions.write_research_question_artifacts",
        _fake_rq,
    )

    captured: list[str] = []
    operator_dashboard.clear_operator_state()
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TEMPORAL_SPLIT_SUMMARY",
        {"test_rows_dropped_unseen_train_classes": 219},
        raising=False,
    )
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="malicious_temporal_stability_locked",
        manifest_context={"label_authority": {"active_training_classes": 18}},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Claim status                    : LIMITED" in text
    assert "headline family Macro-F1 is weak (0.3261)." in text
    assert "dataset foundation does not mark supervised family claims as suitable." in text
    assert "temporal holdout dropped 219 future-only family row(s)." in text
    assert "Claim status                    : STRONG" not in text
    assert "Claim status                    : STRONG_WITH_CAUTIONS" not in text


def test_claim_readiness_context_resolves_evidence_mode_metadata_dict() -> None:
    """Non-empty evidence_mode dicts must not imply publication-active when resolved_value is false."""
    manifest_context = {
        "evidence_mode": {
            "resolved_value": False,
            "source": "profile",
            "raw_inputs": {"profile": False},
        },
        "paper_mode": {
            "resolved_value": False,
            "source": "profile",
            "raw_inputs": {"profile": False},
        },
    }
    title, surface = operator_dashboard._claim_readiness_context(  # pylint: disable=protected-access
        profile_id="android_malware_all_current",
        manifest_context=manifest_context,
        samples_df=None,
    )
    assert title == "RESEARCH CLAIM READINESS"
    assert surface == "broad_current_corpus"


def test_publication_mode_active_treats_resolved_false_metadata_as_off() -> None:
    manifest_context = {
        "evidence_mode": {"resolved_value": False, "source": "profile"},
        "paper_mode": {"resolved_value": False, "source": "profile"},
    }
    assert operator_dashboard._publication_mode_active(manifest_context) is False  # pylint: disable=protected-access
