"""Offline capability-contract checks for a new ObsidianDroid host."""

from __future__ import annotations

from scripts.core_migration.preflight_host import evaluate


def _runtime() -> dict:
    return {"python": "3.14.4", "python_supported": True, "platform": "Fedora", "required_commands": {"mariadb": True, "mariadb-dump": True, "sha256sum": True}}


def _database(**overrides) -> dict:
    value = {
        "version": "10.11.18-MariaDB", "version_comment": "MariaDB Server", "character_set_server": "utf8mb4",
        "collation_server": "utf8mb4_unicode_ci", "time_zone": "SYSTEM", "system_time_zone": "UTC",
        "lower_case_table_names": 0, "have_ssl": "YES", "require_secure_transport": True,
        "local_infile": False, "event_scheduler": "OFF",
    }
    value.update(overrides)
    return value


def test_remote_host_preflight_requires_mariadb_tls_and_safe_import_policy() -> None:
    assert evaluate(runtime=_runtime(), database=_database(), deployment_mode="remote")["status"] == "PASS"
    report = evaluate(runtime=_runtime(), database=_database(require_secure_transport=False), deployment_mode="remote")
    assert report["status"] == "BLOCKED"
    assert report["checks"]["tls_required_for_remote"] is False


def test_local_host_preflight_still_rejects_an_unsupported_database_version() -> None:
    report = evaluate(runtime=_runtime(), database=_database(version="10.5.22-MariaDB"), deployment_mode="local")
    assert report["status"] == "BLOCKED"
    assert report["checks"]["mariadb_version"] is False
