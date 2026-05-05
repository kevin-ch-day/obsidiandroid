"""Unit tests for cross-run app_config cleanup (pipeline / pytest isolation)."""

from __future__ import annotations

from config import app_config
from obsidiandroid.modeling import model_trainer_factory as mtf
from obsidiandroid.pipeline import runtime_policy

CROSS_RUN_ARTIFACT_POINTERS = runtime_policy.CROSS_RUN_ARTIFACT_POINTERS
build_mutable_config_keys = runtime_policy.build_mutable_config_keys
clear_cross_run_artifact_path_pointers = runtime_policy.clear_cross_run_artifact_path_pointers


def test_clear_cross_run_artifact_path_pointers_resets_documented_keys() -> None:
    setattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", "/tmp/stale_overlay.csv")
    setattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "/tmp/stale_perm.csv")
    setattr(app_config, "RUNTIME_FEATURE_COLUMN_SURVIVAL_CSV", "/tmp/stale_feat.csv")
    setattr(app_config, "RUNTIME_SPLIT_METADATA", {"split_audit_path": "/tmp/stale_split.csv"})
    setattr(app_config, "RUNTIME_SPLIT_HASH", "abc")
    setattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "/tmp/stale_audit.csv")

    clear_cross_run_artifact_path_pointers()

    assert getattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", None) == ""
    assert getattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", None) == ""
    assert getattr(app_config, "RUNTIME_FEATURE_COLUMN_SURVIVAL_CSV", None) == ""
    assert getattr(app_config, "RUNTIME_SPLIT_METADATA", "sentinel") is None
    assert getattr(app_config, "RUNTIME_SPLIT_HASH", None) == ""
    assert getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", None) == ""


def test_mutable_config_keys_covers_artifact_pointers() -> None:
    keys = build_mutable_config_keys()
    assert set(CROSS_RUN_ARTIFACT_POINTERS).issubset(keys)
    assert "RUNTIME_TRAINING_STATE" in keys


def test_reset_runtime_training_caches_clears_run_entries(monkeypatch) -> None:
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TRAINING_STATE",
        {"runs": {"prior_run": {"split_cache": {"k": 1}}}},
        raising=False,
    )
    mtf.reset_runtime_training_caches()
    state = getattr(app_config, "RUNTIME_TRAINING_STATE", None)
    assert isinstance(state, dict)
    assert state.get("runs") == {}
