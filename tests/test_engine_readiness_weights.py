"""Config wiring and normalization helpers for ML Readiness Score."""

from __future__ import annotations

import pandas as pd

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
