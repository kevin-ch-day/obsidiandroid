"""Config wiring and normalization helpers for ML Readiness Score."""

from __future__ import annotations

import pandas as pd
from pathlib import Path

from config import app_config

from obsidiandroid.evaluation import engine_scoring_summary as ess


def test_effective_readiness_weights_partial_override_renormalizes(monkeypatch):
    monkeypatch.setattr(
        app_config,
        "ENGINE_READINESS_SCORE_WEIGHTS",
        {"malicious_pct": 0.9, "coverage_pct": 0.9},  # threat_signal keeps DEFAULT
        raising=False,
    )
    w = ess._effective_readiness_weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert set(w.keys()) == {"coverage_pct", "malicious_pct", "threat_signal_score"}
    assert w["malicious_pct"] > w["threat_signal_score"]


def test_effective_readiness_weights_empty_dict_uses_defaults(monkeypatch):
    monkeypatch.setattr(app_config, "ENGINE_READINESS_SCORE_WEIGHTS", {}, raising=False)
    assert ess._effective_readiness_weights() == ess.DEFAULT_READINESS_WEIGHTS


def test_percentile_rank_ordering_and_bounds():
    ser = pd.Series([3.0, 1.0, 2.0])
    pr = ess._percentile_rank_scale(ser)
    assert pr.min() >= 0 and pr.max() <= 1
    # average-rank percentiles order with values
    assert pr.iloc[1] < pr.iloc[2] < pr.iloc[0]


def test_export_summary_log_compact_skips_table_and_emits_single_info(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(
        ess,
        "_resolve_summary_export_paths",
        lambda: (tmp_path / "engine_scoring_summary_log.txt", tmp_path / "engine_scoring_summary.csv"),
    )
    captured: list[str] = []
    monkeypatch.setattr(ess.du, "print_info", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(ess.du, "print_table", lambda *_a, **_k: captured.append("table"))

    df = pd.DataFrame(
        {
            "engine_name": ["a", "b", "c", "d", "e", "f"],
            "ML Readiness Score": [99.0, 97.0, 95.0, 93.0, 91.0, 89.0],
            "Tier Label": ["Tier 1 (High)"] * 6,
            "contributor_flag": [1, 1, 1, 1, 1, 1],
        }
    )
    ess._export_summary_log(df)

    assert "table" not in captured
    assert any("Top engines by ML Readiness Score" in msg for msg in captured)


def test_log_summary_stats_compact_skips_statistical_ranges(monkeypatch):
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    calls: list[str] = []
    monkeypatch.setattr(ess.du, "print_metric_summary", lambda *_a, **_k: calls.append("metric_summary"))
    monkeypatch.setattr(ess.du, "print_statistical_range", lambda *_a, **_k: calls.append("range"))
    monkeypatch.setattr(ess.du, "print_tier_distribution", lambda *_a, **_k: calls.append("tier_distribution"))
    monkeypatch.setattr(ess.du, "print_subheader", lambda *_a, **_k: None)

    df = pd.DataFrame(
        {
            "ML Readiness Score": [10.0, 20.0, 30.0],
            "malicious_pct": [1.0, 2.0, 3.0],
            "coverage_pct": [4.0, 5.0, 6.0],
            "threat_signal_score": [7.0, 8.0, 9.0],
            "Detection Tier": [1, 2, 3],
            "Tier Label": ["Tier 1 (High)", "Tier 2 (Moderate)", "Tier 3 (Low)"],
            "iqr_flag": [0, 0, 0],
        }
    )
    ess._log_summary_stats(df)

    assert calls == ["metric_summary", "tier_distribution"]
