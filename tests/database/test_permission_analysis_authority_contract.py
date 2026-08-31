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
    assert sql.count("= 'OEM'") >= 5
