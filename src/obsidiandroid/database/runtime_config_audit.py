"""Credential-redacted normal-runtime database configuration audit.

This module deliberately opens only the two upstream source connections when
checking health.  It never opens a Core connection and issues only bounded
``SELECT`` statements against the normal analysis read surfaces.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from mysql.connector import Error as MySQLError

from config import app_config

from . import db_config, db_engine


_EXPECTED_NORMAL_READER = "obsidiandroid_pipeline_reader@localhost"


def _option_file_state(value: object) -> str:
    """Return a credential-free status for an explicit client option file."""
    raw = str(value or "").strip()
    if not raw:
        return "not_applicable"
    try:
        path = Path(raw).expanduser()
        mode = path.stat().st_mode & 0o777
    except OSError:
        return "unreadable"
    if not path.is_file():
        return "unreadable"
    return "valid" if mode & 0o077 == 0 else "invalid_mode"


def _credential_mechanism(*, option_file: object, host: object, user: object, password: object) -> str:
    if str(option_file or "").strip():
        return "option_file"
    if all(str(value or "").strip() for value in (host, user, password)):
        return "environment"
    return "missing"


def _connection_status(operation: Callable[[], object]) -> dict[str, str | bool]:
    try:
        operation()
    except Exception as exc:  # connector and source-config errors are intentionally normalized.
        return {"ok": False, "status": _classify_connection_error(exc)}
    return {"ok": True, "status": "ok"}


def _classify_connection_error(exc: BaseException) -> str:
    if isinstance(exc, db_engine.SourceDatabaseConfigurationError):
        text = str(exc).lower()
        if "administrator" in text:
            return "administrator_source_credential_rejected"
        if "option file" in text:
            return "invalid_or_unavailable_option_file"
        return "missing_source_configuration"
    if isinstance(exc, MySQLError):
        errno = int(getattr(exc, "errno", 0) or 0)
        if errno in {1045, 1698}:
            return "authentication_failed"
        if errno in {1044, 1142, 1227}:
            return "insufficient_select_privilege"
        if errno == 1146:
            return "missing_source_object"
        return "connection_or_query_failed"
    return "configuration_or_connection_failed"


def _read_primary_surface(query: str) -> object:
    return db_engine.execute_query(query, fetch=True)


def _read_permission_surface(query: str) -> object:
    return db_engine.execute_permission_query(query, fetch=True)


def _normal_reader_identity_status(operation: Callable[[str], object]) -> dict[str, str | bool]:
    """Confirm the connector selected the approved reader without printing identity details."""
    try:
        rows = operation("SELECT CURRENT_USER()")
        identity = str(rows[0][0] if rows else "").strip().lower()
    except Exception as exc:  # normalized in the same way as surface checks
        return {"ok": False, "status": _classify_connection_error(exc)}
    if identity in {"root@localhost", "root@127.0.0.1", "mysql@localhost", "mariadb@localhost"}:
        return {"ok": False, "status": "administrator_source_credential_rejected"}
    if identity != _EXPECTED_NORMAL_READER:
        return {"ok": False, "status": "unexpected_source_account"}
    return {"ok": True, "status": "ok"}


def permission_intel_reader_identity_status() -> dict[str, str | bool]:
    """Check the Permission Intel connector's approved account without disclosing it."""

    return _normal_reader_identity_status(_read_permission_surface)


def build_runtime_database_config_audit(*, check_connections: bool = True) -> dict[str, object]:
    """Build a JSON-safe audit of normal analysis configuration and read health."""
    source_mechanism = _credential_mechanism(
        option_file=db_config.DB_OPTION_FILE,
        host=db_config.DB_HOST,
        user=db_config.DB_USER,
        password=db_config.DB_PASSWORD,
    )
    permission_mechanism = _credential_mechanism(
        option_file=db_config.PERMISSION_INTEL_DB_OPTION_FILE,
        host=db_config.PERMISSION_INTEL_DB_HOST,
        user=db_config.PERMISSION_INTEL_DB_USER,
        password=db_config.PERMISSION_INTEL_DB_PASSWORD,
    )
    report: dict[str, object] = {
        "audit_version": "runtime-database-config-v1",
        "normal_source": {
            "host_configured": bool(str(db_config.DB_HOST or "").strip()) or source_mechanism == "option_file",
            "account_configured": bool(str(db_config.DB_USER or "").strip()) or source_mechanism == "option_file",
            "credential_mechanism": source_mechanism,
            "option_file_mode": _option_file_state(db_config.DB_OPTION_FILE),
            "schema": str(db_config.DB_NAME),
            "expected_account_role": "normal_pipeline_reader" if source_mechanism != "missing" else "not_configured",
        },
        "permission_intel": {
            "host_configured": bool(str(db_config.PERMISSION_INTEL_DB_HOST or "").strip()) or permission_mechanism == "option_file",
            "account_configured": bool(str(db_config.PERMISSION_INTEL_DB_USER or "").strip()) or permission_mechanism == "option_file",
            "credential_mechanism": permission_mechanism,
            "option_file_mode": _option_file_state(db_config.PERMISSION_INTEL_DB_OPTION_FILE),
            "schema": str(db_config.PERMISSION_INTEL_DB_NAME),
        },
        "core": {
            "credential_reference_present": bool(str(os.environ.get("OBSIDIANDROID_CORE_CREDENTIAL_FILE", "")).strip()),
            "persistence_enabled": bool(db_config.CORE_PERSISTENCE_ENABLED),
            "connection_opened": False,
        },
        "persistence": {
            "effective_mode": str(getattr(app_config, "RESULTS_PERSISTENCE_MODE", "read_only")),
            "legacy_results_warehouse_export_enabled": bool(
                getattr(app_config, "ENABLE_RESULTS_WAREHOUSE_EXPORT", False)
            ),
            "filesystem_artifacts_authoritative": True,
        },
    }
    if not check_connections:
        report["source_connection_health"] = {"ok": False, "status": "not_checked"}
        report["permission_intel_connection_health"] = {"ok": False, "status": "not_checked"}
        return report

    report["source_connection_health"] = _normal_reader_identity_status(_read_primary_surface)
    report["source_surface_checks"] = {
        "catalog": _connection_status(lambda: _read_primary_surface("SELECT 1 FROM `malware_sample_catalog` LIMIT 1")),
        "vt_confidence": _connection_status(
            lambda: _read_primary_surface("SELECT 1 FROM `vt_sample_verdict_confidence_current` LIMIT 1")
        ),
        "family_type_authority": _connection_status(
            lambda: _read_primary_surface("SELECT 1 FROM `v_android_sample_family_type_authority` LIMIT 1")
        ),
    }
    report["permission_intel_connection_health"] = permission_intel_reader_identity_status()
    report["permission_intel_surface_checks"] = {
        "permission_observations": _connection_status(
            lambda: _read_permission_surface("SELECT 1 FROM `android_permission_obs_sample` LIMIT 1")
        ),
        "permission_dictionary": _connection_status(
            lambda: _read_permission_surface("SELECT 1 FROM `android_permission_dict_aosp` LIMIT 1")
        ),
    }
    return report
