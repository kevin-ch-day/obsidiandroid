"""Tests for AV verdict query caching behavior."""

from __future__ import annotations

from config import app_config

from obsidiandroid.database import db_av_engine_verdicts


def _mock_query_result():
    cols = [
        "record_id",
        "sample_id",
        "total_engines",
        "malicious",
        "suspicious",
        "undetected",
        "harmless",
        "engine_a",
        "engine_b",
    ]
    rows = [
        (1, 100, 2, 1, 0, 1, 0, "Trojan.Android", None),
        (2, 200, 2, 0, 1, 1, 0, None, "Adware"),
    ]
    return cols, rows


def test_verdict_query_cache_reuses_results_for_same_sample_set(monkeypatch) -> None:
    """Same sample universe should hit cache even if input order differs."""
    calls = {"count": 0}

    def fake_execute_query(*_args, **_kwargs):
        calls["count"] += 1
        return _mock_query_result()

    db_av_engine_verdicts._VERDICT_QUERY_CACHE.clear()  # pylint: disable=protected-access
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_AV_VERDICT_QUERY_CACHE", True, raising=False)
    monkeypatch.setattr(db_av_engine_verdicts.db_engine, "execute_query", fake_execute_query)

    df_a = db_av_engine_verdicts.fetch_verdicts_simple_ids([100, 200], verbose=False)
    df_b = db_av_engine_verdicts.fetch_verdicts_simple_ids([200, 100], verbose=False)

    assert calls["count"] == 1
    assert not df_a.empty
    assert not df_b.empty
    assert set(df_a["sample_id"].tolist()) == {100, 200}
    assert set(df_b["sample_id"].tolist()) == {100, 200}


def test_verdict_query_cache_disabled_in_paper_mode(monkeypatch) -> None:
    """Paper mode should bypass in-memory verdict caching."""
    calls = {"count": 0}

    def fake_execute_query(*_args, **_kwargs):
        calls["count"] += 1
        return _mock_query_result()

    db_av_engine_verdicts._VERDICT_QUERY_CACHE.clear()  # pylint: disable=protected-access
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_AV_VERDICT_QUERY_CACHE", True, raising=False)
    monkeypatch.setattr(db_av_engine_verdicts.db_engine, "execute_query", fake_execute_query)

    db_av_engine_verdicts.fetch_verdicts_simple_ids([100, 200], verbose=False)
    db_av_engine_verdicts.fetch_verdicts_simple_ids([100, 200], verbose=False)

    assert calls["count"] == 2
