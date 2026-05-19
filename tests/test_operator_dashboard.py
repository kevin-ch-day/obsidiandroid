"""Focused tests for operator dashboard issue surfacing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.reporting import operator_dashboard


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
    assert "Taxonomy mismatch backlog present" in text
    assert "Taxonomy mismatches: total=377; claim-facing=0." in text


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
