"""Tests for research summary modality fallbacks and notes."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.reporting import research_three_questions as rtq


def test_modality_summary_falls_back_to_runtime_engine_counts_and_notes_raw_permissions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Q2 summary should avoid misleading 0/0 engine counts and explain disabled permission fusion."""
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 10,
                "family_type_summary": {
                    "family_count": 2,
                    "type_count": 1,
                    "top_family": "fam_a",
                    "top_family_count": 6,
                    "top_family_share_pct": 60.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"fam_a": 6, "fam_b": 4},
                    "type_distribution": {"banker": 10},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_modality_coverage_summary_run1.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "permission_pi_signal_positive_n": 0,
                "vendor_merge_n": 10,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "modality_method_contract.json").write_text(
        json.dumps(
            {
                "fusion_modality": {"feature_count_permission": 0},
                "permission_modality": {"feature_count_raw": 0},
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "permission_signal_quality.csv").write_text(
        "metric,value,notes\nsamples_with_any_permission_observation,9,\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_INCLUDED_AFTER_GATING", 7, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_EXCLUDED_AFTER_GATING", 3, raising=False)

    bundle = rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id="run1",
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame({"sample_id": list(range(1, 11)), "family_canonical": ["fam_a"] * 6 + ["fam_b"] * 4, "type_slug": ["banker"] * 10}),
        model_results={},
        top_model=None,
    )

    q2 = bundle["q2"]
    assert q2["av_engines_included"] == 7
    assert q2["av_engines_observed"] == 10
    assert any("permission features were disabled" in note for note in q2["interpretation_notes"])

    summary_payload = json.loads((diagnostics_dir / "modality_contribution_summary.json").read_text(encoding="utf-8"))
    assert summary_payload["av_engines_included"] == 7
    assert summary_payload["av_engines_observed"] == 10


def test_dataset_foundation_summary_emits_compatibility_fields(
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_foundation"

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 317,
                "cohort_sql_scope_row_count": 3065,
                "cohort_attrition": {"governed_sql_total": 2621},
                "family_type_summary": {
                    "family_count": 42,
                    "type_count": 6,
                    "top_family": "SpyNote",
                    "top_family_count": 44,
                    "top_family_share_pct": 13.88,
                    "top3_share_pct": 31.0,
                    "top5_share_pct": 46.0,
                    "family_distribution": {"SpyNote": 44, "Gigabud": 33},
                    "type_distribution": {"banker": 139, "rat": 83},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                    "governed_cohort_count_sql": 2621,
                    "total_candidates": 3065,
                },
                "catalog_semantics_summary": {
                    "vt_family_token_rows": 205,
                    "raw_family_vs_canonical_conflict_rows": 0,
                    "weak_label_with_canonical_family_rows": 0,
                },
                "missing_package_rate_pct": 5.36,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json").write_text(
        json.dumps(
            {
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_family_reporting_surface": "family_canonical",
                    "preferred_type_target": "type_slug",
                    "preferred_hierarchical_target": "family_within_type",
                    "auxiliary_audit_surfaces": ["category_subtype", "category_primary_subtype"],
                    "avoid_for_primary_claims": ["category_primary"],
                    "alignment_interpretation": "Raw subtype aligns materially better than raw primary.",
                },
                "alignment": {
                    "subtype_exact_type_match_pct": 69.72,
                    "primary_exact_type_match_pct": 4.10,
                    "inferred_type_match_pct": 70.03,
                }
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"feature_modality_coverage_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "permission_pi_signal_positive_n": 300,
                "vendor_merge_n": 317,
                "permission_feature_columns_in_fused_matrix": 223,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_contract.json").write_text(
        json.dumps({"engine_included_count": 56, "engine_excluded_count": 37}),
        encoding="utf-8",
    )
    (diagnostics_dir / "permission_signal_quality.csv").write_text(
        "metric,value,notes\nsamples_with_any_permission_observation,300,\n",
        encoding="utf-8",
    )

    rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_fast",
        manifest_context={"governed_cohort_rows": 317},
        samples_df=pd.DataFrame({"sample_id": [1, 2], "family_canonical": ["SpyNote", "Gigabud"], "type_slug": ["rat", "banker"]}),
        model_results={},
        top_model=None,
    )

    payload = json.loads((diagnostics_dir / "dataset_foundation_summary.json").read_text(encoding="utf-8"))
    assert payload["final_samples"] == 317
    assert payload["sql_profile_scope"] == 3065
    assert payload["sql_governed_cohort"] == 2621
    assert payload["unique_families"] == 42
    assert payload["represented_types"] == 6
    assert payload["type_distribution"] == {"banker": 139, "rat": 83}
    assert payload["rows_with_vt_family_token"] == 205
    assert payload["raw_to_type_alignment"]["subtype_exact_pct"] == 69.72
    assert payload["weak_labels_with_canonical_family"] == 0
    assert payload["label_strategy"]["preferred_family_target"] == "family_id"
    assert payload["label_strategy"]["preferred_type_target"] == "type_slug"
    assert payload["label_strategy"]["avoid_for_primary_claims"] == ["category_primary"]
    md_text = (diagnostics_dir / "dataset_foundation_summary.md").read_text(encoding="utf-8")
    assert "Preferred family supervision target" in md_text
    assert "Preferred coarse type target" in md_text


def test_modality_summary_computes_raw_permission_fallback_without_csv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Q2 summary should infer raw permission coverage even before hostile-audit CSV exists."""
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 4,
                "family_type_summary": {
                    "family_count": 2,
                    "type_count": 1,
                    "top_family": "fam_a",
                    "top_family_count": 2,
                    "top_family_share_pct": 50.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"fam_a": 2, "fam_b": 2},
                    "type_distribution": {"banker": 4},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_modality_coverage_summary_run2.json").write_text(
        json.dumps(
            {
                "run_id": "run2",
                "permission_pi_signal_positive_n": 0,
                "vendor_merge_n": 4,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "modality_method_contract.json").write_text(
        json.dumps(
            {
                "fusion_modality": {"feature_count_permission": 0},
                "permission_modality": {"feature_count_raw": 0},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(rtq, "_raw_permission_observation_count", lambda _samples_df: 3)

    bundle = rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id="run2",
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2, 3, 4],
                "family_canonical": ["fam_a", "fam_a", "fam_b", "fam_b"],
                "type_slug": ["banker"] * 4,
            }
        ),
        model_results={},
        top_model=None,
    )

    q2 = bundle["q2"]
    assert q2["permission_raw_observation_n"] == 3
    assert any("Raw permission observations exist in the DB" in note for note in q2["interpretation_notes"])


def test_write_research_question_artifacts_ignores_global_latest_ablation_when_current_run_has_none(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_no_ablation"

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 4,
                "family_type_summary": {
                    "family_count": 2,
                    "type_count": 1,
                    "top_family": "fam_a",
                    "top_family_count": 2,
                    "top_family_share_pct": 50.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"fam_a": 2, "fam_b": 2},
                    "type_distribution": {"banker": 4},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"feature_modality_coverage_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "permission_pi_signal_positive_n": 0,
                "vendor_merge_n": 4,
            }
        ),
        encoding="utf-8",
    )

    global_diag = tmp_path / "global_diagnostics"
    global_diag.mkdir(parents=True, exist_ok=True)
    (global_diag / "ablation_summary.latest.csv").write_text(
        "\n".join(
            [
                "experiment,label_target,model,macro_f1_score,accuracy,weighted_f1_score,delta_vs_full_fused",
                "full_fused,family_id,random_forest,0.91,0.92,0.93,0.0",
                "permissions_grouped,family_id,logistic_regression,0.81,0.82,0.83,-0.10",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(oh, "global_diagnostics_root", lambda: global_diag)

    bundle = rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2, 3, 4],
                "family_canonical": ["fam_a", "fam_a", "fam_b", "fam_b"],
                "type_slug": ["banker"] * 4,
            }
        ),
        model_results={},
        top_model=None,
    )

    assert bundle["ablation_display"].empty
    assert any("Ablation summary missing or empty" in note for note in bundle["interpret_q2"])
    ablation_summary = pd.read_csv(diagnostics_dir / "feature_set_ablation_summary.csv")
    assert set(ablation_summary.columns) == {"status", "run_id"}
    assert ablation_summary.iloc[0]["status"] == "ablation_summary_unavailable_or_empty"


def test_write_research_question_artifacts_exports_family_names_not_numeric_ids(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_labels"
    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 2,
                "family_type_summary": {
                    "family_count": 2,
                    "type_count": 1,
                    "top_family": "Godfather",
                    "top_family_count": 1,
                    "top_family_share_pct": 50.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"Godfather": 1, "Irata": 1},
                    "type_distribution": {"banker": 2},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"label_name_map_{run_id}.json").write_text(
        json.dumps({"label_name_map": {"17": "Godfather", "44": "Irata"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_DIAGNOSTICS_DIR",
        str(diagnostics_dir),
        raising=False,
    )
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    bundle = rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["Godfather", "Irata"],
                "family_id": [17, 44],
                "type_slug": ["banker", "banker"],
            }
        ),
        model_results={
            "random_forest": {
                "label_name_map": {"17": "Godfather", "44": "Irata"},
                "metadata": {
                    "classification_report": {
                        "17": {"precision": 1.0, "recall": 0.5, "f1-score": 0.66, "support": 1},
                        "44": {"precision": 1.0, "recall": 1.0, "f1-score": 1.0, "support": 1},
                    }
                },
                "evaluation": {
                    "macro_f1_score": 0.83,
                    "f1_score": 0.9,
                    "accuracy": 0.9,
                },
            }
        },
        top_model="random_forest",
    )

    family_rows = pd.read_csv(diagnostics_dir / "lowest_recall_families.csv").to_dict(orient="records")
    assert family_rows[0]["family"] == "Godfather"
    assert bundle["q3"]["headline_model"] == "random_forest"
    confusion_rows = pd.read_csv(diagnostics_dir / "top_confusion_pairs.csv").to_dict(orient="records")
    assert confusion_rows == [{"note": "insufficient_model_state"}]


def test_write_research_question_artifacts_writes_top_confusion_pairs_without_skeptic_audits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = "run_conf"
    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 2,
                "family_type_summary": {
                    "family_count": 2,
                    "type_count": 1,
                    "top_family": "Godfather",
                    "top_family_count": 1,
                    "top_family_share_pct": 50.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"Godfather": 1, "Irata": 1},
                    "type_distribution": {"banker": 2},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"label_name_map_{run_id}.json").write_text(
        json.dumps({"label_name_map": {"17": "Godfather", "44": "Irata"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["Godfather", "Irata"],
                "family_id": [17, 44],
                "type_slug": ["banker", "banker"],
            }
        ),
        model_results={
            "random_forest": {
                "label_name_map": {"17": "Godfather", "44": "Irata"},
                "metadata": {"classification_report": {}},
                "evaluation": {
                    "macro_f1_score": 0.83,
                    "f1_score": 0.9,
                    "accuracy": 0.9,
                    "confusion_matrix": [[0, 1], [0, 1]],
                    "class_labels": ["17", "44"],
                },
            }
        },
        top_model="random_forest",
    )

    confusion_rows = pd.read_csv(diagnostics_dir / "top_confusion_pairs.csv").to_dict(orient="records")
    assert confusion_rows[0]["true_family"] == "Godfather"
    assert confusion_rows[0]["predicted_family"] == "Irata"
    assert int(confusion_rows[0]["count"]) == 1
    assert confusion_rows[0]["shared_type"] == "yes"


def test_print_research_questions_terminal_labels_vendor_merge_coverage_honestly() -> None:
    """Run summary should not describe 100% vendor-merge coverage as sparse."""
    captured: list[str] = []

    class _DummyDisplay:
        @staticmethod
        def print_section(_title: str) -> None:
            return None

        @staticmethod
        def print_table(*_args, **_kwargs) -> None:
            return None

    rtq.print_research_questions_terminal(
        {
            "q1": {
                "governed_samples": 10,
                "aligned_supervised_samples": 10,
                "trainable_after_support_filter": 10,
                "families_represented": 2,
                "malware_types_represented": 1,
                "concentration": {
                    "top_family": "fam_a",
                    "top_family_count": 6,
                    "top_family_share_pct": 60.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                },
                "quality_gates": {},
                "supervised_family_claims_suitable": True,
            },
            "q2": {
                "permission_signal_n": 9,
                "permission_signal_pct": 90.0,
                "permission_raw_observation_n": 9,
                "permission_raw_observation_pct": 90.0,
                "permission_feature_columns": 10,
                "vendor_merge_n": 10,
                "vendor_merge_pct": 100.0,
                "av_engines_observed": 5,
                "av_engines_included": 3,
            },
            "q3": {},
            "model_key": "random_forest",
            "macro_f1": 0.9,
            "wf1": 0.91,
            "acc": 0.92,
            "gap_w_m": 0.01,
            "concentration_warn": True,
        },
        pr=captured.append,
        du=_DummyDisplay(),
    )

    text = "\n".join(captured)
    assert "parsed vendor weak-support coverage is full (100.0%)." in text
    assert "parsed vendor weak-support coverage is sparse (100.0%)." not in text


def test_print_research_questions_terminal_compact_summary_omits_headline_task_boundary(
    monkeypatch,
) -> None:
    captured: list[str] = []

    class _DummyDisplay:
        @staticmethod
        def print_section(_title: str) -> None:
            return None

        @staticmethod
        def print_table(*_args, **_kwargs) -> None:
            return None

    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    rtq.print_research_questions_terminal(
        {
            "q1": {
                "governed_samples": 10,
                "aligned_supervised_samples": 10,
                "trainable_after_support_filter": 8,
                "families_represented": 2,
                "malware_types_represented": 1,
                "concentration": {
                    "top_family": "fam_a",
                    "top_family_count": 6,
                    "top_family_share_pct": 60.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                },
                "quality_gates": {},
                "supervised_family_claims_suitable": True,
            },
            "q2": {
                "permission_signal_n": 9,
                "permission_signal_pct": 90.0,
                "permission_raw_observation_n": 9,
                "permission_raw_observation_pct": 90.0,
                "permission_feature_columns": 10,
                "vendor_merge_n": 10,
                "vendor_merge_pct": 100.0,
                "av_engines_observed": 5,
                "av_engines_included": 3,
            },
            "q3": {},
            "model_key": "random_forest",
            "macro_f1": 0.9,
            "wf1": 0.91,
            "acc": 0.92,
            "gap_w_m": 0.01,
            "concentration_warn": False,
        },
        pr=captured.append,
        du=_DummyDisplay(),
    )

    text = "\n".join(captured)
    assert "Bottom line:" in text
    assert "Headline task boundary:" not in text


def test_modality_summary_uses_global_feature_column_survival_mirror(make_run_diagnostics_layout) -> None:
    """Q2 feature-group export should still work when run-local `.latest` is intentionally omitted."""
    output_root, diagnostics_dir, global_diag = make_run_diagnostics_layout("run3")

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 2,
                "family_type_summary": {
                    "family_count": 1,
                    "type_count": 1,
                    "top_family": "fam_a",
                    "top_family_count": 2,
                    "top_family_share_pct": 100.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"fam_a": 2},
                    "type_distribution": {"banker": 2},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_modality_coverage_summary_run3.json").write_text(
        json.dumps(
            {
                "run_id": "run3",
                "permission_pi_signal_positive_n": 2,
                "vendor_merge_n": 2,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "modality_method_contract.json").write_text(
        json.dumps(
            {
                "fusion_modality": {"feature_count_permission": 1},
                "permission_modality": {"feature_count_raw": 1},
            }
        ),
        encoding="utf-8",
    )
    (global_diag / "feature_column_survival.latest.csv").write_text(
        "feature_name,nonzero_count_final_training,modality\n"
        "perm__android_CAMERA,2,permission\n",
        encoding="utf-8",
    )

    rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id="run3",
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
    )


def test_terminal_summary_bottom_line_is_not_promising_for_weak_macro_f1() -> None:
    captured: list[str] = []

    class _DummyDisplay:
        @staticmethod
        def print_section(_title: str) -> None:
            return None

    rtq.print_research_questions_terminal(
        bundle={
            "q1": {
                "governed_samples": 1187,
                "families_represented": 35,
                "malware_types_represented": 3,
                "concentration": {"top5_share_pct": 50.88},
            },
            "q2": {
                "permission_raw_observation_n": 1151,
                "permission_raw_observation_pct": 96.97,
                "permission_signal_n": 1151,
                "permission_signal_pct": 96.97,
                "vendor_merge_pct": 100.0,
                "av_engines_observed": 93,
                "av_engines_included": 56,
            },
            "q3": {},
            "model_key": "random_forest",
            "macro_f1": 0.3261,
            "wf1": 0.5890,
            "acc": 0.5474,
            "gap_w_m": 0.2629,
            "concentration_warn": True,
        },
        pr=captured.append,
        du=_DummyDisplay(),
    )

    text = "\n".join(captured)
    assert "Bottom line:" in text
    assert "treat this as weak evidence" in text
    assert "promising, not final proof" not in text


def test_terminal_summary_surfaces_dominant_blockers_for_weak_run(monkeypatch) -> None:
    captured: list[str] = []

    class _DummyDisplay:
        @staticmethod
        def print_section(_title: str) -> None:
            return None

    monkeypatch.setattr(
        rtq.app_config,
        "RUNTIME_TEMPORAL_SPLIT_SUMMARY",
        {"test_rows_dropped_unseen_train_classes": 219},
        raising=False,
    )

    rtq.print_research_questions_terminal(
        bundle={
            "q1": {
                "governed_samples": 1187,
                "families_represented": 43,
                "malware_types_represented": 4,
                "concentration": {"top5_share_pct": 50.46},
                "supervised_family_claims_suitable": False,
            },
            "q2": {
                "permission_raw_observation_n": 1151,
                "permission_raw_observation_pct": 96.97,
                "permission_signal_n": 1151,
                "permission_signal_pct": 96.97,
                "vendor_merge_pct": 100.0,
                "av_engines_observed": 93,
                "av_engines_included": 56,
            },
            "q3": {},
            "model_key": "xgboost",
            "macro_f1": 0.2186,
            "wf1": 0.3848,
            "acc": 0.3387,
            "gap_w_m": 0.1662,
            "confusion_rows": [
                {
                    "true_label": "SpyNote",
                    "predicted_label": "Alien",
                    "count": 10,
                    "shared_malware_type": "no",
                },
                {
                    "true_label": "Godfather",
                    "predicted_label": "PixPirate",
                    "count": 7,
                    "shared_malware_type": "yes",
                },
            ],
            "concentration_warn": True,
        },
        pr=captured.append,
        du=_DummyDisplay(),
    )

    text = "\n".join(captured)
    assert "4. Dominant blockers:" in text
    assert "supervised family claims are not yet suitable" in text
    assert "temporal holdout dropped 219 future-only family row(s)" in text
    assert "weighted F1 exceeds Macro-F1 by +0.1662" in text
    assert "cross-type confusions appear in 1/2 top confusion pairs" in text
