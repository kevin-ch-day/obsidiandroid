#!/usr/bin/env python3
"""Create a checksum-bound Core backup and rehearse it only into a disposable schema.

This tool is separate from the pipeline and Phase 2C importer. ``--create``
only reads Core through ``mariadb-dump``; ``--rehearse --apply`` restores only
to a named, previously absent ``od_core_restore_*`` schema. Credentials are
read solely from a private option file and never written to manifests.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

REPO_ROOT = prepare_script_runtime(__file__)
CORE_SCHEMA = "obsidiandroid_core_prod"
MANIFEST_VERSION = "obsidiandroid-core-backup-v1"
_TARGET = re.compile(r"^od_core_restore_[a-z0-9_]{1,96}$")


def _canonical_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _private_option_file(path: Path) -> Path:
    path = Path(path).expanduser()
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise RuntimeError("A private MariaDB option file (0600) is required")
    return path


def _outside_repository(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise RuntimeError("Core backup packages must be stored outside the repository")
    return path


def _require_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise RuntimeError(f"Required command is unavailable: {name}")
    return binary


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_failure_receipt(path: Path, *, operation: str, error: BaseException, context: dict[str, str]) -> Path | None:
    """Preserve a credential-free, one-attempt recovery failure receipt.

    The receipt intentionally records the exception *type*, not its message:
    client errors can include transport or authentication details that do not
    belong in a retained operational artifact.  An existing receipt is never
    overwritten, preserving the first failure evidence for that attempted
    output or restore target.
    """
    if path.exists():
        return None
    payload = {
        "receipt_version": "obsidiandroid-core-backup-failure-v1",
        "status": "failed",
        "operation": operation,
        "failed_at_utc": _utc_now(),
        "error_type": type(error).__name__,
        "context": dict(context),
        "operator_action": (
            "Preserve this receipt. Inspect only the named disposable target, if any, "
            "before a separately reviewed cleanup or retry."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    return path


def _connect(option_file: Path, database: str | None = None):
    kwargs: dict[str, Any] = {"option_files": str(option_file), "autocommit": False}
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def _core_inventory(option_file: Path, database: str) -> dict[str, Any]:
    connection = _connect(option_file, database)
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT @@version, @@version_comment, @@hostname, @@port, @@server_id")
        server = cursor.fetchone()
        cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME", (database,))
        tables = [str(row[0]) for row in cursor.fetchall()]
        counts: dict[str, int] = {}
        structures: dict[str, str] = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM `{database}`.`{table}`")
            counts[table] = int(cursor.fetchone()[0])
            cursor.execute(f"SHOW CREATE TABLE `{database}`.`{table}`")
            structures[table] = str(cursor.fetchone()[1])
        cursor.execute("SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s", (database,))
        routines = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s", (database,))
        triggers = int(cursor.fetchone()[0])
        return {
            "database": database,
            "server": {"version": str(server[0]), "version_comment": str(server[1]), "hostname": str(server[2]), "port": int(server[3]), "server_id": int(server[4])},
            "tables": tables, "row_counts": counts, "table_structure_sha256": _canonical_hash(structures),
            "routine_count": routines, "trigger_count": triggers,
        }
    finally:
        cursor.close()
        connection.close()


def _manifest_hash(manifest: dict[str, Any]) -> str:
    canonical = dict(manifest)
    canonical.pop("manifest_sha256", None)
    return _canonical_hash(canonical)


def _write_gzip_dump(command: list[str], destination: Path) -> None:
    """Run ``mariadb-dump`` and gzip its stdout without bypassing the codec.

    Passing a :class:`gzip.GzipFile` directly as ``subprocess`` stdout is not
    safe: ``subprocess`` uses its underlying file descriptor and bypasses
    ``GzipFile.write``.  Stage the compact Core dump in a temporary file, then
    stream that file through the gzip writer so the declared compression and
    bytes on disk always agree.
    """
    with tempfile.TemporaryFile() as plain_dump:
        completed = subprocess.run(command, stdout=plain_dump, stderr=subprocess.PIPE, check=False)
        if completed.returncode:
            raise RuntimeError("Core backup dump failed; inspect the protected MariaDB client configuration")
        plain_dump.seek(0)
        with destination.open("wb") as raw_output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, mtime=0) as output:
                shutil.copyfileobj(plain_dump, output)


def create_backup(*, option_file: Path, output_dir: Path) -> dict[str, Any]:
    """Read Core and create a new immutable dump package outside the repository."""
    option_file = _private_option_file(option_file)
    output_dir = _outside_repository(output_dir)
    if output_dir.exists():
        raise RuntimeError("Refusing to overwrite an existing Core backup package")
    inventory = _core_inventory(option_file, CORE_SCHEMA)
    dump_binary = _require_binary("mariadb-dump")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    dump_path = staging / "obsidiandroid_core_prod.sql.gz"
    command = [dump_binary, f"--defaults-extra-file={option_file}", "--single-transaction", "--routines", "--events", "--triggers", "--default-character-set=utf8mb4", "--databases", CORE_SCHEMA]
    try:
        _write_gzip_dump(command, dump_path)
        dump_sha = sha256(dump_path.read_bytes()).hexdigest()
        manifest: dict[str, Any] = {
            "manifest_version": MANIFEST_VERSION, "created_at_utc": _utc_now(), "source_schema": CORE_SCHEMA,
            "dump": {"relative_path": dump_path.name, "sha256": dump_sha, "compression": "gzip"},
            "dump_contract": {"single_transaction": True, "routines": True, "events": True, "triggers": True, "default_character_set": "utf8mb4", "credentials_in_manifest": False},
            "source_inventory": inventory,
        }
        manifest["manifest_sha256"] = _manifest_hash(manifest)
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (staging / "SHA256SUMS").write_text(f"{dump_sha}  {dump_path.name}\n{sha256(manifest_path.read_bytes()).hexdigest()}  manifest.json\n", encoding="utf-8")
        for path in staging.iterdir():
            path.chmod(0o600)
        staging.chmod(0o700)
        staging.rename(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _load_backup(package_dir: Path) -> tuple[dict[str, Any], Path]:
    package_dir = _outside_repository(package_dir)
    try:
        manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Core backup manifest is unavailable or invalid") from exc
    if manifest.get("manifest_version") != MANIFEST_VERSION or manifest.get("source_schema") != CORE_SCHEMA:
        raise RuntimeError("Backup package is not an approved Core backup")
    if manifest.get("manifest_sha256") != _manifest_hash(manifest):
        raise RuntimeError("Core backup manifest hash mismatch")
    dump = package_dir / str(manifest.get("dump", {}).get("relative_path") or "")
    if not dump.is_file() or sha256(dump.read_bytes()).hexdigest() != manifest.get("dump", {}).get("sha256"):
        raise RuntimeError("Core backup dump checksum mismatch")
    return manifest, dump


def _validate_restore_target(target: str) -> str:
    if not _TARGET.fullmatch(target) or target.casefold() == CORE_SCHEMA:
        raise RuntimeError("Core restore target must be a new od_core_restore_* schema")
    return target


def _retarget_dump_line(line: str, target: str) -> str:
    """Retarget only Core schema tokens in a MariaDB dump stream."""
    return line.replace(f"`{CORE_SCHEMA}`", f"`{target}`").replace(f"USE {CORE_SCHEMA};", f"USE {target};")


def rehearse_restore(*, option_file: Path, package_dir: Path, target_schema: str, apply: bool) -> dict[str, Any]:
    """Validate, and only with ``apply=True``, restore into a disposable Core schema."""
    option_file = _private_option_file(option_file)
    target_schema = _validate_restore_target(target_schema)
    manifest, dump_path = _load_backup(package_dir)
    connection = _connect(option_file)
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (target_schema,))
        if int(cursor.fetchone()[0]):
            raise RuntimeError("Disposable Core restore target already exists")
    finally:
        cursor.close()
        connection.close()
    result: dict[str, Any] = {"dry_run": not apply, "source_schema": CORE_SCHEMA, "target_schema": target_schema, "backup_manifest_sha256": manifest["manifest_sha256"]}
    if not apply:
        return result
    client = _require_binary("mariadb")
    with gzip.open(dump_path, "rt", encoding="utf-8", errors="strict") as source:
        transformed = "".join(_retarget_dump_line(line, target_schema) for line in source)
    completed = subprocess.run([client, f"--defaults-extra-file={option_file}"], input=transformed, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode:
        raise RuntimeError("Disposable Core restore failed; retained target may require manual inspection")
    restored = _core_inventory(option_file, target_schema)
    source_inventory = manifest["source_inventory"]
    result["validation"] = {
        "table_set_matches": restored["tables"] == source_inventory["tables"],
        "row_counts_match": restored["row_counts"] == source_inventory["row_counts"],
        "table_structure_matches": restored["table_structure_sha256"] == source_inventory["table_structure_sha256"],
        "routine_count_matches": restored["routine_count"] == source_inventory["routine_count"],
        "trigger_count_matches": restored["trigger_count"] == source_inventory["trigger_count"],
    }
    result["status"] = "PASS" if all(result["validation"].values()) else "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-file", type=Path, required=True)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--rehearse", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--target-schema")
    parser.add_argument("--apply", action="store_true", help="Actually create and retain the disposable restore schema.")
    args = parser.parse_args()
    if args.create == args.rehearse:
        raise SystemExit("Choose exactly one of --create or --rehearse")
    if args.create:
        if args.apply or args.output_dir is None:
            raise SystemExit("Core backup creation requires --create and --output-dir; --apply is not valid")
        output_dir = _outside_repository(args.output_dir)
        try:
            result = create_backup(option_file=args.option_file, output_dir=output_dir)
        except Exception as exc:
            _write_failure_receipt(
                output_dir.parent / f"{output_dir.name}.failure_receipt.json",
                operation="create_backup",
                error=exc,
                context={"requested_output_dir": str(output_dir)},
            )
            raise
    else:
        if args.backup_dir is None or not args.target_schema:
            raise SystemExit("Core restore rehearsal requires --backup-dir and --target-schema")
        package_dir = _outside_repository(args.backup_dir)
        try:
            result = rehearse_restore(
                option_file=args.option_file,
                package_dir=package_dir,
                target_schema=args.target_schema,
                apply=args.apply,
            )
        except Exception as exc:
            _write_failure_receipt(
                package_dir.parent / f"{package_dir.name}.{args.target_schema}.restore_failure_receipt.json",
                operation="rehearse_restore",
                error=exc,
                context={"backup_dir": str(package_dir), "target_schema": str(args.target_schema)},
            )
            raise
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
