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
    assert sql.count(
        "BINARY mp.permission_string = BINARY ops.permission_string"
    ) >= 5
    assert sql.count("ov.vendor_id IS NOT NULL") >= 5
    assert "AND mp.vendor_id IS NOT NULL" in sql
    assert "HAVING COUNT(*) = 1" in sql
    assert "paf.permission_string_norm =" not in sql
    assert "ops.vendor_id = mp.vendor_id" not in sql
    assert "OR ops.vendor_id IS NULL" not in sql
    assert "OR UPPER(COALESCE(ops.classification, '')) = 'OEM'" not in sql
    assert "AS historical_permission_source" in sql
    assert "LEFT(COALESCE(paf.authority_source_type,''), 5) = 'aosp_'" in sql
    assert "pi.identity_status = 'RETIRED'" in sql
    assert sql.count("paf.fact_scope = 'removed_api'") == 1
    known_id_sql = sql.split("AS known_permission_id", 1)[0].rsplit("CASE", 1)[-1]
    assert "THEN ops.permission_string" in known_id_sql
    assert "lifecycle IN ('historical'" not in known_id_sql
    assert "AND NOT (" not in known_id_sql
    known_prot_tail = sql.split("AS known_protection", 1)[0]
    known_prot_when = known_prot_tail[known_prot_tail.rfind("WHEN") :]
    assert "AND NOT (" in known_prot_when
    assert "pi.feature_dependency IS NULL" in known_prot_when
