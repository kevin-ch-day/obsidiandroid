"""Offline tests for the frozen Phase 2C source-extract manifest contract."""

from __future__ import annotations

from hashlib import sha256
import json

import pytest

from obsidiandroid.core_migration.mapping import CoreImportError, SOURCE_SURFACES
from obsidiandroid.core_migration.source_extracts import SOURCE_EXTRACT_MANIFEST_VERSION, validate_source_extract_manifest


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _manifest() -> dict:
    manifest = {
        "manifest_version": SOURCE_EXTRACT_MANIFEST_VERSION,
        "source_schema": "erebus_threat_intel_prod",
        "source_run_id": "fixture-run",
        "observed_at_utc": "2026-07-19T12:00:00Z",
        "canonical_serialization_version": "canonical-jsonl-v1",
        "connection_encoding": {
            "character_set_connection": "utf8mb4",
            "collation_connection": "utf8mb4_unicode_ci",
        },
        "extracts": [
            {
                "source_table": surface,
                "relative_path": f"extracts/{surface}.jsonl.gz",
                "row_count": 0 if surface == "snapshot_label_conflict" else 1,
                "column_contract_sha256": _hash(f"{surface}:columns"),
                "extraction_sql_sha256": _hash(f"{surface}:sql"),
                "ordered_natural_key_sha256": _hash(f"{surface}:keys"),
                "content_sha256": _hash(f"{surface}:content"),
                "compressed_file_sha256": _hash(f"{surface}:compressed"),
            }
            for surface in SOURCE_SURFACES
        ],
    }
    manifest["extract_manifest_sha256"] = sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return manifest


def test_source_extract_manifest_accepts_an_explicit_zero_conflict_extract() -> None:
    manifest = _manifest()
    assert validate_source_extract_manifest(manifest) == manifest["extract_manifest_sha256"]


def test_source_extract_manifest_rejects_missing_zero_conflict_surface() -> None:
    manifest = _manifest()
    manifest["extracts"] = [entry for entry in manifest["extracts"] if entry["source_table"] != "snapshot_label_conflict"]
    manifest["extract_manifest_sha256"] = sha256(
        json.dumps({key: value for key, value in manifest.items() if key != "extract_manifest_sha256"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(CoreImportError, match="each approved source surface"):
        validate_source_extract_manifest(manifest)


def test_source_extract_manifest_rejects_tampered_content_after_hashing() -> None:
    manifest = _manifest()
    manifest["extracts"][0]["row_count"] = 2
    with pytest.raises(CoreImportError, match="hash does not match"):
        validate_source_extract_manifest(manifest)
