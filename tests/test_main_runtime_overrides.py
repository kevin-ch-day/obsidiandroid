"""Tests for runtime override isolation and restoration in main pipeline runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
import pandas as pd

from config import app_config
import main
from obsidiandroid.cli import main_override_bridge
from obsidiandroid.pipeline import main_facade
from obsidiandroid.pipeline import runtime_policy


def test_runtime_overrides_are_restored_after_run(monkeypatch, tmp_path: Path) -> None:
    """Profile runtime overrides should not leak into later runs."""
    original_cv = bool(getattr(app_config, "ENABLE_CROSS_VALIDATION", True))
    original_perm = bool(getattr(app_config, "ENABLE_PERMISSION_FEATURES", True))
    original_snapshot = bool(getattr(app_config, "EXPORT_ANALYSIS_SNAPSHOT", True))
    original_dynamic = bool(getattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", False))
    original_parser_mapped = float(getattr(app_config, "PARSER_MAPPED_MIN_THRESHOLD", 0.30))

    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", str(tmp_path / "output" / "diagnostics"))
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "unit_restore_profile",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": True,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
            "parser_overrides": {
                "PARSER_MAPPED_MIN_THRESHOLD": 0.05,
            },
            "runtime_overrides": {
                "ENABLE_CROSS_VALIDATION": False,
                "EXPORT_ANALYSIS_SNAPSHOT": False,
                "ENABLE_PERMISSION_FEATURES": False,
            },
        },
    )
    monkeypatch.setattr(
        main,
        "load_and_prepare_samples",
        lambda **_kwargs: pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
    )

    result = main.run_pipeline(stop_after="samples", profile_ref="unit_restore_profile")

    assert result == 0
    assert bool(getattr(app_config, "ENABLE_CROSS_VALIDATION", True)) == original_cv
    assert bool(getattr(app_config, "ENABLE_PERMISSION_FEATURES", True)) == original_perm
    assert bool(getattr(app_config, "EXPORT_ANALYSIS_SNAPSHOT", True)) == original_snapshot
    assert bool(getattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", False)) == original_dynamic
    assert float(getattr(app_config, "PARSER_MAPPED_MIN_THRESHOLD", 0.30)) == original_parser_mapped


def test_stop_after_samples_writes_preflight_for_cohort_audit(monkeypatch, tmp_path: Path) -> None:
    """Samples-only runs should emit preflight_report.json even when evidence mode is off."""
    output_base = tmp_path / "output"
    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "EVIDENCE_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_base), raising=False)
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)

    def _fake_load(**_kwargs):
        df = pd.DataFrame(
            {
                "sample_id": [1],
                "sha256": ["a" * 64],
                "family_canonical": ["fam_a"],
                "type_slug": ["trojan"],
            }
        )
        df.attrs["cohort_gate_stats"] = {
            "total_candidates": 100,
            "governed_cohort_count": 1,
        }
        df.attrs["cohort_gate_rows"] = []
        return df

    monkeypatch.setattr(main, "load_and_prepare_samples", _fake_load)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "unit_samples_audit",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "evidence_mode": False,
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
        },
    )

    result = main.run_pipeline(stop_after="samples", profile_ref="unit_samples_audit")
    assert result == 0
    preflight_paths = list(output_base.rglob("preflight_report.json"))
    assert preflight_paths, "expected preflight_report.json under output tree"
    payload = json.loads(preflight_paths[0].read_text(encoding="utf-8"))
    assert payload.get("profile_id") == "unit_samples_audit"
    assert payload.get("status") == "stopped_after_samples"
    audit = payload.get("samples_stage_cohort_counts") or {}
    assert audit.get("cohort_sql_scope_row_count") == 100
    assert audit.get("cohort_prepared_row_count") == 1


def test_confusion_matrix_policy_keeps_random_forest_in_paper_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    run_id = "run123"
    cm_dir = output_root / "runs" / run_id / "conf_matrices"
    cm_dir.mkdir(parents=True, exist_ok=True)
    rf_path = cm_dir / "confusion_matrix_random_forest.png"
    xgb_path = cm_dir / "confusion_matrix_xgboost.png"
    rf_path.write_bytes(b"rf")
    xgb_path.write_bytes(b"xgb")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "CONFUSION_MATRIX_MODE", "primary_only", raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)

    main._apply_confusion_matrix_policy(run_id=run_id, top_model="xgboost")

    assert rf_path.exists()
    assert xgb_path.exists()


def test_stage_failure_finalizes_failed_run(monkeypatch, tmp_path: Path) -> None:
    """Expected stage failures should still finalize manifest context and preflight."""
    output_root = tmp_path / "output"
    captured: dict[str, object] = {}

    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)

    def _capture_finalize(**kwargs):
        captured["manifest_context"] = dict(kwargs["manifest_context"])
        return 0

    monkeypatch.setattr(main, "finalize_run_manifest_stage", _capture_finalize)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "unit_paper_locked",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "paper_locked": True,
            "paper_lock": {
                "contract_id": "unit_locked_contract",
                "expected_sample_count": 1,
                "expected_family_count": 1,
                "expected_type_count": 1,
                "sample_id_lock_status": "unavailable",
                "sample_id_lock_todo": "unit test count-only contract",
            },
            "evidence_mode": True,
            "evidence_perturbation_axes": ["min_malicious_detections"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
        },
    )
    monkeypatch.setattr(
        main,
        "load_and_prepare_samples",
        lambda **_kwargs: pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
    )
    monkeypatch.setattr(main, "run_av_analysis_stage", lambda **_kwargs: {})

    result = main.run_pipeline(profile_ref="malicious_temporal_stability")

    manifest_context = captured["manifest_context"]
    assert result == 1
    assert manifest_context["run_status"] == "failed"
    assert manifest_context["failed_stage"] == "av_pipeline"
    preflight_path = output_root / "runs" / str(manifest_context["run_id"]) / "diagnostics" / "preflight_report.json"
    payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"


def test_non_evidence_stage_failure_writes_preflight_and_failure_summary(monkeypatch, tmp_path: Path) -> None:
    """Ordinary failed runs should persist failure diagnostics even outside evidence mode."""
    output_root = tmp_path / "output"

    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "EVIDENCE_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "unit_non_evidence_failure",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "evidence_mode": False,
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
        },
    )
    monkeypatch.setattr(
        main,
        "load_and_prepare_samples",
        lambda **_kwargs: pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
    )
    monkeypatch.setattr(main, "run_av_analysis_stage", lambda **_kwargs: {})

    result = main.run_pipeline(profile_ref="unit_non_evidence_failure")

    assert result == 1
    preflight_paths = list(output_root.rglob("preflight_report.json"))
    assert preflight_paths, "expected preflight_report.json under output tree for failed run"
    failure_jsons = list(output_root.rglob("failure_summary.json"))
    assert failure_jsons, "expected failure_summary.json under output tree for failed run"
    payload = json.loads(failure_jsons[0].read_text(encoding="utf-8"))
    assert payload["stage"] == "av_pipeline"
    assert payload["recoverable_stage_failure"] is True


def test_locked_cohort_mismatch_finalizes_without_reraising(monkeypatch, tmp_path: Path) -> None:
    """Locked cohort mismatches should finalize as controlled failures in evidence mode."""
    output_root = tmp_path / "output"
    captured: dict[str, object] = {}

    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)

    def _capture_finalize(**kwargs):
        captured["manifest_context"] = dict(kwargs["manifest_context"])
        return 0

    monkeypatch.setattr(main, "finalize_run_manifest_stage", _capture_finalize)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "malicious_temporal_stability_locked",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "paper_locked": True,
            "paper_lock": {
                "contract_id": "unit_locked_contract",
                "expected_sample_count": 3,
                "expected_family_count": 2,
                "expected_type_count": 2,
                "sample_id_lock_status": "unavailable",
                "sample_id_lock_todo": "unit test count-only contract",
            },
            "evidence_mode": True,
            "evidence_perturbation_axes": ["min_malicious_detections"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
        },
    )
    monkeypatch.setattr(
        main,
        "load_and_prepare_samples",
        lambda **_kwargs: pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["fam_a", "fam_b"],
                "type_slug": ["banker", "banker"],
            }
        ),
    )

    result = main.run_pipeline(profile_ref="malicious_temporal_stability_locked")

    assert result == 1
    manifest_context = captured["manifest_context"]
    assert manifest_context["run_status"] == "failed"
    assert manifest_context["failed_stage"] == "samples"
    assert "[COHORT_LOCK]" in str(manifest_context["failure_reason"])
    contract = manifest_context["paper_cohort_contract"]
    assert contract["validation"]["status"] == "mismatch"
    assert "sample_count observed=2 expected=3" in contract["validation"]["mismatches"]


def test_unlocked_paper_profile_fails_early_with_locked_guidance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Publication-intended unlocked profiles should fail before the samples stage."""
    output_root = tmp_path / "output"
    captured: dict[str, object] = {}
    calls = {"samples_called": 0}

    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)

    def _capture_finalize(**kwargs):
        captured["manifest_context"] = dict(kwargs["manifest_context"])
        return 0

    def _samples_should_not_run(**_kwargs):
        calls["samples_called"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(main, "finalize_run_manifest_stage", _capture_finalize)
    monkeypatch.setattr(main, "load_and_prepare_samples", _samples_should_not_run)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "malicious_temporal_stability",
            "type_slug_filter": None,
            "cohort_gates": {
                "time_window_start_utc": "2020-01-01T00:00:00Z",
                "time_window_end_utc": "2026-01-01T00:00:00Z",
            },
            "model_list": ["logistic_regression"],
            "evidence_mode": True,
            "evidence_perturbation_axes": ["min_malicious_detections"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
        },
    )

    result = main.run_pipeline(profile_ref="malicious_temporal_stability")

    assert result == 1
    assert calls["samples_called"] == 0
    manifest_context = captured["manifest_context"]
    assert "Use 'malicious_temporal_stability_locked' instead." in str(manifest_context["failure_reason"])
    assert manifest_context["run_status"] == "failed"


