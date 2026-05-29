"""Tests for trusted-engine malicious-score query helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.database import db_fetch_av_engine_raw_results as raw_fetcher
from obsidiandroid.database import db_sample_malicious_scoring as scoring
from obsidiandroid.database import db_av_engine_detection_totals as detection_totals


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


def test_filter_valid_engine_columns_skips_auxiliary_androguard_without_warning(monkeypatch) -> None:
    monkeypatch.setattr(scoring, "get_existing_result_columns", lambda: {"sample_id", "avast"})

    warnings: list[str] = []
    debug: list[str] = []
    monkeypatch.setattr(scoring.du, "print_warning", lambda msg: warnings.append(str(msg)))
    monkeypatch.setattr(scoring.du, "print_debug", lambda msg: debug.append(str(msg)))

    out = scoring._filter_valid_engine_columns(["avast", "androguard"])  # pylint: disable=protected-access

    assert out == ["avast"]
    assert not any("Trusted engine 'androguard'" in msg for msg in warnings)
    assert any("Auxiliary analysis source 'androguard'" in msg for msg in debug)


def test_filter_valid_engine_columns_normalizes_auxiliary_variants(monkeypatch) -> None:
    monkeypatch.setattr(scoring, "get_existing_result_columns", lambda: {"sample_id", "avast"})

    warnings: list[str] = []
    debug: list[str] = []
    monkeypatch.setattr(scoring.du, "print_warning", lambda msg: warnings.append(str(msg)))
    monkeypatch.setattr(scoring.du, "print_debug", lambda msg: debug.append(str(msg)))

    out = scoring._filter_valid_engine_columns(["avast", "AndroGuard", "androguard "])  # pylint: disable=protected-access

    assert out == ["avast"]
    assert warnings == []
    assert debug.count(
        "[SKIP] Auxiliary analysis source 'androguard' is not modeled as a wide vendor verdict column."
    ) == 2


def test_get_normalized_trusted_engines_canonicalizes_case_and_spacing(monkeypatch) -> None:
    monkeypatch.setattr(
        scoring,
        "get_active_trusted_engines",
        lambda: [" Trend-Micro ", "AndroGuard", "ESET_NOD32"],
    )

    assert scoring._get_normalized_trusted_engines() == [  # pylint: disable=protected-access
        "trend_micro",
        "androguard",
        "eset_nod32",
    ]


def test_union_sql_nulls_non_detection_tokens() -> None:
    sql = detection_totals._build_union_sql(["google"])  # pylint: disable=protected-access

    assert "WHEN `google` IS NULL" in sql
    assert "'type-unsupported'" in sql
    assert "THEN NULL" in sql
    assert "ELSE `google`" in sql


def test_engine_stats_query_counts_positive_non_benign_detections() -> None:
    sql = detection_totals._build_engine_stats_query("SELECT 'google' AS engine_name, 'Detected' AS result")  # pylint: disable=protected-access

    assert "SUM(" in sql
    assert "melted.result IS NOT NULL" in sql
    assert "NOT LOWER(TRIM(melted.result)) REGEXP 'benign|clean|safe|trusted|approved|verified|whitelist'" in sql
    assert "AS malicious_count" in sql
    assert "AS threat_signal_score" in sql
    assert "AS unknown_count" in sql


def test_family_name_hits_regex_uses_current_family_taxonomy_and_aliases() -> None:
    regex = detection_totals._family_name_hits_regex()  # pylint: disable=protected-access

    assert "crocodilus" in regex
    assert "zanubis" in regex
    assert "flu-bot" in regex
    assert "gold digger" in regex
