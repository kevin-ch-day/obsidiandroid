"""Tests for compact runtime run-summary payload and terminal echo."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.orchestration import runtime_reporting


def test_build_run_summary_payload_includes_engine_exclusion_reason_counts(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_VENDOR_FALLBACK_USED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_VENDOR_FALLBACK_ADDED_COUNT", 0, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_K_REQUESTED", 8, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EFFECTIVE_TOP_K", 8, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_NEAR_MISS", 2, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_NON_STANDARD_FEATURES", False, raising=False)

    samples_df = pd.DataFrame({"family_canonical": ["a", "a", "b"]})
    payload = runtime_reporting.build_run_summary_payload(
        run_id="rid",
        profile_id="p1",
        samples_df=samples_df,
        model_results=None,
        top_model=None,
        manifest_context={
            "included_engine_count": 56,
            "engine_count_observed": 93,
            "engine_count_canonical": 93,
            "engine_exclusion_reason_counts": {"BELOW_THRESHOLD": 25, "LOW_COVERAGE": 12},
        },
    )

    assert payload["engine_count_near_miss"] == 2
    assert payload["engine_exclusion_reason_counts"] == {
        "BELOW_THRESHOLD": 25,
        "LOW_COVERAGE": 12,
    }


def test_export_and_print_run_summary_emits_top_exclusion_reasons(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "output" / "runs" / "rid" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        runtime_reporting,
        "runtime_diagnostics_dir",
        lambda: diagnostics_dir,
    )
    monkeypatch.setattr(runtime_reporting.oh, "run_diagnostics_should_omit_latest_duplicate", lambda: False)

    captured_stats: list[tuple[str, object]] = []
    monkeypatch.setattr(runtime_reporting.du, "print_section", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runtime_reporting.du,
        "print_stat",
        lambda label, value, *_a, **_k: captured_stats.append((str(label), value)),
    )

    runtime_reporting.export_and_print_run_summary(
        payload={
            "run_id": "rid",
            "engine_count_observed": 93,
            "engine_count_canonical": 93,
            "engine_count_included_after_gating": 56,
            "engine_count_near_miss": 2,
            "engine_exclusion_reason_counts": {"BELOW_THRESHOLD": 25, "LOW_COVERAGE": 12},
            "engine_count_requested_top_k": 8,
            "effective_top_k": 8,
            "fallback_used": False,
            "fallback_added_count": 0,
            "non_standard_features": False,
            "unknown_rate": 0.0,
            "missing_package_rate": 0.0,
            "macro_f1": 0.88,
            "n_families": 34,
            "top_family_share": 0.88,
        },
        artifact_list=[],
        echo_terminal=True,
    )

    stat_map = dict(captured_stats)
    assert stat_map["Excluded Near-Miss Engines"] == 2
    assert stat_map["Top Exclusion Reasons"] == "BELOW_THRESHOLD=25, LOW_COVERAGE=12"

def test_count_evaluated_models_ignores_family_tier_scope_rows() -> None:
    model_results = {
        "random_forest": {"evaluation": {"macro_f1_score": 0.9}},
        "xgboost": {"evaluation": {"macro_f1_score": 0.8}},
        "logistic_regression": {"evaluation": {"macro_f1_score": 0.7}},
        "family_tier_rows": [{"model": "random_forest"}] * 9,
    }
    model_summary = {
        "model_rows": [
            {"model": "random_forest"},
            {"model": "xgboost"},
            {"model": "logistic_regression"},
        ],
        "family_tier_model_rows": [{"model": "random_forest"}] * 5,
    }

    assert runtime_reporting.count_evaluated_models(model_results, model_summary) == 3
