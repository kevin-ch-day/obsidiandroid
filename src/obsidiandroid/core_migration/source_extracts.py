"""Validation contract for a reviewed, frozen Phase 2C source-extract package.

These helpers perform no database I/O.  A separately approved extraction tool
will later materialize the package using the dedicated Erebus reader; the Core
importer must receive the resulting plan, not a live source connection.
"""

from __future__ import annotations

from datetime import datetime
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .mapping import CoreImportError, SOURCE_SURFACES


SOURCE_EXTRACT_MANIFEST_VERSION = "phase2c-source-extract-manifest-v1"
_SHA256_HEX = frozenset("0123456789abcdef")


def canonical_hash(value: object) -> str:
    """Hash canonical JSON without accepting presentation-level variation."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _sha256(value: object, label: str) -> str:
    rendered = str(value or "")
    if len(rendered) != 64 or any(character not in _SHA256_HEX for character in rendered):
        raise CoreImportError(f"Phase 2C source extract {label} must be a lowercase SHA-256")
    return rendered


def _utc_timestamp(value: object, label: str) -> str:
    rendered = str(value or "")
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CoreImportError(f"Phase 2C source extract {label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise CoreImportError(f"Phase 2C source extract {label} must include a UTC offset")
    return rendered


def validate_source_extract_manifest(manifest: dict[str, Any]) -> str:
    """Validate a complete, content-addressed five-surface package.

    Returns the verified manifest SHA-256.  In particular, a zero-row conflict
    surface still requires an explicit extract entry and content hashes.
    """
    declared_hash = _sha256(manifest.get("extract_manifest_sha256"), "extract_manifest_sha256")
    canonical = dict(manifest)
    canonical.pop("extract_manifest_sha256", None)
    if declared_hash != canonical_hash(canonical):
        raise CoreImportError("Phase 2C source extract manifest hash does not match its canonical contents")
    if manifest.get("manifest_version") != SOURCE_EXTRACT_MANIFEST_VERSION:
        raise CoreImportError("Phase 2C source extract manifest version is unsupported")
    if str(manifest.get("source_schema") or "") != "erebus_threat_intel_prod":
        raise CoreImportError("Phase 2C source extract manifest names an unapproved source schema")
    if not str(manifest.get("source_run_id") or "").strip():
        raise CoreImportError("Phase 2C source extract manifest requires source_run_id")
    _utc_timestamp(manifest.get("observed_at_utc"), "observed_at_utc")
    if not str(manifest.get("canonical_serialization_version") or "").strip():
        raise CoreImportError("Phase 2C source extract manifest requires a canonical serialization version")
    connection_encoding = manifest.get("connection_encoding")
    if not isinstance(connection_encoding, dict) or str(connection_encoding.get("character_set_connection") or "").casefold() != "utf8mb4":
        raise CoreImportError("Phase 2C source extract manifest requires an utf8mb4 connection attestation")
    if not str(connection_encoding.get("collation_connection") or "").strip():
        raise CoreImportError("Phase 2C source extract manifest requires its connection collation")
    extracts = manifest.get("extracts")
    if not isinstance(extracts, list) or len(extracts) != len(SOURCE_SURFACES):
        raise CoreImportError("Phase 2C source extract manifest must contain each approved source surface once")
    observed_surfaces: set[str] = set()
    for entry in extracts:
        if not isinstance(entry, dict):
            raise CoreImportError("Phase 2C source extract manifest contains a non-object extract entry")
        surface = str(entry.get("source_table") or "")
        if surface not in SOURCE_SURFACES or surface in observed_surfaces:
            raise CoreImportError("Phase 2C source extract manifest has an unapproved or duplicate source surface")
        observed_surfaces.add(surface)
        if int(entry.get("row_count", -1)) < 0:
            raise CoreImportError("Phase 2C source extract row_count must be non-negative")
        if not str(entry.get("relative_path") or "").strip():
            raise CoreImportError("Phase 2C source extract entry requires a relative path")
        for field in (
            "column_contract_sha256",
            "extraction_sql_sha256",
            "ordered_natural_key_sha256",
            "content_sha256",
            "compressed_file_sha256",
        ):
            _sha256(entry.get(field), f"{surface}.{field}")
    if observed_surfaces != set(SOURCE_SURFACES):
        raise CoreImportError("Phase 2C source extract manifest does not cover the approved source surfaces")
    return declared_hash


def load_verified_source_extract_package(package_dir: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Read a frozen package only after its manifest and every payload verify.

    This is deliberately filesystem-only: it never connects to a source or
    Core database.  The returned rows are suitable for deterministic plan
    generation, not for mutating a source system.
    """
    package = Path(package_dir)
    manifest_path = package / "extract_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoreImportError("Phase 2C source extract manifest is unavailable or invalid JSON") from exc
    validate_source_extract_manifest(manifest)
    rows_by_surface: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest["extracts"]:
        surface = str(entry["source_table"])
        relative_path = Path(str(entry["relative_path"]))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise CoreImportError("Phase 2C source extract manifest contains an unsafe relative path")
        payload_path = package / relative_path
        try:
            compressed = payload_path.read_bytes()
        except OSError as exc:
            raise CoreImportError(f"Phase 2C source extract payload is unavailable: {surface}") from exc
        if sha256(compressed).hexdigest() != entry["compressed_file_sha256"]:
            raise CoreImportError(f"Phase 2C source extract compressed hash mismatch: {surface}")
        try:
            raw = gzip.decompress(compressed)
        except gzip.BadGzipFile as exc:
            raise CoreImportError(f"Phase 2C source extract payload is invalid gzip: {surface}") from exc
        if sha256(raw).hexdigest() != entry["content_sha256"]:
            raise CoreImportError(f"Phase 2C source extract content hash mismatch: {surface}")
        try:
            rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoreImportError(f"Phase 2C source extract JSONL is invalid: {surface}") from exc
        if any(not isinstance(row, dict) for row in rows):
            raise CoreImportError(f"Phase 2C source extract JSONL row is not an object: {surface}")
        if len(rows) != int(entry["row_count"]):
            raise CoreImportError(f"Phase 2C source extract row count mismatch: {surface}")
        rows_by_surface[surface] = rows
    if set(rows_by_surface) != set(SOURCE_SURFACES):
        raise CoreImportError("Phase 2C source extract package does not contain every approved surface")
    return manifest, rows_by_surface
