"""Tests for ML tuning recommendation artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.diagnostics.ml_tuning_recommendations import (
    build_ml_tuning_recommendations,
    write_ml_tuning_recommendations,
)


def _seed_run_like_diagnostics(diagnostics_dir: Path) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "feature_set_ablation_summary.csv").write_text(
        "\n".join(
            [
                "feature_set_label,model,label_target,macro_f1,weighted_f1,accuracy,delta_vs_full_fused",
                "vendor_parsed_full,random_forest,family_id,0.4318,0.7102,0.6350,0.1287",
                "vendor_parsed_no_family,random_forest,family_id,0.1698,0.3560,0.3139,-0.1333",
                "permissions_raw,random_forest,family_id,0.1675,0.2981,0.2482,-0.1356",
                "permissions_grouped,logistic_regression,family_id,0.2229,0.3299,0.2555,0.0034",
                "full_fused,random_forest,family_id,0.3031,0.4880,0.4380,0.0",
                "permissions_raw,random_forest,type_slug,0.5764,0.8501,0.8816,0.0094",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "top_confusion_pairs.csv").write_text(
        "\n".join(
            [
                "true_family,predicted_family,count,shared_type",
                "Godfather,PixPirate,11,yes",
                "TrickMo,SpyNote,8,no",
                "SpyNote,Joker,7,no",
                "Vultur,Joker,6,yes",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_ml_tuning_recommendations_flags_leakage_and_target_strategy(tmp_path: Path) -> None:
    _seed_run_like_diagnostics(tmp_path)

    payload = build_ml_tuning_recommendations(diagnostics_dir=tmp_path, run_id="run1")

    areas = {row["area"] for row in payload["recommendations"]}
    assert "vendor_feature_processing" in areas
    assert "fusion_policy" in areas
    assert "target_strategy" in areas
    assert "hierarchical_modeling" in areas
    assert payload["metrics"]["vendor_full_family_macro_f1"] == 0.4318
    assert payload["metrics"]["type_slug_macro_f1"] == 0.5764


def test_write_ml_tuning_recommendations_writes_artifacts_and_latest_mirrors(
    make_run_diagnostics_layout,
) -> None:
    run_id = "20260528T055940Z__c4c234"
    out_root, rdiag, gdiag = make_run_diagnostics_layout(run_id)
    _seed_run_like_diagnostics(rdiag)

    md_path, csv_path, json_path, payload = write_ml_tuning_recommendations(
        diagnostics_dir=rdiag,
        run_id=run_id,
    )

    assert payload["recommendation_count"] >= 3
    assert md_path.is_file()
    assert csv_path.is_file()
    assert json_path.is_file()
    assert "vendor_feature_processing" in md_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["recommendation_count"] >= 3
    assert (gdiag / "ml_tuning_recommendations.latest.md").is_file()
    assert (gdiag / "ml_tuning_recommendations.latest.csv").is_file()
    assert (gdiag / "ml_tuning_recommendations.latest.json").is_file()


def test_ml_tuning_recommendations_reads_type_signal_from_family_vs_type_when_compact_ablation_omits_type(
    tmp_path: Path,
) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "feature_set_ablation_summary.csv").write_text(
        "\n".join(
            [
                "feature_set_label,model,label_target,macro_f1,weighted_f1,accuracy,delta_vs_full_fused",
                "vendor_parsed_no_family,random_forest,family_id,0.1698,0.3560,0.3139,-0.1333",
                "full_fused,random_forest,family_id,0.3031,0.4880,0.4380,0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "family_vs_type_performance.csv").write_text(
        "label_target,best_model,best_experiment,macro_f1,weighted_f1,accuracy\n"
        "type_slug,random_forest,permissions_raw,0.5764,0.8501,0.8816\n",
        encoding="utf-8",
    )

    payload = build_ml_tuning_recommendations(diagnostics_dir=tmp_path, run_id="run1")

    areas = {row["area"] for row in payload["recommendations"]}
    assert "target_strategy" in areas
    assert payload["metrics"]["type_slug_macro_f1"] == 0.5764


def test_ml_tuning_recommendations_prefers_run_local_partial_before_global_latest(
    make_run_diagnostics_layout,
) -> None:
    run_id = "partial_run"
    _out_root, rdiag, gdiag = make_run_diagnostics_layout(run_id)
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

    payload = build_ml_tuning_recommendations(diagnostics_dir=rdiag, run_id=run_id)

    assert payload["ablation_source"].endswith(f"ablation_summary_partial_{run_id}.csv")
    assert payload["metrics"]["vendor_full_family_macro_f1"] == 0.38
