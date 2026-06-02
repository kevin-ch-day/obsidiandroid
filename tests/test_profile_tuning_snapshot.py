"""Tests for manifest-derived pipeline profile tuning display."""

from __future__ import annotations

from pathlib import Path

import obsidiandroid.cli.startup_menu_run_overview as run_overview
from obsidiandroid.cli.startup_menu_run_overview import print_profile_tuning_from_manifest


def test_print_profile_tuning_from_manifest_shows_cohort_and_flags(capsys) -> None:
    manifest = {
        "config_hash": "abcdef0123456789",
        "evidence_mode": False,
        "paper_mode": {"resolved_value": False, "source": "profile_default"},
        "k_requested": 8,
        "effective_top_k": 8,
        "vendor_fallback_used": False,
        "profile_params": {
            "profile_id": "test_prof",
            "evidence_mode": False,
            "type_slug_filter": None,
            "cohort_gates": {
                "min_samples_per_family": 5,
                "require_mapped_family": True,
                "exclude_families": ["A", "B"],
            },
            "dataset_filters": {"mode": "malicious_only"},
            "top_k_requested": 8,
            "allow_adaptive_top_k": True,
            "allow_vendor_fallback_for_width": False,
            "exclude_unknown_from_main_results": False,
            "feature_flags": {
                "enable_permission_features": True,
                "confusion_matrix_export_mode": "headline_only",
            },
            "parser_overrides": {},
            "runtime_overrides": {"ENABLE_ABLATION_EXPERIMENTS": True},
            "model_list": ["random_forest"],
        },
    }
    print_profile_tuning_from_manifest(manifest)
    out = capsys.readouterr().out
    assert "test_prof" in out
    assert "Cohort gates" in out
    assert "n>=5" in out
    assert "malicious_only" in out
    assert "enable_permission_features" in out
    assert "ENABLE_ABLATION_EXPERIMENTS" in out
    assert "random_forest" in out
    assert "Evidence mode (manifest)" in out
    assert "Publication-ready mode (manifest)" in out
    assert "profile_default" in out
    assert "Top-k (requested / effective)" in out
    assert "Top-k policy" in out
    assert "Feature flags" in out
    assert "Parser overrides" in out
    assert "Runtime overrides" in out
    assert "Models" in out


def test_print_profile_tuning_from_manifest_missing_profile_params(capsys) -> None:
    print_profile_tuning_from_manifest({"run_id": "x"})
    out = capsys.readouterr().out
    assert "No profile_params" in out


def test_show_profile_tuning_snapshot_prefers_canonical_run_manifest_path(monkeypatch) -> None:
    stats: list[tuple[str, object]] = []

    monkeypatch.setattr(
        run_overview,
        "build_operator_state",
        lambda: {
            "manifest_payload": {
                "run_id": "r_can",
                "profile_params": {"profile_id": "dev_smoke"},
                "paper_mode": {"resolved_value": False, "source": "profile"},
            },
            "resolved_run_id": "r_can",
            "manifest_path": Path("/tmp/output/diagnostics/run_manifest.latest.json"),
            "canonical_manifest_path": Path("/tmp/output/runs/r_can/run_manifest.json"),
        },
    )
    monkeypatch.setattr(run_overview.du, "print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        run_overview.du,
        "print_stat",
        lambda label, value, *args, **kwargs: stats.append((str(label), value)),
    )
    monkeypatch.setattr(run_overview.du, "print_info", lambda *_args, **_kwargs: None)

    result = run_overview.show_profile_tuning_snapshot()

    assert result == 0
    assert ("Resolved run ID", "r_can") in stats
    assert ("Manifest path", "/tmp/output/runs/r_can/run_manifest.json") in stats
