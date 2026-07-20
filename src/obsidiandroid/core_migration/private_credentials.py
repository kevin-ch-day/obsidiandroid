"""Strict, role-bound loaders for Phase 2C private ``.env`` credentials.

These helpers are intentionally separate from normal runtime configuration.
They never read process environment variables, shell-evaluate a file, or emit
secret values in an exception or representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import os
from pathlib import Path
import re

from .mapping import CoreImportError


_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


class Phase2CCredentialRole(StrEnum):
    """The three intentionally separated Phase 2C database identities."""

    EREBUS_READER = "erebus_reader"
    CORE_WRITER = "core_writer"
    CORE_AUDITOR = "core_auditor"


@dataclass(frozen=True)
class Phase2CCredentials:
    """Validated connection fields with a deliberately redacted representation."""

    role: Phase2CCredentialRole
    host: str
    port: int
    user: str
    password: str = field(repr=False)
    database: str


_ROLE_CONTRACTS = {
    Phase2CCredentialRole.EREBUS_READER: {
        "keys": {
            "OBSIDIANDROID_DB_HOST", "OBSIDIANDROID_DB_PORT", "OBSIDIANDROID_DB_USER",
            "OBSIDIANDROID_DB_PASSWORD", "OBSIDIANDROID_DB_NAME",
        },
        "host": "localhost",
        "user": "obsidiandroid_erebus_reader",
        "database": "erebus_threat_intel_prod",
        "mapping": {
            "host": "OBSIDIANDROID_DB_HOST", "port": "OBSIDIANDROID_DB_PORT",
            "user": "OBSIDIANDROID_DB_USER", "password": "OBSIDIANDROID_DB_PASSWORD",
            "database": "OBSIDIANDROID_DB_NAME",
        },
    },
    Phase2CCredentialRole.CORE_WRITER: {
        "keys": {
            "OBSIDIANDROID_CORE_DB_HOST", "OBSIDIANDROID_CORE_DB_PORT", "OBSIDIANDROID_CORE_DB_USER",
            "OBSIDIANDROID_CORE_DB_PASSWORD", "OBSIDIANDROID_CORE_DB_NAME", "OBSIDIANDROID_CORE_PERSISTENCE_ENABLED",
        },
        "host": "localhost",
        "user": "obsidiandroid_core_writer",
        "database": "obsidiandroid_core_prod",
        "mapping": {
            "host": "OBSIDIANDROID_CORE_DB_HOST", "port": "OBSIDIANDROID_CORE_DB_PORT",
            "user": "OBSIDIANDROID_CORE_DB_USER", "password": "OBSIDIANDROID_CORE_DB_PASSWORD",
            "database": "OBSIDIANDROID_CORE_DB_NAME",
        },
    },
    Phase2CCredentialRole.CORE_AUDITOR: {
        "keys": {
            "OBSIDIANDROID_DB_HOST", "OBSIDIANDROID_DB_PORT", "OBSIDIANDROID_DB_USER",
            "OBSIDIANDROID_DB_PASSWORD", "OBSIDIANDROID_DB_NAME",
        },
        "host": "localhost",
        "user": "obsidiandroid_core_auditor",
        "database": "obsidiandroid_core_prod",
        "mapping": {
            "host": "OBSIDIANDROID_DB_HOST", "port": "OBSIDIANDROID_DB_PORT",
            "user": "OBSIDIANDROID_DB_USER", "password": "OBSIDIANDROID_DB_PASSWORD",
            "database": "OBSIDIANDROID_DB_NAME",
        },
    },
}


def _private_path(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.suffix != ".env" or candidate.is_symlink() or not candidate.is_file():
        raise CoreImportError("Phase 2C credential file must be a regular private .env file")
    stat = candidate.stat()
    if stat.st_uid != os.geteuid():
        raise CoreImportError("Phase 2C credential file must be owned by the current operator")
    if stat.st_mode & 0o077:
        raise CoreImportError("Phase 2C credential file must be mode 0600")
    parent = candidate.parent
    if parent.is_symlink() or not parent.is_dir():
        raise CoreImportError("Phase 2C credential parent directory is invalid")
    parent_stat = parent.stat()
    if parent_stat.st_uid != os.geteuid() or parent_stat.st_mode & 0o077:
        raise CoreImportError("Phase 2C credential parent directory must be private and operator-owned")
    return candidate.resolve()


def _parse(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CoreImportError("Phase 2C credential file could not be read") from exc
    for raw_line in lines:
        if not raw_line or raw_line.startswith("#"):
            continue
        key, separator, value = raw_line.partition("=")
        if not separator or not _KEY.fullmatch(key) or not value:
            raise CoreImportError("Phase 2C credential file contains a malformed entry")
        if key in values:
            raise CoreImportError("Phase 2C credential file contains a duplicate key")
        values[key] = value
    return values


def load_phase2c_credentials(path: Path, role: Phase2CCredentialRole) -> Phase2CCredentials:
    """Load one exact Phase 2C role contract without logging a secret."""
    contract = _ROLE_CONTRACTS[role]
    values = _parse(_private_path(path))
    if set(values) != contract["keys"]:
        raise CoreImportError("Phase 2C credential file does not match the required role contract")
    if role is Phase2CCredentialRole.CORE_WRITER and values["OBSIDIANDROID_CORE_PERSISTENCE_ENABLED"].casefold() != "false":
        raise CoreImportError("Phase 2C Core writer credential requires persistence to remain disabled")
    mapping = contract["mapping"]
    try:
        port = int(values[mapping["port"]])
    except (KeyError, ValueError) as exc:
        raise CoreImportError("Phase 2C credential port must be numeric") from exc
    if not 1 <= port <= 65535:
        raise CoreImportError("Phase 2C credential port is out of range")
    if values[mapping["host"]] != contract["host"]:
        raise CoreImportError("Phase 2C credential host violates the localhost-only policy")
    if values[mapping["user"]] != contract["user"]:
        raise CoreImportError("Phase 2C credential identity does not match the required role")
    if values[mapping["database"]] != contract["database"]:
        raise CoreImportError("Phase 2C credential schema does not match the required role")
    return Phase2CCredentials(
        role=role, host=values[mapping["host"]], port=port, user=values[mapping["user"]],
        password=values[mapping["password"]], database=values[mapping["database"]],
    )
