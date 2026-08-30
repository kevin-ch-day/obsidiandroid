from __future__ import annotations

import csv
import hashlib
import importlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from obsidiandroid.database.permission_intel_v1.adapter import PermissionIntelV1Adapter
from obsidiandroid.database.permission_intel_v1.models import (
    PINNED_CATALOG_DIGEST,
    PINNED_CATALOG_PLAN_DIGEST,
    PINNED_MIGRATION_SET_DIGEST,
    PINNED_SHARED_COMMIT,
    AuthorityClass,
    CatalogGateState,
)
from obsidiandroid.database.permission_intel_v1.parity import (
    LegacyPlatformFact,
    ParityReport,
    compare_permission,
)

pytestmark = pytest.mark.integration

IMAGE = "docker.io/library/mariadb:11.8"
DATABASE_NAME = "android_permission_intel_test_obsidian"
SHARED_ROOT = Path(
    os.environ.get(
        "ANDROID_PERMISSION_INTEL_SHARED_ROOT",
        "/home/systemadmin/GitHub/android-permission-intel",
    )
).resolve()
EVIDENCE_ROOT = Path(
    os.environ.get(
        "OBSIDIANDROID_PERMISSION_INTEL_V1_EVIDENCE_ROOT",
        "/tmp/obsidiandroid-permission-intel-v1-shadow-evidence",
    )
).resolve()


def _run(
    argv: Sequence[str], *, input_text: str | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv),
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"disposable command failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    return result


