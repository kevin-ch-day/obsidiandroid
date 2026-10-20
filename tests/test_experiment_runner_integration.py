"""Synthetic full runner-to-generic-trainer integrity checks; no real sources."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from config import app_config
from obsidiandroid.pipeline import runner as pipeline_runner
from obsidiandroid.modeling import pipeline_core, model_trainer_factory as factory
from obsidiandroid.modeling import experiment_split as es
from obsidiandroid.reporting import family_distribution_report
from test_experiment_split_integrity import fixture  # noqa: F401
main = pipeline_runner

@pytest.mark.integration
@pytest.mark.parametrize('target', ['family_id', 'type_slug', 'family_within_type'])
@pytest.mark.parametrize('corrupt', [False, True])
def test_runner_reaches_governed_trainer(
    monkeypatch,
    tmp_path: Path, fixture, target, corrupt,
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

    samples_df, profile, fit_calls = fixture
    profile['training_label_field'] = target
    profile['model_list'] = ['random_forest']
    profile['feature_flags']['permission_input_policy'] = 'required'
    profile['feature_flags']['enable_dynamic_generic_vendor_parsers'] = False
    profile['runtime_overrides'] = {'AUTO_ADJUST_TRAIN_TEST_SPLIT': False,
                                    'ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT': False}
    monkeypatch.setattr(main.profile_manager, 'load_profile', lambda ref: profile)
    labels_df = samples_df.copy()
    def feature_build(*args, **kwargs):
        frame = args[2].copy()
        frame['vendor_signal'] = np.arange(len(frame)) % 5
        if corrupt:
            columns = [c for c in frame if c.startswith('perm_provider_unresolved__')]
            frame.loc[:, columns] = frame[columns].iloc[::-1].to_numpy()
        frame.attrs['selected_vendors'] = ['v1', 'v2']
        return frame.set_index('sample_id', drop=False)
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
    monkeypatch.setattr(pipeline_runner, 'build_feature_matrix_stage', feature_build)
    # Keep the real runner, enrichment/fusion, alignment, training stage and
    # classifier pipeline. Only model evaluation/reporting is replaced here;
    # its adapter still calls the real generic trainer and estimator spy.
    def synthetic_evaluate(features, labels, models=None, **kwargs):
        result = factory.train_model_factory(features, labels, use_smote=False)
        assert result['experiment_split_receipt']['plan_digest'] == es.ACTIVE.get().plan.sha256
        return {'random_forest': {'evaluation': {'macro_f1_score': .5, 'accuracy': .5},
                                 'metadata': {'params': {}}}}, []
    monkeypatch.setattr(pipeline_core, 'train_models', synthetic_evaluate)
    monkeypatch.setattr(pipeline_core, 'summarize_models', lambda results: 'random_forest')
    monkeypatch.setattr(pipeline_core, 'promote_default_model', lambda *a, **k: None)
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
    from obsidiandroid.pipeline import runner_stage_control
    monkeypatch.setattr(runner_stage_control, "finalize_run_manifest_stage", lambda **_kwargs: 0)

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

    if corrupt:
        assert result != 0
        assert fit_calls == []
    else:
        assert result == 0
        assert len(fit_calls) == 1
    assert es.ACTIVE.get() is None
    assert calls["ablation"] == 0
    assert calls["permission"] == 0

