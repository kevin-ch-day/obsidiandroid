"""Production Core imports require a complete, one-time Phase 2C record."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pytest

from obsidiandroid.core_migration.authorization import (
    FileAuthorizationConsumptionLedger,
    Phase2CImportAuthorization,
    mariadb_server_attestation,
    validate_core_preflight_payload,
    validate_host_preflight_payload,
)
from obsidiandroid.core_migration.importer import _database_json, execute_import_plan
from obsidiandroid.core_migration.mapping import CoreImportError, build_import_plan


_MIGRATIONS = {
    "0001": "a" * 64,
    "0002": "b" * 64,
}
_EXTRACT_MANIFEST = "c" * 64
_REPOSITORY_COMMIT = "d" * 40


def _plan() -> dict:
    return build_import_plan(
        run={"run_id": "fixture-run", "profile_id": "fixture-profile", "created_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64},
        snapshots=[{"run_id": "fixture-run", "extracted_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64, "snapshot_row_count": 1}],
        samples=[{"run_id": "fixture-run", "sha256": "b" * 64, "sample_id": 1}],
        artifacts=[],
        conflicts=[],
        phase2c_execution_contract={
            "source_extract_manifest_sha256": _EXTRACT_MANIFEST,
            "repository_commit": _REPOSITORY_COMMIT,
            "migration_checksums": _MIGRATIONS,
        },
    )


def _authorization(plan: dict) -> Phase2CImportAuthorization:
    now = datetime.now(UTC)
    return Phase2CImportAuthorization(
        authorization_id="phase2c-fixture-001",
        approved_by="reviewer",
        authorized_operator="operator",
        target_database="obsidiandroid_core_prod",
        target_server_identity="f" * 64,
        writer_account="obsidiandroid_core_writer@localhost",
        source_run_id="fixture-run",
        plan_sha256=plan["plan_sha256"],
        source_extract_manifest_sha256=_EXTRACT_MANIFEST,
        mapping_contract_version=plan["mapping_contract_version"],
        repository_commit=_REPOSITORY_COMMIT,
        migration_checksums=_MIGRATIONS,
        expected_counts=plan["expected_counts"],
        core_preflight_sha256="e" * 64,
        host_preflight_sha256="f" * 64,
        issued_at_utc=now.isoformat().replace("+00:00", "Z"),
        expires_at_utc=(now + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
        fixture_classification="diagnostic_non_publication",
    )


def _preflight(authorization: Phase2CImportAuthorization) -> dict:
    payload = {
        "target": "obsidiandroid_core_prod",
        "server_attestation": {
            "attestation_version": "mariadb-server-attestation-v1",
            "hostname": "fixture-host",
            "port": 3306,
            "server_id": 7,
            "version": "10.11.18-MariaDB",
            "version_comment": "MariaDB Server",
            "sha256": authorization.target_server_identity,
        },
        "table_contract_ok": True,
        "migration_contract_ok": True,
        "evidence_empty": True,
    }
    payload["audit_sha256"] = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return payload


def _host_preflight(authorization: Phase2CImportAuthorization) -> dict:
    payload = {
        "report_version": "obsidiandroid-host-preflight-v1",
        "status": "PASS",
        "deployment_mode": "local",
        "runtime": {"python_supported": True},
        "database": {"version": "10.11.18-MariaDB"},
        "checks": {"mariadb_version": True},
        "generated_at_utc": "2026-07-19T12:00:00Z",
    }
    payload["report_sha256"] = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return payload


def test_production_import_is_rejected_without_an_explicit_authorization() -> None:
    with pytest.raises(CoreImportError, match="explicit Phase 2C authorization"):
        execute_import_plan(target_database="obsidiandroid_core_prod", plan=_plan(), connection_factory=None)


def test_authorization_must_match_the_exact_plan_before_connection() -> None:
    plan = _plan()
    authorization = _authorization(plan)
    authorization = Phase2CImportAuthorization(**{**authorization.__dict__, "plan_sha256": "0" * 64})
    with pytest.raises(CoreImportError, match="hash does not match"):
        execute_import_plan(
            target_database="obsidiandroid_core_prod",
            plan=plan,
            connection_factory=lambda _target: (_ for _ in ()).throw(AssertionError("must not connect")),
            production_authorization=authorization,
            authorization_consumption_ledger=FileAuthorizationConsumptionLedger(Path("/tmp/phase2c-unused-ledger")),
        )


def test_preflight_requires_its_self_hash_and_reviewed_server_attestation() -> None:
    plan = _plan()
    identity = mariadb_server_attestation(
        hostname="fixture-host", port=3306, server_id=7, version="10.11.18-MariaDB", version_comment="MariaDB Server"
    )
    authorization = Phase2CImportAuthorization(**{**_authorization(plan).__dict__, "target_server_identity": identity})
    payload = _preflight(authorization)
    authorization = Phase2CImportAuthorization(**{**authorization.__dict__, "core_preflight_sha256": payload["audit_sha256"]})
    validate_core_preflight_payload(payload, authorization)
    payload["evidence_empty"] = False
    with pytest.raises(CoreImportError, match="invalid audit hash"):
        validate_core_preflight_payload(payload, authorization)


def test_host_preflight_must_pass_and_match_the_authorization() -> None:
    authorization = _authorization(_plan())
    payload = _host_preflight(authorization)
    authorization = Phase2CImportAuthorization(**{**authorization.__dict__, "host_preflight_sha256": payload["report_sha256"]})
    validate_host_preflight_payload(payload, authorization)
    payload["status"] = "BLOCKED"
    with pytest.raises(CoreImportError, match="invalid report hash"):
        validate_host_preflight_payload(payload, authorization)


def test_mutated_plan_is_rejected_before_authorization_or_connection() -> None:
    plan = _plan()
    plan["destination_rows"]["core_run"][0]["run_slot"] = "mutated-after-review"
    with pytest.raises(CoreImportError, match="SHA-256 does not match"):
        execute_import_plan(target_database="obsidiandroid_core_prod", plan=plan, connection_factory=None)


def test_valid_authorization_requires_a_durable_single_use_ledger_before_connection() -> None:
    plan = _plan()
    with pytest.raises(CoreImportError, match="durable single-use authorization ledger"):
        execute_import_plan(
            target_database="obsidiandroid_core_prod",
            plan=plan,
            connection_factory=lambda _target: (_ for _ in ()).throw(AssertionError("must not connect")),
            production_authorization=_authorization(plan),
        )


def test_authorization_is_rejected_for_a_disposable_target() -> None:
    plan = _plan()
    with pytest.raises(CoreImportError, match="cannot be used for a disposable"):
        execute_import_plan(
            target_database="od_core_phase2b_validate_20260719T211000Z",
            plan=plan,
            connection_factory=None,
            production_authorization=_authorization(plan),
        )


def test_file_consumption_ledger_rejects_reuse_and_writes_private_receipt(tmp_path: Path) -> None:
    authorization = _authorization(_plan())
    ledger = FileAuthorizationConsumptionLedger(tmp_path / "phase2c-authorizations")
    receipt = Path(ledger.consume(authorization))
    assert receipt.exists()
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert receipt.parent.stat().st_mode & 0o777 == 0o700
    with pytest.raises(CoreImportError, match="already been consumed"):
        ledger.consume(authorization)


def test_authorization_rejects_an_expired_record() -> None:
    plan = _plan()
    authorization = _authorization(plan)
    expired = Phase2CImportAuthorization(
        **{
            **authorization.__dict__,
            "issued_at_utc": "2026-01-01T00:00:00Z",
            "expires_at_utc": "2026-01-01T00:01:00Z",
        }
    )
    with pytest.raises(CoreImportError, match="has expired"):
        expired.validate_for(target_database="obsidiandroid_core_prod", plan=plan)


def test_importer_has_no_boolean_production_bypass() -> None:
    text = Path("src/obsidiandroid/core_migration/importer.py").read_text(encoding="utf-8")
    assert "allow_production: bool" not in text
    assert "production_authorization: Phase2CImportAuthorization | None" in text
    assert "authorization_consumption_ledger: AuthorizationConsumptionLedger | None" in text


def test_importer_preserves_structured_json_without_double_encoding() -> None:
    source_value = '{"source_observed_values":"one|two"}'
    assert _database_json(source_value) == source_value
    assert _database_json({"source_observed_values": "one|two"}) == source_value