def _git(*args: str) -> str:
    return _run(["git", "-C", str(SHARED_ROOT), *args]).stdout.strip()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sql_literal(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        raise TypeError(
            f"unsupported disposable query parameter: {type(value).__name__}"
        )
    return "'" + value.replace("'", "''") + "'"


def _bind_read_query(sql: str, params: Sequence[object]) -> str:
    if sql.lstrip().split(None, 1)[0].upper() != "SELECT":
        raise ValueError("Obsidian disposable query is not SELECT-only")
    rendered = sql
    for value in params:
        if "%s" not in rendered:
            raise ValueError("too many query parameters")
        rendered = rendered.replace("%s", _sql_literal(value), 1)
    if "%s" in rendered:
        raise ValueError("not enough query parameters")
    return rendered


def _parse_tsv(output: str) -> tuple[Mapping[str, Any], ...]:
    rows = list(csv.reader(output.splitlines(), delimiter="\t"))
    if not rows:
        return ()
    headers = rows[0]
    integer_columns = {
        "exhaustive_scope",
        "import_receipt_count",
        "public_manifest_exposed",
        "public_health_exposed",
        "health_module_declared",
        "target_sdk_threshold",
        "target_ordinal",
    }
    parsed: list[Mapping[str, Any]] = []
    for values in rows[1:]:
        row: dict[str, Any] = {}
        for key, value in zip(headers, values):
            if value == "NULL":
                row[key] = None
            elif key in integer_columns:
                row[key] = int(value)
            else:
                row[key] = value
        parsed.append(row)
    return tuple(parsed)


def test_real_obsidiandroid_selects_against_disposable_mariadb() -> None:
    if os.environ.get("OBSIDIANDROID_RUN_PERMISSION_INTEL_V1_DISPOSABLE") != "1":
        pytest.skip("requires explicit disposable Permission Intel integration consent")

    assert SHARED_ROOT.is_dir()
    assert _git("rev-parse", PINNED_SHARED_COMMIT) == PINNED_SHARED_COMMIT
    assert _git("status", "--porcelain") == ""
    manifest = json.loads((SHARED_ROOT / "migrations/manifest.json").read_text())
    plan = json.loads(
        (SHARED_ROOT / "plans/schema-v1/catalog_load_plan.json").read_text()
    )
    assert manifest["migration_set_digest"] == PINNED_MIGRATION_SET_DIGEST
    assert (
        plan["catalog_content_release"]["semantic_catalog_digest"]
        == PINNED_CATALOG_DIGEST
    )
    assert plan["catalog_plan_digest"] == PINNED_CATALOG_PLAN_DIGEST
    for migration in manifest["migrations"]:
        migration_path = SHARED_ROOT / "migrations/mariadb" / migration["filename"]
        assert _file_sha256(migration_path) == migration["sha256"]

    if str(SHARED_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(SHARED_ROOT / "src"))
    rehearsal = importlib.import_module("android_permission_intel.schema.rehearsal")
    migrations = importlib.import_module("android_permission_intel.schema.migrations")
    outputs = importlib.import_module("android_permission_intel.schema.outputs")
    safety = importlib.import_module("android_permission_intel.schema.safety")
    safety.validate_rehearsal_target(DATABASE_NAME, ephemeral=True, socket=None)
    assert (
        migrations.validate_migration_package(SHARED_ROOT)["migration_set_digest"]
        == PINNED_MIGRATION_SET_DIGEST
    )
    outputs.validate_rendered_plans(SHARED_ROOT)

    assert _run(["podman", "image", "exists", IMAGE], check=False).returncode == 0
    container = f"obsidian-pi-v1-{secrets.token_hex(5)}"
    teardown = False
    integration_result: dict[str, Any] = {}
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="obsidian-pi-v1-") as temporary:
        password_file = Path(temporary) / "root-password"
        password_file.write_text(secrets.token_urlsafe(32), encoding="ascii")
        password_file.chmod(0o600)
        try:
            _run(
                [
                    "podman",
                    "run",
                    "-d",
                    "--name",
                    container,
                    "--network",
                    "none",
                    "--mount",
                    f"type=bind,src={password_file},dst=/run/secrets/root-password,ro=true,relabel=private",
                    "-e",
                    "MARIADB_ROOT_PASSWORD_FILE=/run/secrets/root-password",
                    IMAGE,
                ]
            )
            ready = False
            ready_command = (
                'test "$(cat /proc/1/comm)" = mariadbd && '
                "test -S /run/mysqld/mysqld.sock && "
                "MYSQL_PWD=$(cat /run/secrets/root-password) "
                "mariadb-admin -uroot ping --silent"
            )
            for _ in range(60):
                probe = _run(
                    [
                        "podman",
                        "exec",
                        container,
                        "sh",
                        "-lc",
                        ready_command,
                    ],
                    check=False,
                )
                if probe.returncode == 0:
                    ready = True
                    break
                time.sleep(0.5)
            assert ready, "disposable MariaDB did not become ready"

            client = [
                "podman",
                "exec",
                "-i",
                container,
                "sh",
                "-lc",
                "MYSQL_PWD=$(cat /run/secrets/root-password) exec mariadb -uroot --batch --skip-column-names",
            ]
            query_client = [
                "podman",
                "exec",
                "-i",
                container,
                "sh",
                "-lc",
                "MYSQL_PWD=$(cat /run/secrets/root-password) exec mariadb -uroot --batch --column-names --raw",
            ]
            _run(
                client,
                input_text=(
                    f"CREATE DATABASE `{DATABASE_NAME}` CHARACTER SET utf8mb4 "
                    "COLLATE utf8mb4_unicode_ci;\n"
                ),
            )
            applied = rehearsal._apply_migrations(SHARED_ROOT, client, DATABASE_NAME)
            _run(
                client,
                input_text=(
                    f"USE `{DATABASE_NAME}`;\n"
                    + rehearsal.render_catalog_load_sql(SHARED_ROOT)
                ),
            )
            validation_lines = _run(
                client,
                input_text=rehearsal._rehearsal_validation_sql(DATABASE_NAME),
            ).stdout.splitlines()
            rehearsal._validate_rehearsal_results(
                validation_lines,
                catalog_digest=PINNED_CATALOG_DIGEST,
            )

            executed_selects: list[str] = []

            def query(
                sql: str, params: Sequence[object]
            ) -> Sequence[Mapping[str, Any]]:
                rendered = _bind_read_query(sql, params)
                executed_selects.append(sql)
                result = _run(
                    query_client,
                    input_text=(
                        f"USE `{DATABASE_NAME}`;\n"
                        "START TRANSACTION READ ONLY;\n"
                        f"{rendered};\n"
                        "ROLLBACK;\n"
                    ),
                )
                return _parse_tsv(result.stdout)

            adapter = PermissionIntelV1Adapter(query)
            gate = adapter.read_catalog_gate()
            assert gate.state is CatalogGateState.COMPATIBLE_INCOMPLETE_SCOPE
            assert gate.catalog_status is not None
            assert gate.catalog_status.exhaustive_scope is False

            public = adapter.get_permission("android.permission.INTERNET")
            health = adapter.get_permission(
                "android.permission.health.READ_HEALTH_DATA_HISTORY"
            )
            internal = adapter.get_permission("com.android.alarm.permission.SET_ALARM")
            modified = adapter.get_permission(
                "android.permission.WIFI_UPDATE_USABILITY_STATS_SCORE"
            )
            flagged = adapter.get_permission(
                "android.permission.health.READ_SYMPTOM_GENERALIZED_BODY_ACHE"
            )
            unknown = adapter.get_permission("android.permission.NOT_IN_PINNED_CATALOG")
            case_variant = adapter.get_permission("android.permission.internet")
            splits = adapter.get_split_relations("android.permission.READ_CONTACTS")
            evidence = adapter.get_source_evidence("android.permission.INTERNET")

            assert (
                public is not None
                and public.authority_class is AuthorityClass.AOSP_PUBLIC
            )
            assert health is not None and health.public_health_exposed is True
            assert (
                internal is not None
                and internal.authority_class is AuthorityClass.AOSP_INTERNAL
            )
            assert (
                modified is not None and "privileged" in modified.protection.modifiers
            )
            assert (
                flagged is not None and "allowedInPrivateComputeCore" in flagged.flags
            )
            assert (
                public.platform_release is not None
                and public.platform_release.full == "37"
            )
            assert public.sdk_extension_release_id is None
            assert unknown is None
            assert case_variant is None
            assert (
                splits
                and splits[0].source_permission == "android.permission.READ_CONTACTS"
            )
            assert evidence and evidence[0]["fact_type"] == "DECLARATION"

            comparisons = []
            for fact in (public, health, internal, modified, flagged):
                assert fact is not None
                legacy = LegacyPlatformFact.from_mapping(
                    {
                        "constant_value": fact.canonical_permission,
                        "authority_class": fact.authority_class.value,
                        "protection_level": fact.protection.compatibility_expression,
                    }
                )
                comparisons.append(compare_permission(legacy, fact))
            report = ParityReport(
                obsidiandroid_commit="b65d78993c417d1390062098f0b4e110d65bc224",
                schema_contract_version=gate.catalog_status.schema_contract_version,
                catalog_release_id=gate.catalog_status.catalog_release_id,
                source_scope_status="INCOMPLETE_EXPLICIT",
                gate_state=gate.state.value,
                test_environment_identity="rootless-network-none-mariadb-11.8",
                comparisons=tuple(comparisons),
                unsupported_queries=("sdk_extension_detail_view_not_exposed",),
                dynamic_sql_not_covered=("legacy_runtime_object_discovery",),
            )
            first_json, first_markdown = report.write(
                EVIDENCE_ROOT / "permission_intel_v1_parity.json",
                EVIDENCE_ROOT / "permission_intel_v1_parity.md",
            )
            second_json, second_markdown = report.write(
                EVIDENCE_ROOT / "permission_intel_v1_parity_second.json",
                EVIDENCE_ROOT / "permission_intel_v1_parity_second.md",
            )
            assert first_json.read_bytes() == second_json.read_bytes()
            assert first_markdown.read_bytes() == second_markdown.read_bytes()

            count_rows = query(
                "SELECT "
                "(SELECT COUNT(*) FROM android_permission_v1_current_public_permission) AS public_union, "
                "(SELECT SUM(public_manifest_exposed) FROM android_permission_v1_current_permission) AS public_manifest, "
                "(SELECT SUM(public_health_exposed) FROM android_permission_v1_current_permission) AS public_health, "
                "(SELECT COUNT(*) FROM android_permission_v1_split_permission) AS split_targets",
                (),
            )
            counts = count_rows[0]
            assert counts == {
                "public_union": "577",
                "public_manifest": "358",
                "public_health": "219",
                "split_targets": "27",
            }
            version = _run(client, input_text="SELECT VERSION();\n").stdout.strip()
            assert all(
                sql.lstrip().upper().startswith("SELECT") for sql in executed_selects
            )
            integration_result = {
                "status": "PASS",
                "evidence_class": "disposable_integration_evidence",
                "mariadb_version": version,
                "network": "none",
                "database_name_class": "allowlisted_ephemeral_test",
                "migration_result": applied,
                "migration_set_digest": PINNED_MIGRATION_SET_DIGEST,
                "catalog_digest": PINNED_CATALOG_DIGEST,
                "catalog_plan_digest": PINNED_CATALOG_PLAN_DIGEST,
                "gate_state": gate.state.value,
                "executed_adapter_select_count": len(executed_selects),
                "obsidiandroid_write_count": 0,
                "public_manifest_count": 358,
                "public_health_count": 219,
                "public_union_count": 577,
                "split_target_count": 27,
                "case_sensitive_lookup": "PASS",
                "parity_digest": report.semantic_digest(),
            }
        finally:
            _run(["podman", "rm", "-f", container], check=False)
            teardown = (
                _run(
                    ["podman", "container", "exists", container], check=False
                ).returncode
                != 0
            )

    integration_result["teardown_result"] = "PASS" if teardown else "FAIL"
    (EVIDENCE_ROOT / "permission_intel_v1_integration_result.json").write_text(
        json.dumps(integration_result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert teardown is True
    assert integration_result["status"] == "PASS"
