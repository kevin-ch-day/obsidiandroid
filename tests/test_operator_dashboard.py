"""Focused tests for operator dashboard issue surfacing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.reporting import operator_dashboard


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
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
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
    assert "Taxonomy mismatch backlog present" in text
    assert "Taxonomy mismatches: total=377; claim-facing=0." in text


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
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
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
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
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
    assert "Skeptic audits" in text
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
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("obsidiandroid.cli.ui.display.print_subheader", lambda *_args, **_kwargs: None)

    def _fake_rq(**_kwargs):
        return {
            "_written_paths": [],
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

    captured: list[str] = []
    operator_dashboard.clear_operator_state()
    operator_dashboard.emit_research_operator_report(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_fast",
        manifest_context={"label_authority": {"active_training_classes": 30}},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        model_results={},
        top_model=None,
        artifact_list=[],
        print_fn=captured.append,
    )

    text = "\n".join(captured)
    assert "Train family models on family_id and coarse taxonomy on type_slug." in text
    assert "Label policy is explicit: train family on `family_id` and coarse taxonomy on `type_slug`." in text
    assert "Do not promote raw label surfaces such as `category_primary`" in text
    assert "Raw subtype aligns materially better than raw primary." in text
