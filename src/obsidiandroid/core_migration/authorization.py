"""Explicit, plan-bound authorization controls for a future Phase 2C import.

The normal application pipeline does not create, load, or consume these
records.  They protect one separately approved, controlled Core fixture
import; they are not a replacement for the required operator review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Protocol

from .mapping import CoreImportError


PRODUCTION_CORE_SCHEMA = "obsidiandroid_core_prod"
AUTHORIZATION_VERSION = "phase2c-import-auth-v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AUTHORIZATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def _canonical_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def mariadb_server_attestation(
    *, hostname: object, port: object, server_id: object, version: object, version_comment: object
) -> str:
    """Return the reviewed MariaDB-server attestation used by Phase 2C.

    MariaDB does not expose MySQL's ``@@server_uuid``.  This is deliberately
    called an *attestation*, not an immutable server UUID: the approved Core
    preflight records the five values and the importer compares the exact
    canonical hash immediately before writing.
    """
    return _canonical_hash(
        {
            "attestation_version": "mariadb-server-attestation-v1",
            "hostname": str(hostname),
            "port": int(port),
            "server_id": int(server_id),
            "version": str(version),
            "version_comment": str(version_comment),
        }
    )


def validate_core_preflight_payload(payload: dict[str, Any], authorization: "Phase2CImportAuthorization") -> None:
    """Require the exact, self-verifying Core audit approved for this import."""
    if not isinstance(payload, dict):
        raise CoreImportError("Production Core import requires the reviewed Core preflight payload")
    observed_hash = str(payload.get("audit_sha256") or "")
    canonical = dict(payload)
    canonical.pop("audit_sha256", None)
    if not _SHA256.fullmatch(observed_hash) or observed_hash != _canonical_hash(canonical):
        raise CoreImportError("Production Core preflight payload has an invalid audit hash")
    if observed_hash != authorization.core_preflight_sha256:
        raise CoreImportError("Production Core preflight hash does not match the authorization")
    if payload.get("target") != authorization.target_database:
        raise CoreImportError("Production Core preflight names a different target database")
    if not payload.get("table_contract_ok") or not payload.get("migration_contract_ok"):
        raise CoreImportError("Production Core preflight reports an invalid schema or migration contract")
    if not payload.get("evidence_empty"):
        raise CoreImportError("Production Core preflight requires an empty evidence ledger")
    attestation = payload.get("server_attestation")
    if not isinstance(attestation, dict) or attestation.get("sha256") != authorization.target_server_identity:
        raise CoreImportError("Production Core preflight server attestation does not match the authorization")


def validate_host_preflight_payload(payload: dict[str, Any], authorization: "Phase2CImportAuthorization") -> None:
    """Require the reviewed, self-verifying host capability gate at execution."""
    if not isinstance(payload, dict):
        raise CoreImportError("Production Core import requires the reviewed host preflight payload")
    observed_hash = str(payload.get("report_sha256") or "")
    canonical = dict(payload)
    canonical.pop("report_sha256", None)
    if not _SHA256.fullmatch(observed_hash) or observed_hash != _canonical_hash(canonical):
        raise CoreImportError("Production host preflight payload has an invalid report hash")
    if observed_hash != authorization.host_preflight_sha256:
        raise CoreImportError("Production host preflight hash does not match the authorization")
    if payload.get("report_version") != "obsidiandroid-host-preflight-v1" or payload.get("status") != "PASS":
        raise CoreImportError("Production host preflight did not pass the required capability gate")


def require_clean_repository_at_commit(repository_root: Path, expected_commit: str) -> None:
    """Fail closed when executable source differs from the reviewed Git commit."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository_root, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CoreImportError("Production Core import requires a verifiable Git checkout") from exc
    if head != expected_commit:
        raise CoreImportError("Production Core import checkout does not match the authorized repository commit")
    if dirty.strip():
        raise CoreImportError("Production Core import requires a clean working tree")


