"""Tests for trusted-engine malicious-score query helpers."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.database import db_fetch_av_engine_raw_results as raw_fetcher
from obsidiandroid.database import db_sample_malicious_scoring as scoring


def test_build_union_sql_treats_non_detection_tokens_as_undetected() -> None:
    sql = scoring.build_union_sql(["avast"])

    assert "TRIM(LOWER(`avast`)) IN (" in sql
    assert "'undetected'" in sql
    assert "'type-unsupported'" in sql
    assert "'clean'" in sql
    assert "ELSE 'malicious'" in sql


def test_build_malicious_score_query_counts_only_malicious_rows() -> None:
    sql = scoring._build_malicious_score_query(["avast", "alibaba"], 5)  # pylint: disable=protected-access

    assert "SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) AS malicious_engines" in sql
    assert "HAVING total_engines >= 5" in sql
    assert "ELSE 'No Consensus'" in sql


def test_fetch_av_results_drops_legacy_optional_metadata_columns() -> None:
    samples_df = pd.DataFrame({"sample_id": [1, 2]})
    raw_df = pd.DataFrame(
        [
            {
                "sample_id": 1,
                "updated_at": "2026-05-10 00:00:00",
                "total_engines": 2,
                "malicious": 1,
                "avast": "Trojan.Android",
            },
            {
                "sample_id": 2,
                "updated_at": "2026-05-10 00:00:01",
                "total_engines": 2,
                "malicious": 0,
                "avast": "undetected",
            },
        ]
    )

    def fake_execute_query(**_kwargs):
        return raw_df

    original = raw_fetcher.db_engine.execute_query
    raw_fetcher.db_engine.execute_query = fake_execute_query
    try:
        out = raw_fetcher.fetch_av_engine_results_for_samples(samples_df, verbose=False)
    finally:
        raw_fetcher.db_engine.execute_query = original

    assert out.columns.tolist() == ["sample_id", "avast"]
    assert out["sample_id"].tolist() == [1, 2]
