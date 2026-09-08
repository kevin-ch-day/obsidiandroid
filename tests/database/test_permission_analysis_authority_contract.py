from __future__ import annotations

from obsidiandroid.database import db_permission_analysis_queries as queries


def test_app_defined_is_not_manufacturer_authority(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_execute(query, **_kwargs):
        captured["query"] = query
        return [], []

    monkeypatch.setattr(queries.db_engine, "execute_query", fake_execute)
    queries.fetch_android_banking_trojans_with_permissions()
    sql = captured["query"]
    assert "IN ('OEM', 'APP_DEFINED')" not in sql
    assert sql.count("mp.permission_string IS NOT NULL") >= 5
    assert "OR UPPER(COALESCE(ops.classification, '')) = 'OEM'" not in sql
    assert "AS historical_permission_source" in sql
    assert "LEFT(COALESCE(paf.authority_source_type,''), 5) = 'aosp_'" in sql
