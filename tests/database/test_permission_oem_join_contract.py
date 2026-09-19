from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.database import permission_contracts
from obsidiandroid.database.permission_contracts import (
    aosp_dictionary_join_predicate,
    authority_fact_join,
    catalog_identity_expr,
    oem_dictionary_join_predicate,
    token_alias_join,
    unknown_dictionary_join_predicate,
    vt_current_join,
)


def test_oem_dictionary_join_is_exact_token_and_resolved_vendor() -> None:
    predicate = oem_dictionary_join_predicate(
        observation_alias="ops",
        oem_alias="o",
    )
    assert predicate == (
        "BINARY o.permission_string = BINARY ops.permission_string"
        " AND o.vendor_id IS NOT NULL"
    )


def test_oem_dictionary_join_rejects_unsafe_aliases() -> None:
    with pytest.raises(ValueError, match="invalid SQL alias"):
        oem_dictionary_join_predicate(observation_alias="ops; DROP", oem_alias="o")
    with pytest.raises(ValueError, match="invalid SQL alias"):
        oem_dictionary_join_predicate(observation_alias="ops", oem_alias="")


def test_aosp_and_unknown_joins_are_exact_token_bytes() -> None:
    aosp = aosp_dictionary_join_predicate(raw_expr="ops.permission_string")
    assert "BINARY a.constant_value = BINARY ops.permission_string" in aosp
    assert "a.lifecycle_status = 'invalid_token'" in aosp
    assert "a.authority_source_type = 'queue_apply_shell'" in aosp
    assert "a.source_family_key = 'aosp_sparse_queue_apply_shell'" in aosp
    assert unknown_dictionary_join_predicate(
        observation_alias="ops",
        unknown_alias="up",
    ) == "BINARY up.permission_string = BINARY ops.permission_string"


def test_authority_fact_join_is_unique_current_best_and_exact() -> None:
    sql = authority_fact_join(raw_expr="ops.permission_string")
    assert "HAVING COUNT(*) = 1" in sql
    assert "WHERE is_current_best = 1" in sql
    assert "fact_scope IN ('permission_definition','removed_api','provider_permission')" in sql
    assert "GROUP BY BINARY permission_string" in sql
    assert "BINARY paf.permission_string = BINARY ops.permission_string" in sql
    assert "permission_string_norm" not in sql
    with pytest.raises(ValueError, match="invalid SQL expression"):
        authority_fact_join(raw_expr="ops.permission_string; DROP TABLE x")


def test_token_alias_join_is_unique_exact_raw_bytes() -> None:
    sql = token_alias_join(raw_expr="ops.permission_string")
    assert "GROUP BY BINARY raw_token" in sql
    assert "HAVING COUNT(*) = 1" in sql
    assert "BINARY als.raw_token = BINARY ops.permission_string" in sql
    assert catalog_identity_expr(raw_expr="ops.permission_string") == (
        "COALESCE(als.canonical_token, ops.permission_string)"
    )


def test_vt_current_join_is_unique_casefold() -> None:
    sql = vt_current_join(raw_expr="ops.permission_string")
    assert "GROUP BY LOWER(permission_string)" in sql
    assert "HAVING COUNT(*) = 1" in sql
    assert "LOWER(vtc.permission_string) = LOWER(ops.permission_string)" in sql
    assert "BINARY vtc.permission_string = BINARY ops.permission_string" not in sql


def _permission_row_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": [1],
            "permission_string_raw": ["android.permission.INTERNET"],
            "permission_string": ["android.permission.internet"],
            "protection_level": ["NORMAL"],
            "permission_source": ["AOSP"],
            "historical_permission_source": ["AOSP"],
            "is_aosp_dict_match": [1],
            "is_oem_dict_match": [0],
        }
    )


def test_banking_and_observation_sql_share_the_oem_join_contract(monkeypatch) -> None:
    permission_contracts.reset_permission_obs_norm_cache()
    monkeypatch.setattr(
        permission_contracts.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string", "permission_string_norm"],
    )

    from obsidiandroid.database import db_permission_analysis_queries as banking
    from obsidiandroid.orchestration import permission_features
    from obsidiandroid.pipeline.permission_trends import sample_permission_data

    captured: dict[str, str] = {}

    def capture_banking(query, *_args, **_kwargs):
        captured["banking"] = query
        return [], []

    def capture_observation(query, **_kwargs):
        if "LEFT JOIN android_permission_dict_oem" in query:
            name = "trends" if "is_oem_dict_match" in query else "features"
            captured[name] = query
        return _permission_row_frame()

    monkeypatch.setattr(banking.db_engine, "execute_query", capture_banking)
    monkeypatch.setattr(
        permission_features.db_engine,
        "execute_permission_query",
        capture_observation,
    )

    banking.fetch_android_banking_trojans_with_permissions()
    permission_features.build_permission_feature_frame(
        pd.DataFrame({"sample_id": [1]}),
        min_permission_support=1,
    )
    sample_permission_data.fetch_permission_rows_for_samples([1])

    alias_by_query = {"banking": "mp", "features": "o", "trends": "o"}
    forbidden = (
        "ops.vendor_id =",
        "OR ops.vendor_id IS NULL",
        "OR o.vendor_id IS NULL",
        "OR mp.vendor_id IS NULL",
        "LOWER(TRIM(o.permission_string))",
        "LOWER(TRIM(mp.permission_string))",
        "= o.permission_string_norm",
        "mp.permission_string_norm =",
        "paf.permission_string_norm",
        "= a.constant_value_norm",
    )
    assert set(captured) == set(alias_by_query)
    for name, sql in captured.items():
        oem = alias_by_query[name]
        assert (
            f"BINARY {oem}.permission_string = BINARY ops.permission_string"
        ) in sql
        assert f"AND {oem}.vendor_id IS NOT NULL" in sql
        assert "HAVING COUNT(*) = 1" in sql
        if name == "banking":
            assert "BINARY up.permission_string = BINARY ops.permission_string" in sql
            assert "BINARY vtc.permission_string = BINARY ops.permission_string" not in sql
            assert "GROUP BY LOWER(permission_string)" in sql
            assert "LOWER(vtc.permission_string) = LOWER(ops.permission_string)" in sql
        else:
            assert "BINARY a.constant_value = BINARY ops.permission_string" in sql
            assert "a.lifecycle_status = 'invalid_token'" in sql
            assert "queue_apply_shell" in sql
        for needle in forbidden:
            assert needle not in sql
