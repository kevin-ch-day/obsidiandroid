"""Tests for quantitative data-problem diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.diagnostics.data_problem_quantification import (
    build_data_problem_quantification,
    compare_data_problem_quantification,
    write_data_problem_delta,
    write_data_problem_quantification,
)


def _seed_quantification_inputs(diagnostics_dir: Path) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "family_distribution.csv").write_text(
        "\n".join(
            [
                "family,sample_count",
                "Dominant,50",
                "RunnerUp,30",
                "TailNear,18",
                "TailA,10",
                "TailB,5",
                "TailC,5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "family_support_vs_performance.csv").write_text(
        "\n".join(
            [
                "family,support,recall,precision,f1_score",
                "Dominant,20,0.80,0.85,0.82",
                "RunnerUp,12,0.50,0.55,0.52",
                "TailA,5,0.00,0.00,0.00",
                "Unseen,0,0.00,0.00,0.00",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "top_confusion_pairs.csv").write_text(
        "\n".join(
            [
                "true_family,predicted_family,count,shared_type",
                "TailA,Dominant,8,no",
                "RunnerUp,Dominant,4,yes",
                "TailB,RunnerUp,3,no",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_set_ablation_summary.csv").write_text(
        "\n".join(
            [
                "feature_set_label,model,label_target,macro_f1,weighted_f1,accuracy",
                "vendor_parsed_full,random_forest,family_id,0.45,0.70,0.62",
                "vendor_parsed_no_family,random_forest,family_id,0.20,0.35,0.30",
                "permissions_grouped,logistic_regression,family_id,0.24,0.40,0.33",
                "full_fused,random_forest,family_id,0.31,0.49,0.44",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "family_vs_type_performance.csv").write_text(
        "label_target,best_model,best_experiment,macro_f1,weighted_f1,accuracy\n"
        "type_slug,random_forest,permissions_raw,0.60,0.86,0.88\n",
        encoding="utf-8",
    )
    prediction_error_text = (
        "\n".join(
            [
                "sample_id,family_canonical_expected,predicted_family",
                "1,Dominant,RunnerUp",
                "2,Dominant,RunnerUp",
                "3,Dominant,RunnerUp",
                "4,Dominant,RunnerUp",
                "5,TailA,Dominant",
                "6,TailA,Dominant",
                "7,TailA,Dominant",
                "8,TailB,Dominant",
                "9,TailB,Dominant",
                "10,TailC,RunnerUp",
            ]
        )
        + "\n"
    )
    for run_id in ("run1", "20260528T055940Z__c4c234"):
        (diagnostics_dir / f"prediction_errors_{run_id}.csv").write_text(
            prediction_error_text,
            encoding="utf-8",
        )


def test_build_data_problem_quantification_flags_math_and_risk(tmp_path: Path) -> None:
    _seed_quantification_inputs(tmp_path)

    payload = build_data_problem_quantification(diagnostics_dir=tmp_path, run_id="run1")

    dist = payload["family_distribution"]
    assert dist["total"] == 118
    assert dist["classes"] == 6
    assert dist["top1_share"] == pytest.approx(0.423729)
    assert dist["top3_share"] == pytest.approx(0.830508)
    assert dist["top5_share"] == pytest.approx(0.957627)
    assert dist["hhi"] == pytest.approx(0.278225)
    assert dist["effective_class_count_hhi"] == pytest.approx(3.594218)
    assert dist["kl_to_uniform_bits"] > 0
    assert dist["palma_ratio"] > 1
    assert dist["hhi_marginal_relief_smallest_plus_one"] > 0
    assert payload["support_performance"]["zero_recall_positive_support_rows"] == 1
    assert payload["support_gap"]["below_support_family_count"] == 4
    assert payload["support_gap"]["families_with_gap_le_5"] == 1
    assert payload["support_gap"]["top_support_gap_family"] == "TailNear"
    assert payload["support_gap"]["samples_needed_to_make_all_families_trainable"] == 42
    assert payload["support_threshold_curve"]["threshold_20"]["trainable_classes"] == 2
    assert payload["support_threshold_curve"]["dual_track_recommended"] is True
    assert payload["support_threshold_curve"]["recommended_exploratory_threshold"]["threshold"] == 10
    policy = payload["training_policy_recommendations"]
    assert policy["primary_headline_track"] == "evidence_conservative_threshold_20"
    assert policy["secondary_tuning_track"] == "exploratory_expanded_class_threshold"
    tracks = {row["track"]: row for row in policy["tracks"]}
    assert tracks["exploratory_expanded_class_threshold"]["class_lift_vs_threshold_20"] == 2
    assert "curation_support_gap_closure" in tracks
    assert payload["confusion"]["cross_type_confusion_mass"] == 11
    assert payload["confusion"]["cross_type_confusion_share"] == pytest.approx(0.733333)
    assert payload["prediction_errors"]["top3_error_pair_share"] == pytest.approx(0.9)
    assert payload["prediction_errors"]["top_expected_error_family"] == "Dominant"
    assert payload["ablation"]["vendor_full_minus_safe"] == pytest.approx(0.25)
    assert payload["ablation"]["vendor_full_minus_full_fused"] == pytest.approx(0.14)
    assert payload["ablation"]["type_minus_best_family_safe"] == pytest.approx(0.29)
    assert payload["priority_score"]["composite_problem_score_0_100"] > 70

    issues = {row["issue"] for row in payload["issue_flags"]}
    assert "family_concentration" in issues
    assert "zero_recall_supported_families" in issues
    assert "near_threshold_trainability_lift" in issues
    assert "dual_support_threshold_track" in issues
    assert "cross_type_confusion" in issues
    assert "prediction_error_pair_concentration" in issues
    assert "vendor_semantic_leakage_delta" in issues
    assert "type_family_task_gap" in issues


def test_write_data_problem_quantification_writes_artifacts_and_latest_mirrors(
    make_run_diagnostics_layout,
) -> None:
    run_id = "20260528T055940Z__c4c234"
    _out_root, rdiag, gdiag = make_run_diagnostics_layout(run_id)
    _seed_quantification_inputs(rdiag)

    md_path, csv_path, json_path, payload = write_data_problem_quantification(
        diagnostics_dir=rdiag,
        run_id=run_id,
    )

    assert payload["issue_flags"]
    assert md_path.is_file()
    assert csv_path.is_file()
    assert json_path.is_file()
    md_text = md_path.read_text(encoding="utf-8")
    assert "Distribution Math" in md_text
    assert "Marginal Fix Math" in md_text
    assert "Support Threshold Curve" in md_text
    assert "Training Policy Recommendations" in md_text
    assert "exploratory_expanded_class_threshold" in md_text
    assert "Fastest Trainability Lift" in md_text
    assert "Concentrated Prediction Errors" in md_text
    assert "vendor_semantic_leakage_delta" in md_text
    assert json.loads(json_path.read_text(encoding="utf-8"))["run_id"] == run_id
    assert (gdiag / "data_problem_quantification.latest.md").is_file()
    assert (gdiag / "data_problem_quantification.latest.csv").is_file()
    assert (gdiag / "data_problem_quantification.latest.json").is_file()


def test_data_problem_quantification_uses_run_local_partial_artifacts_before_global_latest(
    make_run_diagnostics_layout,
) -> None:
    run_id = "partial_run"
    _out_root, rdiag, gdiag = make_run_diagnostics_layout(run_id)
    (rdiag / f"aligned_labels_{run_id}.csv").write_text(
        "\n".join(
            [
                "sample_id,family_canonical,type_slug",
                "1,Alpha,banker",
                "2,Alpha,banker",
                "3,Beta,rat",
                "4,Gamma,spyware",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (rdiag / f"ablation_summary_partial_{run_id}.csv").write_text(
        "\n".join(
            [
                "experiment,label_target,model,macro_f1_score,weighted_f1_score,accuracy",
                "vendor_full,family_id,logistic_regression,0.38,0.56,0.52",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (gdiag / "feature_set_ablation_summary.latest.csv").write_text(
        "\n".join(
            [
                "feature_set_label,model,label_target,macro_f1,weighted_f1,accuracy",
                "vendor_parsed_full,random_forest,family_id,0.99,0.99,0.99",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_data_problem_quantification(diagnostics_dir=rdiag, run_id=run_id)

    assert payload["family_distribution"]["total"] == 4
    assert payload["family_distribution"]["classes"] == 3
    assert payload["support_gap"]["below_support_family_count"] == 3
    assert payload["ablation"]["best_family_experiment"] == "vendor_full"
    assert payload["ablation"]["best_family_macro_f1"] == pytest.approx(0.38)


def test_compare_data_problem_quantification_flags_taxonomy_tail_regression() -> None:
    baseline = {
        "run_id": "baseline",
        "family_distribution": {
            "classes": 35,
            "normalized_entropy": 0.858,
            "gini": 0.511,
            "atkinson_0_5": 0.224,
            "bottom20_share": 0.039,
            "bottom50_share": 0.190,
            "palma_ratio": 3.7,
        },
        "support_gap": {
            "below_support_family_count": 17,
            "samples_needed_to_make_all_families_trainable": 134,
        },
        "ablation": {"best_family_macro_f1": 0.431},
        "priority_score": {"composite_problem_score_0_100": 80},
    }
    current = {
        "run_id": "current",
        "family_distribution": {
            "classes": 40,
            "normalized_entropy": 0.832,
            "gini": 0.567,
            "atkinson_0_5": 0.285,
            "bottom20_share": 0.011,
            "bottom50_share": 0.147,
            "palma_ratio": 5.3,
        },
        "support_gap": {
            "below_support_family_count": 23,
            "samples_needed_to_make_all_families_trainable": 230,
        },
        "ablation": {"best_family_macro_f1": 0.381},
        "priority_score": {"composite_problem_score_0_100": 90},
    }

    payload = compare_data_problem_quantification(
        current_payload=current,
        baseline_payload=baseline,
    )

    assert payload["deltas"]["family_classes_delta"] == 5
    assert payload["deltas"]["samples_needed_to_trainable_delta"] == 96
    assert payload["composite_score_comparable"] is False
    assert payload["deltas"]["composite_problem_score_delta"] is None
    regression_metrics = {row["metric"] for row in payload["regressions"]}
    assert "family_classes_delta" in regression_metrics
    assert "below_support_family_count_delta" in regression_metrics
    assert "samples_needed_to_trainable_delta" in regression_metrics
    assert "bottom50_share_delta" in regression_metrics
    assert "best_family_macro_f1_delta" in regression_metrics


def test_write_data_problem_delta_writes_markdown_and_json(make_run_diagnostics_layout) -> None:
    current_run = "current_run"
    baseline_run = "baseline_run"
    _out_root, current_diag, _gdiag = make_run_diagnostics_layout(current_run)
    baseline_diag = current_diag.parent.parent / baseline_run / "diagnostics"
    baseline_diag.mkdir(parents=True, exist_ok=True)
    _seed_quantification_inputs(baseline_diag)
    _seed_quantification_inputs(current_diag)
    (baseline_diag / f"aligned_labels_{baseline_run}.csv").write_text(
        "\n".join(
            [
                "sample_id,family_canonical,family_id,type_slug,vt_family_token",
                "1,Dominant,1,banker,dominant",
                "2,Dominant,1,banker,dominant",
                "3,Dominant,1,banker,newtail",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (current_diag / f"aligned_labels_{current_run}.csv").write_text(
        "\n".join(
            [
                "sample_id,family_canonical,family_id,type_slug,vt_family_token",
                "1,Dominant,1,banker,dominant",
                "2,DominantSplit,2,banker,dominant",
                "3,NewTail,3,banker,newtail",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    md_path, json_path, payload = write_data_problem_delta(
        current_diagnostics_dir=current_diag,
        current_run_id=current_run,
        baseline_diagnostics_dir=baseline_diag,
        baseline_run_id=baseline_run,
    )

    assert md_path.is_file()
    assert json_path.is_file()
    assert payload["current_run_id"] == current_run
    text = md_path.read_text(encoding="utf-8")
    assert "Deltas" in text
    assert "Composite score comparable" in text
    assert "Taxonomy Transition Summary" in text
    assert payload["taxonomy_transition_summary"]["changed_sample_rows"] == 2
    assert payload["taxonomy_transition_summary"]["new_current_families"] == [
        "DominantSplit",
        "NewTail",
    ]
    remerge = payload["taxonomy_transition_summary"]["remerge_simulation"]
    assert remerge["candidate_family_count"] == 2
    assert remerge["family_count_delta"] == -2
    assert remerge["merge_groups"][0]["source_family"] == "Dominant"
    assert sorted(remerge["merge_groups"][0]["merge_families"]) == ["DominantSplit", "NewTail"]
    regression_metrics = {row["metric"] for row in payload["regressions"]}
    assert "taxonomy_fragmentation_transition" in regression_metrics
    transition_csv = current_diag / f"data_problem_family_transitions_{current_run}_vs_{baseline_run}.csv"
    assert transition_csv.is_file()
