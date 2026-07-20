#!/usr/bin/env python3
"""Create the one reviewed, read-only Phase 2C Erebus extract package.

This command is deliberately not part of the pipeline or importer.  It is
locked to the approved diagnostic fixture, requires the dedicated reader
credential, opens one read-only consistent-snapshot transaction, and writes a
new content-addressed package outside the repository.  It never opens Core.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.mapping import SOURCE_SURFACES
from obsidiandroid.core_migration.source_extracts import (
    SOURCE_EXTRACT_MANIFEST_VERSION,
    canonical_hash,
    validate_source_extract_manifest,
)


FIXTURE_RUN_ID = "20260718T032717Z__a8cf01"
SOURCE_SCHEMA = "erebus_threat_intel_prod"
SERIALIZATION_VERSION = "canonical-jsonl-v1"
_REPO_ROOT = Path(__file__).resolve().parents[2]

_QUERIES: dict[str, tuple[str, tuple[str, ...], Callable[[dict[str, Any]], tuple[str, ...]]]] = {
    "analysis_run": (
        "SELECT run_id, created_at_utc, profile_id, git_commit, selection_rule_version, snapshot_sha256_hash, snapshot_row_count, vendor_constrained_run_flag, selected_vendor_count, included_vendor_count, excluded_vendor_count, notes FROM analysis_run WHERE run_id = %s ORDER BY run_id",
        ("run_id", "created_at_utc", "profile_id", "git_commit", "selection_rule_version", "snapshot_sha256_hash", "snapshot_row_count", "vendor_constrained_run_flag", "selected_vendor_count", "included_vendor_count", "excluded_vendor_count", "notes"),
        lambda row: (str(row["run_id"]),),
    ),
    "analysis_snapshot": (
        "SELECT run_id, extracted_at_utc, selection_rule_version, snapshot_sha256_hash, snapshot_row_count, vendor_constrained_run_flag, selected_vendor_count, included_vendor_count, excluded_vendor_count FROM analysis_snapshot WHERE run_id = %s ORDER BY run_id",
        ("run_id", "extracted_at_utc", "selection_rule_version", "snapshot_sha256_hash", "snapshot_row_count", "vendor_constrained_run_flag", "selected_vendor_count", "included_vendor_count", "excluded_vendor_count"),
        lambda row: (str(row["run_id"]),),
    ),
    "analysis_snapshot_sample": (
        "SELECT run_id, sha256, sample_id, family_id, family_canonical, type_slug, extracted_at_utc, feature_hash FROM analysis_snapshot_sample WHERE run_id = %s ORDER BY sha256, sample_id",
        ("run_id", "sha256", "sample_id", "family_id", "family_canonical", "type_slug", "extracted_at_utc", "feature_hash"),
        lambda row: (str(row.get("sha256") or ""), str(row.get("sample_id") or "")),
    ),
    "analysis_artifact": (
        "SELECT run_id, artifact_key, artifact_path, artifact_sha256, created_at_utc FROM analysis_artifact WHERE run_id = %s ORDER BY artifact_key",
        ("run_id", "artifact_key", "artifact_path", "artifact_sha256", "created_at_utc"),
        lambda row: (str(row["artifact_key"]),),
    ),
    "snapshot_label_conflict": (
        "SELECT run_id, sha256, conflict_type, observed_values, created_at_utc FROM snapshot_label_conflict WHERE run_id = %s ORDER BY sha256, conflict_type",
        ("run_id", "sha256", "conflict_type", "observed_values", "created_at_utc"),
        lambda row: (str(row.get("sha256") or ""), str(row["conflict_type"])),
    ),
}


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z") if value.tzinfo else value.isoformat(timespec="microseconds") + "Z"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _canonical_jsonl(rows: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps({key: _normalize(value) for key, value in row.items()}, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for row in rows]
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def _read_private_env(path: Path) -> dict[str, str]:
    path = Path(path).expanduser()
    try:
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise RuntimeError("Dedicated Erebus reader credential file is unavailable") from exc
    if not path.is_file() or mode & 0o077:
        raise RuntimeError("Dedicated Erebus reader credential file must be private (0600)")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or not value:
            raise RuntimeError("Dedicated Erebus reader credential file has an invalid entry")
        values[key] = value
    required = ("OBSIDIANDROID_DB_HOST", "OBSIDIANDROID_DB_PORT", "OBSIDIANDROID_DB_USER", "OBSIDIANDROID_DB_PASSWORD", "OBSIDIANDROID_DB_NAME")
    if any(not values.get(key) for key in required):
        raise RuntimeError("Dedicated Erebus reader credential file is incomplete")
    if values["OBSIDIANDROID_DB_NAME"] != SOURCE_SCHEMA or values["OBSIDIANDROID_DB_USER"] != "obsidiandroid_erebus_reader":
        raise RuntimeError("Refusing a credential that is not the dedicated approved Erebus reader")
    return values


def _connect(reader_env: dict[str, str]):
    return mysql.connector.connect(
        host=reader_env["OBSIDIANDROID_DB_HOST"],
        port=int(reader_env["OBSIDIANDROID_DB_PORT"]),
        user=reader_env["OBSIDIANDROID_DB_USER"],
        password=reader_env["OBSIDIANDROID_DB_PASSWORD"],
        database=SOURCE_SCHEMA,
        charset="utf8mb4",
        autocommit=False,
        connection_timeout=30,
    )


def _write_package(
    *,
    output_dir: Path,
    run_id: str,
    observed_at_utc: str,
    source_rows: dict[str, list[dict[str, Any]]],
    connection_encoding: dict[str, str] | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    connection_encoding = connection_encoding or {
        "character_set_connection": "utf8mb4",
        "collation_connection": "utf8mb4_unicode_ci",
    }
    if output_dir.exists():
        raise RuntimeError("Refusing to overwrite an existing Phase 2C extract package")
    if _REPO_ROOT == output_dir.resolve() or _REPO_ROOT in output_dir.resolve().parents:
        raise RuntimeError("Phase 2C source extracts must be written outside the repository")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        extracts_dir = staging / "extracts"
        extracts_dir.mkdir()
        entries: list[dict[str, Any]] = []
        checksums: list[tuple[str, str]] = []
        for surface in SOURCE_SURFACES:
            query, columns, natural_key = _QUERIES[surface]
            rows = source_rows[surface]
            raw = _canonical_jsonl(rows)
            relative_path = Path("extracts") / f"{surface}.jsonl.gz"
            target = staging / relative_path
            with target.open("wb") as handle:
                with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as compressed:
                    compressed.write(raw)
            compressed_bytes = target.read_bytes()
            key_rows = [{"key": list(natural_key(row))} for row in rows]
            entries.append(
                {
                    "source_table": surface,
                    "relative_path": relative_path.as_posix(),
                    "row_count": len(rows),
                    "column_contract_sha256": canonical_hash(list(columns)),
                    "extraction_sql_sha256": _sha256_bytes(query.encode("utf-8")),
                    "ordered_natural_key_sha256": canonical_hash(key_rows),
                    "content_sha256": _sha256_bytes(raw),
                    "compressed_file_sha256": _sha256_bytes(compressed_bytes),
                }
            )
            checksums.append((_sha256_bytes(compressed_bytes), relative_path.as_posix()))
        manifest: dict[str, Any] = {
            "manifest_version": SOURCE_EXTRACT_MANIFEST_VERSION,
            "source_schema": SOURCE_SCHEMA,
            "source_run_id": run_id,
            "observed_at_utc": observed_at_utc,
            "canonical_serialization_version": SERIALIZATION_VERSION,
            "connection_encoding": connection_encoding,
            "extracts": entries,
        }
        manifest["extract_manifest_sha256"] = canonical_hash(manifest)
        validate_source_extract_manifest(manifest)
        manifest_path = staging / "extract_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        checksums.append((_sha256_bytes(manifest_path.read_bytes()), manifest_path.name))
        (staging / "SHA256SUMS").write_text("".join(f"{digest}  {path}\n" for digest, path in sorted(checksums)), encoding="utf-8")
        os.chmod(staging, 0o700)
        for path in staging.rglob("*"):
            if path.is_file():
                os.chmod(path, 0o600)
            elif path.is_dir():
                os.chmod(path, 0o700)
        staging.rename(output_dir)
        return manifest
    except Exception:
        for path in sorted(staging.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        staging.rmdir()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-read-only-extract", action="store_true")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.approve_read_only_extract:
        raise SystemExit("Refusing: pass --approve-read-only-extract after separate approval")
    if args.run_id != FIXTURE_RUN_ID:
        raise SystemExit(f"Refusing: Phase 2C is approved only for fixture {FIXTURE_RUN_ID}")
    reader_env = _read_private_env(args.credential_file)
    connection = _connect(reader_env)
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT @@character_set_connection, @@collation_connection")
        encoding_row = cursor.fetchone()
        if not encoding_row or str(encoding_row[0]).casefold() != "utf8mb4":
            raise RuntimeError("Phase 2C extraction requires an utf8mb4 MariaDB connection")
        connection_encoding = {"character_set_connection": str(encoding_row[0]), "collation_connection": str(encoding_row[1])}
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
        source_rows: dict[str, list[dict[str, Any]]] = {}
        for surface in SOURCE_SURFACES:
            query, _, _ = _QUERIES[surface]
            cursor.execute(query, (args.run_id,))
            source_rows[surface] = list(cursor.fetchall())
        if len(source_rows["analysis_run"]) != 1:
            raise RuntimeError("Approved fixture must produce exactly one analysis_run row")
        if len(source_rows["analysis_snapshot"]) > 1:
            raise RuntimeError("Approved fixture must produce at most one analysis_snapshot row")
        observed_at_utc = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    finally:
        connection.rollback()
        cursor.close()
        connection.close()
    manifest = _write_package(output_dir=args.output_dir, run_id=args.run_id, observed_at_utc=observed_at_utc, source_rows=source_rows, connection_encoding=connection_encoding)
    print(f"READ-ONLY EXTRACT COMPLETE: run_id={args.run_id} manifest_sha256={manifest['extract_manifest_sha256']} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
