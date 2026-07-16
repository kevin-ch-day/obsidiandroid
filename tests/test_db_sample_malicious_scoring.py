"""Tests for trusted-engine malicious-score query helpers."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.database import db_fetch_av_engine_raw_results as raw_fetcher
from obsidiandroid.database import db_sample_malicious_scoring as scoring
from obsidiandroid.database import db_av_engine_detection_totals as detection_totals
from obsidiandroid.matrix import enrich_malicious_scores


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


def test_scoped_malicious_score_query_uses_one_selected_sample_cte() -> None:
    sql = scoring._build_malicious_score_query(  # pylint: disable=protected-access
        ["avast", "alibaba"],
        5,
        sample_ids=[9, 2, 9],
    )

    assert "WITH selected_samples AS" in sql
    assert "WHERE sample_id IN (%s, %s)" in sql
    assert sql.count("INNER JOIN selected_samples AS selected") == 2
    assert "verdict_row.sample_id AS sample_id" in sql


def test_scoped_score_fetch_binds_unique_sorted_cohort_ids(monkeypatch) -> None:
    monkeypatch.setattr(scoring, "_get_normalized_trusted_engines", lambda: ["avast"])
    monkeypatch.setattr(scoring, "_filter_valid_engine_columns", lambda _engines: ["avast"])
    captured: dict[str, object] = {}

    def fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["params"] = kwargs.get("params")
        return ["sample_id"], [(2,)]

    monkeypatch.setattr(scoring.db_engine, "execute_query", fake_execute_query)

    rows, columns = scoring.get_sample_malicious_score(sample_ids=[9, 2, 9])

    assert columns == ["sample_id"]
    assert rows == [(2,)]
    assert captured["params"] == [2, 9]
    assert "WITH selected_samples AS" in str(captured["query"])


def test_score_enrichment_scopes_fetch_to_matrix_sample_ids(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch(sample_ids=None):
        captured["sample_ids"] = sample_ids
        return pd.DataFrame()

    monkeypatch.setattr(enrich_malicious_scores, "fetch_malicious_score_table", fake_fetch)
    matrix = pd.DataFrame({"sample_id": [4, 2], "engine_a": [1, 0]})

    out = enrich_malicious_scores.apply_score_enrichment(matrix)

    assert out is matrix
    assert captured["sample_ids"] == [4, 2]


def test_score_enrichment_merges_scores_without_mutating_matrix(monkeypatch) -> None:
    matrix = pd.DataFrame({"sample_id": [4, 2], "engine_a": [1, 0]})
    score_df = pd.DataFrame({"sample_id": [2, 4], "malicious_count": [3, 7]})
    monkeypatch.setattr(
        enrich_malicious_scores,
        "fetch_malicious_score_table",
        lambda sample_ids: score_df,
    )
    monkeypatch.setattr(
        enrich_malicious_scores.enrich_score_features,
        "add_derived_score_features",
        lambda frame: frame,
    )

    out = enrich_malicious_scores.apply_score_enrichment(matrix)

    assert out is not matrix
    assert out["malicious_count"].tolist() == [7, 3]
    assert "malicious_count" not in matrix.columns
    assert "_merge" not in out.columns


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


def test_scoped_engine_totals_query_joins_selected_samples() -> None:
    union_sql = detection_totals._build_union_sql(  # pylint: disable=protected-access
        ["google", "avast"],
        restrict_to_selected_samples=True,
    )

    assert union_sql.count("INNER JOIN selected_samples AS selected") == 2
    assert "verdict_row.`google`" in union_sql


def test_scoped_engine_totals_binds_unique_sorted_cohort_ids(monkeypatch) -> None:
    monkeypatch.setattr(detection_totals, "_get_valid_engine_list", lambda: ["google"])
    captured: dict[str, object] = {}

    def fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["params"] = kwargs.get("params")
        return pd.DataFrame({"engine_name": ["google"]})

    monkeypatch.setattr(detection_totals.db_engine, "execute_query", fake_execute_query)

    out = detection_totals.get_engine_detection_totals(sample_ids=[9, 2, 9])

    assert out["engine_name"].tolist() == ["google"]
    assert captured["params"] == [2, 9]
    assert "WITH selected_samples AS" in str(captured["query"])


def test_family_name_hits_regex_uses_current_family_taxonomy_and_aliases() -> None:
    regex = detection_totals._family_name_hits_regex()  # pylint: disable=protected-access

    assert "crocodilus" in regex
    assert "zanubis" in regex
    assert "flu-bot" in regex
    assert "gold digger" in regex
