"""Tests for stop-after-training execution boundaries."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
import analysis.pipeline.runner as pipeline_runner
import main
from obsidiandroid.reporting import family_distribution_report


def test_stop_after_training_skips_ablation_and_permission_trends(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`stop_after='training'` should not execute post-training heavy stages."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_EXPERIMENTS", True, raising=False)
    monkeypatch.setattr(app_config, "SKIP_ABLATIONS_FOR_SINGLE_MODEL", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_PERMISSION_TRENDS_REPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(output_root), raising=False)
    monkeypatch.setattr(pipeline_runner, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))

    sha = "a" * 64
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": [sha, "b" * 64],
            "family_id": [10, 11],
            "family_name": ["fam_a", "fam_b"],
            "family_canonical": ["fam_a", "fam_b"],
            "type_slug": ["banker", "dropper"],
        }
    )
    feature_df = pd.DataFrame({"f1": [0.1, 0.2]}, index=pd.Index([1, 2], name="sample_id"))
    feature_df["sample_id"] = feature_df.index
    feature_df.attrs["selected_vendors"] = ["v1", "v2"]
    labels_df = samples_df[["sample_id", "sha256", "family_id", "family_name", "family_canonical"]].copy()

    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "unit_profile",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
            },
        },
    )
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)
    monkeypatch.setattr(main, "load_and_prepare_samples", lambda **_kwargs: samples_df.copy())
    monkeypatch.setattr(
        main,
        "run_av_analysis_stage",
        lambda **_kwargs: {
            "engine_lifecycle": pd.DataFrame(
                {"included_in_model_flag": [True, False], "engine_name_canonical": ["v1", "v2"]}
            ),
            "enriched_matrix": pd.DataFrame(),
        },
    )
    monkeypatch.setattr(
        pipeline_runner,
        "extract_vendor_metadata_stage",
        lambda **_kwargs: (pd.DataFrame({"Vendor": ["v1"]}), {"v1": []}, {}, pd.DataFrame({"Final ML Score": [0.1]})),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "compute_engine_weights_from_pipeline",
        lambda _results: pd.DataFrame({"Leakage Safe Score": [0.5]}),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "build_feature_matrix_stage",
        lambda *_args, **_kwargs: feature_df.copy(),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_feature_alignment_stage",
        lambda **_kwargs: (feature_df.copy(), labels_df.copy()),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_training_stage",
        lambda **_kwargs: {
            "logistic_regression": {
                "evaluation": {"macro_f1_score": 0.8, "accuracy": 0.9},
                "metadata": {"params": {"C": 1.0}},
                "cv_score_mean": 0.79,
            }
        },
    )
    monkeypatch.setattr(
        pipeline_runner,
        "_export_model_config_snapshot",
        lambda **_kwargs: str(tmp_path / "output" / "diagnostics" / "model_config_snapshot_test.json"),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "_enforce_duplicate_sha_policy",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        family_distribution_report, "print_family_distribution_stats", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)

    calls = {"ablation": 0, "permission": 0}
    monkeypatch.setattr(
        pipeline_runner,
        "run_ablation_experiments",
        lambda **_kwargs: calls.__setitem__("ablation", calls["ablation"] + 1) or [],
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_permission_trends_report_stage",
        lambda **_kwargs: calls.__setitem__("permission", calls["permission"] + 1) or [],
    )

    result = main.run_pipeline(stop_after="training", profile_ref="unit_profile")

    assert result == 0
    assert calls["ablation"] == 0
    assert calls["permission"] == 0


def test_stop_after_ablation_skips_permission_trends(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`stop_after='ablation'` should execute ablation but skip later report stages."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_EXPERIMENTS", True, raising=False)
    monkeypatch.setattr(app_config, "SKIP_ABLATIONS_FOR_SINGLE_MODEL", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_PERMISSION_TRENDS_REPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(output_root), raising=False)
    monkeypatch.setattr(pipeline_runner, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))

    sha = "a" * 64
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": [sha, "b" * 64],
            "family_id": [10, 11],
            "family_name": ["fam_a", "fam_b"],
            "family_canonical": ["fam_a", "fam_b"],
            "type_slug": ["banker", "dropper"],
        }
    )
    feature_df = pd.DataFrame({"f1": [0.1, 0.2]}, index=pd.Index([1, 2], name="sample_id"))
    feature_df["sample_id"] = feature_df.index
    feature_df.attrs["selected_vendors"] = ["v1", "v2"]
    labels_df = samples_df[["sample_id", "sha256", "family_id", "family_name", "family_canonical"]].copy()

    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "unit_profile",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
            },
        },
    )
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)
    monkeypatch.setattr(main, "load_and_prepare_samples", lambda **_kwargs: samples_df.copy())
    monkeypatch.setattr(
        main,
        "run_av_analysis_stage",
        lambda **_kwargs: {
            "engine_lifecycle": pd.DataFrame(
                {"included_in_model_flag": [True, False], "engine_name_canonical": ["v1", "v2"]}
            ),
            "enriched_matrix": pd.DataFrame(),
        },
    )
    monkeypatch.setattr(
        pipeline_runner,
        "extract_vendor_metadata_stage",
        lambda **_kwargs: (pd.DataFrame({"Vendor": ["v1"]}), {"v1": []}, {}, pd.DataFrame({"Final ML Score": [0.1]})),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "compute_engine_weights_from_pipeline",
        lambda _results: pd.DataFrame({"Leakage Safe Score": [0.5]}),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "build_feature_matrix_stage",
        lambda *_args, **_kwargs: feature_df.copy(),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_feature_alignment_stage",
        lambda **_kwargs: (feature_df.copy(), labels_df.copy()),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_training_stage",
        lambda **_kwargs: {
            "logistic_regression": {
                "evaluation": {"macro_f1_score": 0.8, "accuracy": 0.9},
                "metadata": {"params": {"C": 1.0}},
                "cv_score_mean": 0.79,
            }
        },
    )
    monkeypatch.setattr(
        pipeline_runner,
        "_export_model_config_snapshot",
        lambda **_kwargs: str(tmp_path / "output" / "diagnostics" / "model_config_snapshot_test.json"),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "_enforce_duplicate_sha_policy",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        family_distribution_report, "print_family_distribution_stats", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)

    calls = {"ablation": 0, "permission": 0}
    monkeypatch.setattr(
        pipeline_runner,
        "run_ablation_experiments",
        lambda **_kwargs: calls.__setitem__("ablation", calls["ablation"] + 1) or [],
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_permission_trends_report_stage",
        lambda **_kwargs: calls.__setitem__("permission", calls["permission"] + 1) or [],
    )

    result = main.run_pipeline(stop_after="ablation", profile_ref="unit_profile")

    assert result == 0
    assert calls["ablation"] == 1
    assert calls["permission"] == 0


def test_stop_after_label_resolution_with_stage_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`stop_after='label_resolution'` should finalize cleanly when stage is disabled."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_EXPERIMENTS", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_PERMISSION_TRENDS_REPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LABEL_RESOLUTION_STAGE", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(output_root), raising=False)
    monkeypatch.setattr(pipeline_runner, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))

    sha = "a" * 64
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": [sha, "b" * 64],
            "family_id": [10, 11],
            "family_name": ["fam_a", "fam_b"],
            "family_canonical": ["fam_a", "fam_b"],
            "type_slug": ["banker", "dropper"],
        }
    )
    feature_df = pd.DataFrame({"f1": [0.1, 0.2]}, index=pd.Index([1, 2], name="sample_id"))
    feature_df["sample_id"] = feature_df.index
    feature_df.attrs["selected_vendors"] = ["v1", "v2"]
    labels_df = samples_df[["sample_id", "sha256", "family_id", "family_name", "family_canonical"]].copy()

    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "unit_profile",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
            },
        },
    )
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)
    monkeypatch.setattr(main, "load_and_prepare_samples", lambda **_kwargs: samples_df.copy())
    monkeypatch.setattr(
        main,
        "run_av_analysis_stage",
        lambda **_kwargs: {
            "engine_lifecycle": pd.DataFrame(
                {"included_in_model_flag": [True, False], "engine_name_canonical": ["v1", "v2"]}
            ),
            "enriched_matrix": pd.DataFrame(),
        },
    )
    monkeypatch.setattr(
        pipeline_runner,
        "extract_vendor_metadata_stage",
        lambda **_kwargs: (pd.DataFrame({"Vendor": ["v1"]}), {"v1": []}, {}, pd.DataFrame({"Final ML Score": [0.1]})),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "compute_engine_weights_from_pipeline",
        lambda _results: pd.DataFrame({"Leakage Safe Score": [0.5]}),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "build_feature_matrix_stage",
        lambda *_args, **_kwargs: feature_df.copy(),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_feature_alignment_stage",
        lambda **_kwargs: (feature_df.copy(), labels_df.copy()),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "run_training_stage",
        lambda **_kwargs: {
            "logistic_regression": {
                "evaluation": {"macro_f1_score": 0.8, "accuracy": 0.9},
                "metadata": {"params": {"C": 1.0}},
                "cv_score_mean": 0.79,
            }
        },
    )
    monkeypatch.setattr(
        pipeline_runner,
        "_export_model_config_snapshot",
        lambda **_kwargs: str(tmp_path / "output" / "diagnostics" / "model_config_snapshot_test.json"),
    )
    monkeypatch.setattr(
        pipeline_runner,
        "_enforce_duplicate_sha_policy",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        family_distribution_report, "print_family_distribution_stats", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)

    calls = {"label_resolution": 0}
    monkeypatch.setattr(
        pipeline_runner,
        "resolve_final_labels_stage",
        lambda *_args, **_kwargs: calls.__setitem__("label_resolution", calls["label_resolution"] + 1) or None,
    )

    result = main.run_pipeline(stop_after="label_resolution", profile_ref="unit_profile")

    assert result == 0
    assert calls["label_resolution"] == 0
