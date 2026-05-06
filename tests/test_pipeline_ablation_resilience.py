"""Integration-style tests for ablation bookkeeping + interrupted pipeline finalization."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
import obsidiandroid.pipeline.runner as pipeline_runner
import main
from obsidiandroid.reporting import family_distribution_report


def _find_run_scoped_stage_summary(tmp_path: Path) -> Path:
    """PipelineObservability writes under output/runs/<run_id>/diagnostics/ in non-evidence mode."""
    hits = sorted(tmp_path.glob("output/runs/*/diagnostics/pipeline_stage_summary.csv"))
    assert len(hits) == 1, f"expected exactly one stage summary, got {hits}"
    return hits[0]


def _minimal_pipeline_fixture(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    diag = output_root / "diagnostics"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_PERMISSION_TRENDS_REPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(output_root), raising=False)
    monkeypatch.setattr(pipeline_runner, "DIAGNOSTICS_DIR", str(diag))


def test_ablation_keyboard_interrupt_records_interrupted_stage_and_finalizes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _minimal_pipeline_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_EXPERIMENTS", True, raising=False)
    monkeypatch.setattr(app_config, "SKIP_ABLATIONS_FOR_SINGLE_MODEL", False, raising=False)

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
            "evidence_mode": False,
            "allow_vendor_fallback_for_width": True,
            "allow_adaptive_top_k": True,
            "top_k_requested": 8,
            "exclude_unknown_from_main_results": False,
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
    monkeypatch.setattr(pipeline_runner, "_enforce_duplicate_sha_policy", lambda **_kwargs: None)
    monkeypatch.setattr(family_distribution_report, "print_family_distribution_stats", lambda *_a, **_k: None)

    finalized: list[int] = []

    def _finalize(**_kwargs) -> int:
        finalized.append(1)
        return 0

    monkeypatch.setattr(main, "finalize_run_manifest_stage", _finalize)

    monkeypatch.setattr(
        pipeline_runner,
        "run_ablation_experiments",
        lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    result = main.run_pipeline(stop_after="ablation", profile_ref="unit_profile")
    assert result == 130
    assert finalized == [1]
    summary_csv = _find_run_scoped_stage_summary(tmp_path)
    body = summary_csv.read_text(encoding="utf-8")
    assert "ablation" in body
    assert "INTERRUPTED" in body


def test_ablation_runtime_error_emits_failed_stage_timing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _minimal_pipeline_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_EXPERIMENTS", True, raising=False)
    monkeypatch.setattr(app_config, "SKIP_ABLATIONS_FOR_SINGLE_MODEL", False, raising=False)

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
            "evidence_mode": False,
            "allow_vendor_fallback_for_width": True,
            "allow_adaptive_top_k": True,
            "top_k_requested": 8,
            "exclude_unknown_from_main_results": False,
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
    monkeypatch.setattr(pipeline_runner, "_enforce_duplicate_sha_policy", lambda **_kwargs: None)
    monkeypatch.setattr(family_distribution_report, "print_family_distribution_stats", lambda *_a, **_k: None)
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)

    def _boom(**_kwargs) -> None:
        raise RuntimeError("ablation_stage_unit_fail")

    monkeypatch.setattr(pipeline_runner, "run_ablation_experiments", _boom)

    result = main.run_pipeline(stop_after="ablation", profile_ref="unit_profile")
    assert result == 1
    summary_csv = _find_run_scoped_stage_summary(tmp_path)
    blob = summary_csv.read_text(encoding="utf-8")
    assert "ablation" in blob
    assert "FAIL" in blob


def test_apply_profile_sets_ablation_model_list_from_yaml_shape(monkeypatch) -> None:
    from obsidiandroid.pipeline.runtime_policy import apply_profile_runtime_policy

    monkeypatch.setattr(app_config, "FEATURE_TOP_K", 8, raising=False)
    profile = {
        "profile_id": "unit_yaml_shape",
        "type_slug_filter": None,
        "cohort_gates": {},
        "model_list": ["logistic_regression", "random_forest"],
        "feature_flags": {},
        "runtime_overrides": {},
        "parser_overrides": {},
        "evidence_mode": False,
        "allow_vendor_fallback_for_width": True,
        "allow_adaptive_top_k": True,
        "top_k_requested": 8,
        "exclude_unknown_from_main_results": False,
        "ablation_model_list": ["random_forest"],
    }
    apply_profile_runtime_policy(
        profile=profile,
        feature_flags=profile["feature_flags"],
        allow_evidence_override=False,
        allow_global_artifacts=False,
        manifest_context={},
    )
    assert app_config.ABLATION_MODEL_LIST == ["random_forest"]
