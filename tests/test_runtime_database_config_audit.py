"""Focused tests for the credential-redacted normal-runtime DB audit."""

from __future__ import annotations

from obsidiandroid.database import db_config
from obsidiandroid.database import runtime_config_audit as audit


def test_audit_reports_missing_source_configuration_without_connecting(monkeypatch) -> None:
    monkeypatch.setattr(db_config, "DB_OPTION_FILE", "")
    monkeypatch.setattr(db_config, "DB_HOST", "")
    monkeypatch.setattr(db_config, "DB_USER", "")
    monkeypatch.setattr(db_config, "DB_PASSWORD", "")
    report = audit.build_runtime_database_config_audit(check_connections=False)
    assert report["normal_source"]["credential_mechanism"] == "missing"
    assert report["normal_source"]["option_file_mode"] == "not_applicable"
    assert report["source_connection_health"]["status"] == "not_checked"
    assert report["core"]["connection_opened"] is False


def test_audit_reports_private_option_file_configuration(monkeypatch, tmp_path) -> None:
    option_file = tmp_path / "pipeline-reader.cnf"
    option_file.write_text("[client]\n", encoding="utf-8")
    option_file.chmod(0o600)
    monkeypatch.setattr(db_config, "DB_OPTION_FILE", str(option_file))
    monkeypatch.setattr(db_config, "PERMISSION_INTEL_DB_OPTION_FILE", str(option_file))
    report = audit.build_runtime_database_config_audit(check_connections=False)
    assert report["normal_source"]["credential_mechanism"] == "option_file"
    assert report["normal_source"]["option_file_mode"] == "valid"
    assert report["permission_intel"]["credential_mechanism"] == "option_file"


def test_audit_runs_only_primary_and_permission_select_checks(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _primary(sql: str):
        calls.append(("primary", sql))
        return [("obsidiandroid_pipeline_reader@localhost",)] if sql == "SELECT CURRENT_USER()" else []

    def _permission(sql: str):
        calls.append(("permission", sql))
        return [("obsidiandroid_pipeline_reader@localhost",)] if sql == "SELECT CURRENT_USER()" else []

    monkeypatch.setattr(audit, "_read_primary_surface", _primary)
    monkeypatch.setattr(audit, "_read_permission_surface", _permission)
    report = audit.build_runtime_database_config_audit(check_connections=True)
    assert report["source_connection_health"]["ok"] is True
    assert report["permission_intel_connection_health"]["ok"] is True
    assert calls and all(sql.startswith("SELECT") for _, sql in calls)
    assert {role for role, _ in calls} == {"primary", "permission"}


def test_audit_rejects_administrator_identity(monkeypatch) -> None:
    monkeypatch.setattr(audit, "_read_primary_surface", lambda _sql: [("root@localhost",)])
    report = audit.build_runtime_database_config_audit(check_connections=True)
    assert report["source_connection_health"]["status"] == "administrator_source_credential_rejected"
