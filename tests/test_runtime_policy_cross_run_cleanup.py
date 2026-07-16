"""Unit tests for cross-run app_config cleanup (pipeline / pytest isolation)."""

from __future__ import annotations

from pathlib import Path

from config import app_config
from obsidiandroid.modeling import model_trainer_factory as mtf
from obsidiandroid.pipeline import runtime_policy
from obsidiandroid.reporting import export_manager

CROSS_RUN_ARTIFACT_POINTERS = runtime_policy.CROSS_RUN_ARTIFACT_POINTERS
build_mutable_config_keys = runtime_policy.build_mutable_config_keys
clear_cross_run_artifact_path_pointers = runtime_policy.clear_cross_run_artifact_path_pointers


def test_clear_cross_run_artifact_path_pointers_resets_documented_keys() -> None:
    setattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", "/tmp/stale_overlay.csv")
    setattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "/tmp/stale_perm.csv")
    setattr(app_config, "RUNTIME_FEATURE_COLUMN_SURVIVAL_CSV", "/tmp/stale_feat.csv")
    setattr(app_config, "RUNTIME_PERMISSION_BUNDLE_DIR", "/tmp/stale_bundle")
    setattr(app_config, "RUNTIME_PERMISSION_BUNDLE_ZIP", "/tmp/stale_bundle.zip")
    setattr(app_config, "RUNTIME_PERMISSION_BUNDLE_LATEST_DIR", "/tmp/stale_bundle_latest")
    setattr(app_config, "RUNTIME_PERMISSION_FUSE_AUDIT", {"stale": True})
    setattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", "/tmp/stale_dup.csv")
    setattr(app_config, "RUNTIME_SPLIT_METADATA", {"split_audit_path": "/tmp/stale_split.csv"})
    setattr(app_config, "RUNTIME_SPLIT_HASH", "abc")
    setattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "/tmp/stale_audit.csv")
    setattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", {"split_hash": "x"})
    setattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "fh")
    setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", {"k": "v"})
    export_manager._CONSOLIDATED_RUNTIME_TARGET = Path("/tmp/stale_workbook.xlsx")

    clear_cross_run_artifact_path_pointers()

    assert getattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", None) == ""
    assert getattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", None) == ""
    assert getattr(app_config, "RUNTIME_FEATURE_COLUMN_SURVIVAL_CSV", None) == ""
    assert getattr(app_config, "RUNTIME_PERMISSION_BUNDLE_DIR", None) == ""
    assert getattr(app_config, "RUNTIME_PERMISSION_BUNDLE_ZIP", None) == ""
    assert getattr(app_config, "RUNTIME_PERMISSION_BUNDLE_LATEST_DIR", None) == ""
    assert getattr(app_config, "RUNTIME_PERMISSION_FUSE_AUDIT", None) == {}
    assert getattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", None) == ""
    assert getattr(app_config, "RUNTIME_SPLIT_METADATA", "sentinel") is None
    assert getattr(app_config, "RUNTIME_SPLIT_HASH", None) == ""
    assert getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", None) == ""
    assert getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", "sentinel") is None
    assert getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", None) == ""
    assert getattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", "sentinel") is None
    assert export_manager._CONSOLIDATED_RUNTIME_TARGET is None


def test_mutable_config_keys_covers_artifact_pointers() -> None:
    keys = build_mutable_config_keys()
    assert set(CROSS_RUN_ARTIFACT_POINTERS).issubset(keys)
    assert "RUNTIME_TRAINING_STATE" in keys
    assert {"FEATURE_TOP_K", "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", "AV_BINARY_FEATURE_ENGINE_SCOPE"}.issubset(keys)


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
