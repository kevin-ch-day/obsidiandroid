from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.database.permission_intel_v1.adapter import EXECUTABLE_SELECTS
from obsidiandroid.database.permission_intel_v1.models import ShadowMode

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src/obsidiandroid/database/permission_intel_v1"
FORBIDDEN_SQL = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|REPLACE|ALTER|CREATE|DROP|TRUNCATE|CALL)\b",
    re.IGNORECASE,
)


def test_executable_adapter_queries_are_select_only() -> None:
    for sql in EXECUTABLE_SELECTS:
        tokens = sql.lstrip().split(None, 1)
        assert tokens and tokens[0].upper() == "SELECT"
        assert FORBIDDEN_SQL.search(sql) is None
        assert "START TRANSACTION" not in sql.upper()


def test_adapter_has_no_production_names_credentials_or_host_sockets() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    )
    assert "erebus_threat_intel_prod" not in source
    assert "android_permission_intel`" not in source
    assert "/run/mysqld" not in source
    assert "MYSQL_PWD" not in source
    assert "password=" not in source.lower()


def test_runtime_package_does_not_import_shared_python_package() -> None:
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(name.startswith("android_permission_intel") for name in imported)


def test_runtime_package_introduces_no_network_client() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    )
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket." not in source


def test_no_authoritative_shadow_mode_exists() -> None:
    assert "V1_AUTHORITATIVE" not in {mode.value for mode in ShadowMode}


def test_shadow_configuration_is_not_automatically_enabled() -> None:
    source = (PACKAGE / "shadow.py").read_text(encoding="utf-8")
    assert 'os.getenv(SHADOW_MODE_ENV, "LEGACY_ONLY")' in source


def test_machine_inventory_is_complete_and_has_explicit_scope() -> None:
    payload = json.loads(
        (ROOT / "tests/fixtures/permission_intel_v1_query_inventory.json").read_text()
    )
    assert payload["audited_commit"] == "b65d78993c417d1390062098f0b4e110d65bc224"
    assert payload["baseline_commit"] == payload["audited_commit"]
    assert payload["integration_commit"] == "15d6b738ee8df85b473a08306fa7259fb5a747e6"
    assert payload["artifact_generation_commit"] == payload["integration_commit"]
    assert payload["baseline_commit"] != payload["integration_commit"]
    assert payload["shared_contract_commit"] == "0cf71e18e43f33f5bd43ac442e88c4a423529236"
    assert payload["catalog_release"]
    digest_body = {key: value for key, value in payload.items() if key != "evidence_digest"}
    assert payload["evidence_digest"] == hash_payload(digest_body)
    assert len(payload["queries"]) >= 16
    assert any(item["in_pilot_scope"] for item in payload["queries"])
    assert all(
        item["in_pilot_scope"] or item["reason_excluded"] for item in payload["queries"]
    )


def test_query_inventory_document_does_not_relabel_baseline_as_current() -> None:
    text = (ROOT / "docs/permission_intel_v1_query_inventory.md").read_text()
    assert "Audited/current commit" not in text
    assert "Audited legacy baseline" in text
    assert "Integration and artifact-generation commit" in text


def test_policy_held_report_quotes_permission_database_identifier() -> None:
    source = (
        ROOT / "scripts/diagnostics/report_android_policy_held_token_risk.py"
    ).read_text()
    assert "_quote_identifier(PERMISSION_INTEL_DB_NAME)" in source
    assert ".format(permission_db=PERMISSION_INTEL_DB_NAME)" not in source
    assert "FROM {_PERMISSION_OBSERVATION_TABLE}" in source
