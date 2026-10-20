"""Opt-in requirement that training samples carry both AV and permission evidence."""

from __future__ import annotations

import pandas as pd
import pytest

from config import app_config
from obsidiandroid.modeling import modality_requirement, pipeline_core
from obsidiandroid.pipeline import runtime_policy, stage_ablation


def _pool() -> tuple[pd.DataFrame, pd.Series]:
    ids = [1, 2, 3, 4, 5]
    features = pd.DataFrame({"f": [0.1, 0.2, 0.3, 0.4, 0.5]}, index=ids)
    labels = pd.Series(["A", "A", "B", "B", "B"], index=ids, name="family_id")
    return features, labels


@pytest.fixture()
def _modalities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_AV_DETECTION_SAMPLE_IDS", {1, 2, 3, 5}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PERMISSION_PRESENT_SAMPLE_IDS", {1, 3, 4, 5}, raising=False)


def test_default_leaves_training_pool_unchanged(monkeypatch, _modalities) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", False, raising=False)
    features, labels = _pool()
    out_features, out_labels, dropped = modality_requirement.apply_modality_requirement(features, labels)
    assert out_features is features and out_labels is labels and dropped == 0


def test_requirement_keeps_samples_with_av_detections_and_permissions(monkeypatch, _modalities) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", True, raising=False)
    features, labels = _pool()
    out_features, out_labels, dropped = modality_requirement.apply_modality_requirement(features, labels)
    assert list(out_features.index) == [1, 3, 5]
    assert list(out_labels.index) == [1, 3, 5]
    assert dropped == 2


def test_requirement_fails_closed_without_modality_evidence(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_AV_DETECTION_SAMPLE_IDS", None, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PERMISSION_PRESENT_SAMPLE_IDS", {1}, raising=False)
    features, labels = _pool()
    with pytest.raises(ValueError, match="AV detection"):
        modality_requirement.apply_modality_requirement(features, labels)


def test_permission_presence_counts_any_positive_permission_column() -> None:
    frame = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "perm__android_permission_internet": [1, 0, 0],
            "perm_grp__sms_telephony_count": [0, 0, 2],
            "perm__total_count": [0, 0, 0],
        }
    )
    assert modality_requirement.permission_present_sample_ids(frame) == {1, 3}


def test_av_presence_reads_detection_matrix_sample_ids() -> None:
    results = {"binary_matrix": pd.DataFrame({"sample_id": [7, 8], "engine_a": [1, 0]})}
    assert modality_requirement.av_detection_sample_ids(results) == {7, 8}
    assert modality_requirement.av_detection_sample_ids({}) is None


def _capture_support_floor(monkeypatch, module) -> list[list[int]]:
    seen: list[list[int]] = []

    def fake_support(**kwargs):
        seen.append(list(kwargs["features_df"].index))
        return kwargs["features_df"], kwargs["labels_df"], 0, 0, []

    monkeypatch.setattr(module.distribution_reporter, "apply_min_family_support", fake_support)
    return seen


def test_ablation_pool_applies_requirement_before_support_floor(monkeypatch, _modalities) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", True, raising=False)
    features, labels = _pool()
    monkeypatch.setattr(stage_ablation.pipeline_core, "align_data", lambda *_a, **_k: (features, labels))
    seen = _capture_support_floor(monkeypatch, stage_ablation)
    stage_ablation._prepare_training_inputs(features, pd.DataFrame())  # pylint: disable=protected-access
    assert seen == [[1, 3, 5]]


def test_headline_pool_applies_requirement_before_support_floor(monkeypatch, tmp_path, _modalities) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "membership_gate", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    features, labels = _pool()
    monkeypatch.setattr(pipeline_core, "align_data", lambda *_a, **_k: (features, labels))
    monkeypatch.setattr(
        pipeline_core.distribution_reporter, "print_family_distribution", lambda *_a, **_k: None
    )
    seen = _capture_support_floor(monkeypatch, pipeline_core)
    monkeypatch.setattr(pipeline_core, "train_models", lambda *_a, **_k: ({}, []))
    pipeline_core.run_classifier_pipeline(
        features_df=features, samples_df=pd.DataFrame(), save_model=False, models=["random_forest"]
    )
    assert seen == [[1, 3, 5]]


def test_profile_option_defaults_off_and_is_run_scoped() -> None:
    assert runtime_policy.resolve_require_both_modalities({}) is False
    assert runtime_policy.resolve_require_both_modalities(
        {"cohort_gates": {"require_vendor_and_permission": True}}
    ) is True
    keys = runtime_policy.build_mutable_config_keys()
    assert {"RUNTIME_REQUIRE_BOTH_MODALITIES", "RUNTIME_AV_DETECTION_SAMPLE_IDS",
            "RUNTIME_PERMISSION_PRESENT_SAMPLE_IDS"} <= keys


def test_headline_pool_fails_loudly_when_receipts_are_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_AV_DETECTION_SAMPLE_IDS", None, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PERMISSION_PRESENT_SAMPLE_IDS", None, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path), raising=False)
    features, labels = _pool()
    monkeypatch.setattr(pipeline_core, "align_data", lambda *_a, **_k: (features, labels))
    monkeypatch.setattr(
        pipeline_core.distribution_reporter, "print_family_distribution", lambda *_a, **_k: None
    )
    monkeypatch.setattr(pipeline_core, "train_models", lambda *_a, **_k: ({}, []))
    with pytest.raises(ValueError, match="AV detection"):
        pipeline_core.run_classifier_pipeline(
            features_df=features, samples_df=pd.DataFrame(), save_model=False, models=["random_forest"]
        )


def test_permission_presence_reads_source_aware_tokens_but_not_missing_flags() -> None:
    frame = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "perm_provider__" + "a" * 64: [1, 0, 0, 0],
            "perm_status__has_manifest_parse": [0, 1, 0, 0],
            "perm_status__provider_missing": [0, 0, 1, 1],
            "perm_status__manifest_missing": [0, 0, 1, 1],
            "perm_status__provider_reported_unresolved_count": [0, 0, 0, 3],
        }
    )
    assert modality_requirement.permission_present_sample_ids(frame) == {1, 2, 4}


def test_av_presence_prefers_the_enriched_matrix_used_by_coverage_audit() -> None:
    results = {
        "enriched_matrix": pd.DataFrame({"sample_id": [7]}),
        "binary_matrix": pd.DataFrame({"sample_id": [7, 8]}),
    }
    assert modality_requirement.av_detection_sample_ids(results) == {7}


def test_headline_records_modality_survivors_for_lineage(monkeypatch, tmp_path, _modalities) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path), raising=False)
    features, labels = _pool()
    monkeypatch.setattr(pipeline_core, "align_data", lambda *_a, **_k: (features, labels))
    monkeypatch.setattr(
        pipeline_core.distribution_reporter, "print_family_distribution", lambda *_a, **_k: None
    )
    _capture_support_floor(monkeypatch, pipeline_core)
    monkeypatch.setattr(pipeline_core, "train_models", lambda *_a, **_k: ({}, []))
    pipeline_core.run_classifier_pipeline(
        features_df=features, samples_df=pd.DataFrame(), save_model=False, models=["random_forest"]
    )
    assert sorted(app_config.RUNTIME_MODALITY_REQUIREMENT_SAMPLE_IDS) == [1, 3, 5]