def test_exploratory_profile_is_not_blocked_by_publication_lock(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Exploratory profiles should continue to run without paper_locked contracts."""
    output_root = tmp_path / "output"

    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)
    monkeypatch.setattr(main, "finalize_run_manifest_stage", lambda **_kwargs: 0)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "malicious_temporal_stability",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "evidence_mode": False,
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
        },
    )
    monkeypatch.setattr(
        main,
        "load_and_prepare_samples",
        lambda **_kwargs: pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
    )

    result = main.run_pipeline(stop_after="samples", profile_ref="malicious_temporal_stability")
    assert result == 0


def test_broad_current_profile_refuses_second_concurrent_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Broad current-corpus runs should fail early when another active peer run exists."""
    output_root = tmp_path / "output"
    captured: dict[str, object] = {}
    existing_run_root = output_root / "runs" / "existing_peer"
    existing_run_root.mkdir(parents=True, exist_ok=True)
    (existing_run_root / ".RUNNING").write_text(
        json.dumps(
            {
                "state": "running",
                "started_at_utc": "2026-06-01T00:00:00+00:00",
                "pid": 1,
                "hostname": "other-host",
                "run_id": "existing_peer",
                "profile_id": "android_malware_all_current",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "ENABLE_DB_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "EVIDENCE_MODE_LOCKED_VALUE", None, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(main, "DIAGNOSTICS_DIR", str(output_root / "diagnostics"))
    monkeypatch.setattr(main.runtime_logging, "start_runtime_logging", lambda _run_id: None)
    monkeypatch.setattr(main.runtime_logging, "stop_runtime_logging", lambda _ctx: None)

    def _capture_finalize(**kwargs):
        captured["manifest_context"] = dict(kwargs["manifest_context"])
        return 0

    monkeypatch.setattr(main, "finalize_run_manifest_stage", _capture_finalize)
    monkeypatch.setattr(
        main.profile_manager,
        "load_profile",
        lambda _ref: {
            "profile_id": "android_malware_all_current",
            "type_slug_filter": None,
            "cohort_gates": {},
            "model_list": ["logistic_regression"],
            "feature_flags": {
                "enable_dynamic_generic_vendor_parsers": False,
                "enable_sample_metadata_features": False,
                "enable_permission_features": False,
            },
            "runtime_overrides": {
                "ENABLE_CROSS_VALIDATION": False,
                "ENABLE_ABLATION_EXPERIMENTS": False,
            },
        },
    )

    def _samples_should_not_run(**_kwargs):
        raise AssertionError("samples stage should not run when active peer broad run exists")

    monkeypatch.setattr(main, "load_and_prepare_samples", _samples_should_not_run)

    result = main.run_pipeline(profile_ref="android_malware_all_current")

    assert result == 1
    manifest_context = captured["manifest_context"]
    assert manifest_context["run_status"] == "failed"
    assert manifest_context["failed_stage"] == "preflight"
    assert "Another active broad current-corpus run is already in progress" in str(
        manifest_context["failure_reason"]
    )

def test_enforce_paper_perturbation_axes_rejects_invalid_axis() -> None:
    """Evidence mode should fail when profile declares a non-approved perturbation axis."""
    profile = {
        "profile_id": "repro_bad",
        "evidence_perturbation_axes": ["min_malicious_detections", "random_undersampling"],
    }
    with pytest.raises(ValueError, match="Invalid perturbation axis"):
        runtime_policy.enforce_paper_perturbation_axes(profile=profile, paper_mode=True)


def test_enforce_paper_perturbation_axes_accepts_locked_axes() -> None:
    """Evidence mode should accept approved perturbation axes."""
    profile = {
        "profile_id": "malicious_temporal_stability",
        "evidence_perturbation_axes": [
            "min_malicious_detections",
            "family_cap",
            "exclude_unknown_type_slug",
        ],
    }
    runtime_policy.enforce_paper_perturbation_axes(profile=profile, paper_mode=True)


def test_from_main_or_returns_default_when_main_missing(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "main", raising=False)
    assert main_facade.from_main_or("anything", 42) == 42


def test_from_main_or_prefers_main_attribute(monkeypatch) -> None:
    class _FakeMain:
        marker = "patched"

    monkeypatch.setitem(sys.modules, "main", _FakeMain())
    assert main_facade.from_main_or("marker", "default") == "patched"


def test_resolve_main_override_returns_default_when_main_missing(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "main", raising=False)
    assert main_override_bridge.resolve_main_override("anything", 42) == 42


def test_resolve_main_override_prefers_main_attribute(monkeypatch) -> None:
    class _FakeMain:
        marker = "patched"

    monkeypatch.setitem(sys.modules, "main", _FakeMain())
    assert main_override_bridge.resolve_main_override("marker", "default") == "patched"