def _parse_utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CoreImportError(f"Phase 2C authorization {label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CoreImportError(f"Phase 2C authorization {label} must include a UTC offset")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class Phase2CImportAuthorization:
    """Human-reviewed authority for exactly one deterministic Core import.

    The record binds both the reviewed source package and the target-side
    preflight.  A separate, private consumption ledger is required at runtime
    so that an authorization cannot be replayed after an attempted execution.
    """

    authorization_id: str
    approved_by: str
    authorized_operator: str
    target_database: str
    target_server_identity: str
    writer_account: str
    source_run_id: str
    plan_sha256: str
    source_extract_manifest_sha256: str
    mapping_contract_version: str
    repository_commit: str
    migration_checksums: dict[str, str]
    expected_counts: dict[str, int]
    core_preflight_sha256: str
    host_preflight_sha256: str
    issued_at_utc: str
    expires_at_utc: str
    fixture_classification: str
    authorization_version: str = AUTHORIZATION_VERSION
    single_use: bool = True
    max_execution_count: int = 1
    persistence_must_remain_disabled: bool = True

    def canonical_hash(self) -> str:
        """Return a stable identity for the reviewed authorization contents."""
        return _canonical_hash(asdict(self))

    def validate_for(self, *, target_database: str, plan: dict[str, Any]) -> None:
        """Fail closed unless this record names the exact production plan."""
        required_text = {
            "authorization_id": self.authorization_id,
            "approved_by": self.approved_by,
            "authorized_operator": self.authorized_operator,
            "target_server_identity": self.target_server_identity,
            "writer_account": self.writer_account,
            "fixture_classification": self.fixture_classification,
        }
        if any(not value.strip() for value in required_text.values()):
            raise CoreImportError("Phase 2C authorization requires all identity and fixture fields")
        if not _AUTHORIZATION_ID.fullmatch(self.authorization_id):
            raise CoreImportError("Phase 2C authorization_id contains unsafe receipt-path characters")
        if self.authorization_version != AUTHORIZATION_VERSION:
            raise CoreImportError("Phase 2C authorization version is unsupported")
        if self.target_database != PRODUCTION_CORE_SCHEMA or target_database != PRODUCTION_CORE_SCHEMA:
            raise CoreImportError("Phase 2C authorization is valid only for the production Core schema")
        if not self.single_use or self.max_execution_count != 1:
            raise CoreImportError("Phase 2C authorization must be explicitly single-use")
        if not self.persistence_must_remain_disabled:
            raise CoreImportError("Phase 2C authorization cannot enable normal Core persistence")
        for label, value in {
            "plan_sha256": self.plan_sha256,
            "source_extract_manifest_sha256": self.source_extract_manifest_sha256,
            "core_preflight_sha256": self.core_preflight_sha256,
            "host_preflight_sha256": self.host_preflight_sha256,
        }.items():
            if not _SHA256.fullmatch(value):
                raise CoreImportError(f"Phase 2C authorization {label} must be a lowercase SHA-256")
        if not _SHA256.fullmatch(self.target_server_identity):
            raise CoreImportError("Phase 2C authorization target_server_identity must be a MariaDB attestation SHA-256")
        if set(self.migration_checksums) != {"0001", "0002"} or not all(_SHA256.fullmatch(value) for value in self.migration_checksums.values()):
            raise CoreImportError("Phase 2C authorization must bind the exact 0001 and 0002 checksums")
        if not _GIT_OBJECT_ID.fullmatch(self.repository_commit):
            raise CoreImportError("Phase 2C authorization repository_commit must be a full Git object ID")
        if any(not isinstance(value, int) or value < 0 for value in self.expected_counts.values()):
            raise CoreImportError("Phase 2C authorization expected_counts must contain non-negative integers")
        issued = _parse_utc(self.issued_at_utc, "issued_at_utc")
        expires = _parse_utc(self.expires_at_utc, "expires_at_utc")
        if expires <= issued:
            raise CoreImportError("Phase 2C authorization expiry must be after issuance")
        if datetime.now(UTC) > expires:
            raise CoreImportError("Phase 2C authorization has expired")
        execution_contract = plan.get("phase2c_execution_contract")
        if not isinstance(execution_contract, dict):
            raise CoreImportError("Phase 2C plan lacks its reviewed execution contract")
        if self.source_run_id != str(plan.get("source_run_id") or ""):
            raise CoreImportError("Phase 2C authorization run identity does not match the import plan")
        if self.plan_sha256 != str(plan.get("plan_sha256") or ""):
            raise CoreImportError("Phase 2C authorization hash does not match the import plan")
        if self.source_extract_manifest_sha256 != str(execution_contract.get("source_extract_manifest_sha256") or ""):
            raise CoreImportError("Phase 2C authorization extract manifest does not match the import plan")
        if self.mapping_contract_version != str(plan.get("mapping_contract_version") or ""):
            raise CoreImportError("Phase 2C authorization mapping contract does not match the import plan")
        if self.repository_commit != str(execution_contract.get("repository_commit") or ""):
            raise CoreImportError("Phase 2C authorization repository commit does not match the import plan")
        if self.migration_checksums != execution_contract.get("migration_checksums"):
            raise CoreImportError("Phase 2C authorization migration checksums do not match the import plan")
        if self.expected_counts != plan.get("expected_counts"):
            raise CoreImportError("Phase 2C authorization expected counts do not match the import plan")


class AuthorizationConsumptionLedger(Protocol):
    """Durably consume a reviewed authorization before any Core connection."""

    def consume(self, authorization: Phase2CImportAuthorization) -> str:
        """Return a receipt path or raise if this authorization was used before."""


@dataclass(frozen=True)
class FileAuthorizationConsumptionLedger:
    """Minimal private, append-only receipt store for one-time authorizations.

    This is intentionally external to Core: it can record an attempted import
    even if the Core transaction later rolls back.  The caller must provide a
    protected directory outside the repository and preserve it with receipts.
    """

    directory: Path

    def consume(self, authorization: Phase2CImportAuthorization) -> str:
        directory = Path(self.directory)
        directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError as exc:
            raise CoreImportError("Cannot protect the Phase 2C authorization receipt directory") from exc
        path = directory / f"{authorization.authorization_id}.consumed.json"
        payload = {
            "receipt_version": "phase2c-authorization-consumption-v1",
            "authorization_id": authorization.authorization_id,
            "authorization_sha256": authorization.canonical_hash(),
            "plan_sha256": authorization.plan_sha256,
            "source_run_id": authorization.source_run_id,
            "consumed_at_utc": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise CoreImportError("Phase 2C authorization has already been consumed") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return str(path)
