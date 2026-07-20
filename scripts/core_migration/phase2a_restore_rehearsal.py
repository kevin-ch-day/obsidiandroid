#!/usr/bin/env python3
"""Run the separately authorized, disposable Phase 2A recovery rehearsal.

This tool never targets production or ``obsidiandroid_core_prod``.  It requires
``--apply`` before it creates its two explicitly named restore schemas.  It
validates the July 19 backup manifests, refuses a running event scheduler,
rewrites only schema-selection/qualified-schema DDL references while streaming
the dumps, and writes checksum-protected recovery receipts outside the backup
directories. It selects the newest complete manifest for each source, so a
replacement backup can be rehearsed without altering historical artifacts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from scripts._bootstrap import prepare_script_runtime

ROOT = prepare_script_runtime(__file__)
from obsidiandroid.database import db_config  # noqa: E402

BACKUP_ROOT = Path("/mnt/MERCURY_DATA_V2/mercury_backups")
RECEIPT_ROOT = Path("/mnt/MERCURY_DATA_V2/mercury_restore_checks/obsidiandroid_phase2a")
TARGETS = {
    "erebus_threat_intel_prod": "od_phase2a_restore_20260719_r2_erebus",
    "android_permission_intel": "od_phase2a_restore_20260719_permission",
}
FORBIDDEN_TARGETS = {*TARGETS, "erebus_threat_intel_prod", "android_permission_intel", "obsidiandroid_core_prod", "scytaledroid_core_prod"}
REPRESENTATIVE_TABLES = {
    "erebus_threat_intel_prod": (
        "analysis_run", "analysis_snapshot", "analysis_snapshot_sample", "analysis_artifact", "schema_migrations",
        "android_malware_family", "android_malware_family_alias", "malware_sample_catalog", "virustotal_sample_vendor_engine_verdicts",
    ),
    "android_permission_intel": (
        "schema_migrations", "android_permission_dict_unknown", "android_permission_obs_sample",
        "android_permission_authority_fact", "android_permission_concept", "android_permission_token_alias",
    ),
}


@dataclass(frozen=True)
class BackupSpec:
    source_schema: str
    target_schema: str
    backup_id: str
    dump_path: Path
    schema_path: Path
    manifest_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _mysql_command(*, database: str | None = None, query: str | None = None) -> list[str]:
    command = [
        shutil.which("mariadb") or "mariadb", "--no-defaults", "--protocol=TCP",
        f"--host={db_config.DB_HOST}", f"--port={int(db_config.DB_PORT)}", f"--user={db_config.DB_USER}",
        "--batch", "--skip-column-names", "--show-warnings",
    ]
    if database:
        command.append(f"--database={database}")
    if query:
        command.extend(["--execute", query])
    return command


def _mysql_env() -> dict[str, str]:
    env = dict(os.environ)
    env["MYSQL_PWD"] = str(db_config.DB_PASSWORD)
    return env


def _run_mysql(*, database: str | None = None, query: str) -> str:
    completed = subprocess.run(
        _mysql_command(database=database, query=query), env=_mysql_env(), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"MariaDB command failed ({completed.returncode}): {completed.stderr.strip()}")
    return completed.stdout


def _assert_safe_target(target: str) -> None:
    if not re.fullmatch(r"od_phase2a_restore_[a-z0-9_]+", target):
        raise ValueError(f"invalid disposable restore target: {target!r}")
    if target.casefold() in {name.casefold() for name in FORBIDDEN_TARGETS if not name.startswith("od_phase2a_restore_")}:
        raise ValueError(f"forbidden target: {target!r}")


def _load_backup(source_schema: str, target_schema: str) -> BackupSpec:
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for date_dir in sorted(BACKUP_ROOT.iterdir() if BACKUP_ROOT.is_dir() else ()):
        directory = date_dir / source_schema
        if not directory.is_dir():
            continue
        manifest_paths = [directory / "manifest.json"]
        manifest_paths.extend(child / "manifest.json" for child in sorted(directory.iterdir()) if child.is_dir())
        for manifest_path in manifest_paths:
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if manifest.get("database") != source_schema or manifest.get("backup_kind") != "full":
                continue
            dump_path = manifest_path.parent / str(manifest.get("dump_file", ""))
            schema_path = manifest_path.parent / str(manifest.get("schema_file", ""))
            if dump_path.is_file() and schema_path.is_file():
                candidates.append((str(manifest.get("created_at", "")), manifest_path, manifest))
    if not candidates:
        raise RuntimeError(f"no complete full backup manifest found for {source_schema}")
    _, manifest_path, manifest = max(candidates, key=lambda item: item[0])
    if manifest.get("verified") is not False:
        raise RuntimeError(f"unexpected backup manifest state for {source_schema}")
    dump_path = manifest_path.parent / str(manifest["dump_file"])
    schema_path = manifest_path.parent / str(manifest["schema_file"])
    return BackupSpec(source_schema, target_schema, str(manifest["backup_id"]), dump_path, schema_path, manifest_path)


def _verify_backup(spec: BackupSpec) -> dict[str, Any]:
    checksum_path = spec.manifest_path.parent / "checksum.sha256"
    checks = [line.strip().split(maxsplit=1) for line in checksum_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {name.lstrip(" *"): digest for digest, name in checks}
    result: dict[str, Any] = {"backup_id": spec.backup_id, "manifest_verified_flag": False, "files": []}
    for path in (spec.dump_path, spec.schema_path):
        with gzip.open(path, "rb") as handle:
            while handle.read(1024 * 1024):
                pass
        actual = _sha256(path)
        expected_digest = expected.get(path.name)
        if actual != expected_digest:
            raise RuntimeError(f"backup checksum mismatch: {path.name}")
        result["files"].append({"name": path.name, "sha256": actual, "gzip_integrity": "pass"})
    return result


def _transform_line(line: str, replacements: dict[str, str]) -> str | None:
    """Remove dump database-selection lines and retarget qualified identifiers."""
    # Most full-dump lines are bulk data and cannot contain a DDL reference.
    # Avoid regex work on them; the slower path remains mandatory for every
    # line that could carry a source-schema or definer reference.
    if (
        "DEFINER=" not in line
        and not line.startswith("CREATE DATABASE")
        and not line.startswith("USE ")
        and not any(source_schema in line for source_schema in replacements)
    ):
        return line
    for source_schema in replacements:
        if re.match(rf"^CREATE DATABASE .*`{re.escape(source_schema)}`", line):
            return None
        if re.match(rf"^USE\s+`{re.escape(source_schema)}`;\s*$", line):
            return None
    for source_schema, target_schema in replacements.items():
        line = line.replace(f"`{source_schema}`.", f"`{target_schema}`.")
        line = re.sub(rf"(?<=TRIGGER\s){re.escape(source_schema)}\.", f"{target_schema}.", line)
        line = re.sub(
            rf"(\b(?:BEFORE|AFTER)\s+(?:INSERT|UPDATE|DELETE)\s+ON\s+){re.escape(source_schema)}\.",
            rf"\1{target_schema}.",
            line,
        )
    # Restored views/triggers must not retain a production service-account
    # definer that lacks privileges on the disposable schema. This transforms
    # only the stream sent to the rehearsal target; source definitions and
    # grants remain untouched.
    line = re.sub(r"DEFINER=`[^`]+`@`[^`]+`", "DEFINER=`root`@`localhost`", line)
    return line


def _scan_transform(spec: BackupSpec, replacements: dict[str, str]) -> dict[str, int]:
    counts = {"removed_create_database": 0, "removed_use": 0, "qualified_rewrites": 0, "definer_rewrites": 0, "unrewritten_qualified_references": 0, "unrewritten_bare_trigger_targets": 0, "unrewritten_nonroot_definers": 0}
    with gzip.open(spec.dump_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            relevant = (
                "DEFINER=" in line
                or line.startswith("CREATE DATABASE")
                or line.startswith("USE ")
                or any(source in line for source in replacements)
            )
            transformed = _transform_line(line, replacements)
            if transformed is None:
                if line.startswith("CREATE DATABASE"):
                    counts["removed_create_database"] += 1
                else:
                    counts["removed_use"] += 1
                continue
            if not relevant:
                continue
            counts["qualified_rewrites"] += sum(line.count(f"`{source}`.") for source in replacements)
            counts["definer_rewrites"] += len(re.findall(r"DEFINER=`[^`]+`@`[^`]+`", line))
            counts["unrewritten_qualified_references"] += sum(transformed.count(f"`{source}`.") for source in replacements)
            counts["unrewritten_bare_trigger_targets"] += sum(
                len(re.findall(rf"\b(?:BEFORE|AFTER)\s+(?:INSERT|UPDATE|DELETE)\s+ON\s+{re.escape(source)}\.", transformed))
                for source in replacements
            )
            counts["unrewritten_nonroot_definers"] += len(re.findall(r"DEFINER=`(?!root`@`localhost)[^`]+`@`[^`]+`", transformed))
    if counts["unrewritten_qualified_references"] or counts["unrewritten_bare_trigger_targets"] or counts["unrewritten_nonroot_definers"]:
        raise RuntimeError(f"unsafe unrewritten qualified schema references in {spec.dump_path.name}")
    return counts


def _stream_restore(spec: BackupSpec, replacements: dict[str, str]) -> None:
    _assert_safe_target(spec.target_schema)
    _run_mysql(query=f"CREATE DATABASE `{spec.target_schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    # MariaDB can emit many restore warnings.  Capturing them in pipes can
    # deadlock a long import when the child fills stdout/stderr before this
    # process reaches ``communicate``. A temporary local log avoids that while
    # retaining a bounded diagnostic tail on failure.
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", prefix="obsidiandroid-phase2a-", suffix=".log", delete=False) as restore_log:
        restore_log_path = Path(restore_log.name)
        process = subprocess.Popen(
            _mysql_command(database=spec.target_schema), env=_mysql_env(), text=True,
            stdin=subprocess.PIPE, stdout=restore_log, stderr=restore_log,
        )
        assert process.stdin is not None
        try:
            with gzip.open(spec.dump_path, "rt", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    transformed = _transform_line(line, replacements)
                    if transformed is not None:
                        process.stdin.write(transformed)
            process.stdin.close()
            returncode = process.wait()
        except BaseException as exc:
            if process.stdin and not process.stdin.closed:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            restore_log.flush()
            restore_log.seek(0)
            tail = restore_log.read()[-4000:].strip()
            raise RuntimeError(
                f"restore stream failed for {spec.target_schema}; diagnostic_log={restore_log_path}; "
                f"server_output={tail}"
            ) from exc
        if returncode:
            restore_log.seek(0)
            tail = restore_log.read()[-4000:].strip()
            raise RuntimeError(f"restore failed for {spec.target_schema} ({returncode}); diagnostic_log={restore_log_path}: {tail}")
    restore_log_path.unlink(missing_ok=True)


def _scalar(query: str) -> int:
    output = _run_mysql(query=query).strip()
    return int(output or "0")


def _schema_structure(schema: str) -> dict[str, int]:
    return {
        "tables": _scalar(f"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='{schema}' AND TABLE_TYPE='BASE TABLE'"),
        "views": _scalar(f"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='{schema}' AND TABLE_TYPE='VIEW'"),
        "routines": _scalar(f"SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='{schema}'"),
        "triggers": _scalar(f"SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='{schema}'"),
        "events": _scalar(f"SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA='{schema}'"),
    }


def _validate_views(schema: str) -> dict[str, Any]:
    raw = _run_mysql(query=f"SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA='{schema}' ORDER BY TABLE_NAME")
    failures: list[str] = []
    names = [line.strip() for line in raw.splitlines() if line.strip()]
    for name in names:
        try:
            _run_mysql(query=f"SELECT 1 FROM `{schema}`.`{name}` LIMIT 0")
        except RuntimeError:
            failures.append(name)
    return {"views_checked": len(names), "view_failures": failures}


def _validate_schema(spec: BackupSpec) -> dict[str, Any]:
    source_structure = _schema_structure(spec.source_schema)
    target_structure = _schema_structure(spec.target_schema)
    failures: list[dict[str, Any]] = []
    if source_structure != target_structure:
        failures.append({"code": "structure_mismatch", "source": source_structure, "restored": target_structure})
    row_counts: dict[str, int] = {}
    for table in REPRESENTATIVE_TABLES[spec.source_schema]:
        source_count = _scalar(f"SELECT COUNT(*) FROM `{spec.source_schema}`.`{table}`")
        target_count = _scalar(f"SELECT COUNT(*) FROM `{spec.target_schema}`.`{table}`")
        if source_count != target_count:
            failures.append({"code": "representative_row_count_mismatch", "table": table, "source": source_count, "restored": target_count})
        row_counts[table] = source_count
    view_result = _validate_views(spec.target_schema)
    if view_result["view_failures"]:
        failures.append({"code": "view_validation_failed", "views": view_result["view_failures"]})
    invariants: dict[str, int] = {}
    if spec.source_schema == "erebus_threat_intel_prod":
        query = "SELECT COUNT(*) FROM `{}`.`android_malware_family_alias` a LEFT JOIN `{}`.`android_malware_family` f ON f.family_id=a.family_id WHERE a.family_id IS NOT NULL AND f.family_id IS NULL"
        invariants["alias_missing_family_source"] = _scalar(query.format(spec.source_schema, spec.source_schema))
        invariants["alias_missing_family_restore"] = _scalar(query.format(spec.target_schema, spec.target_schema))
    else:
        query = "SELECT COUNT(*) FROM `{}`.`android_permission_authority_fact`"
        invariants["permission_authority_fact_source"] = _scalar(query.format(spec.source_schema))
        invariants["permission_authority_fact_restore"] = _scalar(query.format(spec.target_schema))
    if len(set(invariants.values())) != 1:
        failures.append({"code": "invariant_mismatch", "values": invariants})
    return {"status": "passed" if not failures else "failed", "failures": failures, "source_structure": source_structure, "target_structure": target_structure, "representative_row_counts": row_counts, "views": view_result, "invariants": invariants}


def _event_scheduler_state() -> str:
    return _run_mysql(query="SELECT @@event_scheduler").strip().upper()


def _target_exists(target: str) -> bool:
    return bool(_scalar(f"SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{target}'"))


def _write_receipts(payload: dict[str, Any]) -> list[Path]:
    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    paths: list[Path] = []
    for source_schema, result in payload["restores"].items():
        path = RECEIPT_ROOT / f"{timestamp}_{source_schema}_recovery_receipt.json"
        receipt = {"phase": "2A", "status": result["validation"]["status"], "source_schema": source_schema, "target_schema": result["target_schema"], "backup": result["backup"], "transform": result["transform"], "validation": result["validation"], "event_scheduler": payload["event_scheduler"], "production_and_core_modified": False, "retention": "retained_pending_review"}
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        path.with_suffix(path.suffix + ".sha256").write_text(f"{_sha256(path)}  {path.name}\n", encoding="utf-8")
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Disposable Phase 2A backup restore rehearsal.")
    parser.add_argument("--apply", action="store_true", help="Create the two disposable restore schemas and stream the backup data into them.")
    parser.add_argument(
        "--source-schema", action="append", choices=tuple(TARGETS),
        help="Restore only one source schema. Repeat for an intentionally staged rehearsal; default restores both.",
    )
    parser.add_argument("--validate-existing", action="store_true", help="Validate an existing disposable target and issue a passed/failed receipt without restoring it.")
    args = parser.parse_args()
    selected = tuple(args.source_schema or TARGETS.keys())
    specs = [_load_backup(source, TARGETS[source]) for source in selected]
    # Keep both mappings during a staged import: Erebus views contain explicit
    # Permission Intel references even when the latter is restored separately.
    replacements = dict(TARGETS)
    event_scheduler = _event_scheduler_state()
    if event_scheduler != "OFF":
        raise RuntimeError(f"event scheduler must be OFF for rehearsal, got {event_scheduler}")
    for spec in specs:
        _assert_safe_target(spec.target_schema)
        if _target_exists(spec.target_schema) and not args.validate_existing:
            raise RuntimeError(f"disposable target already exists; inspect it instead of overwriting: {spec.target_schema}")
        if args.validate_existing and not _target_exists(spec.target_schema):
            raise RuntimeError(f"cannot validate missing disposable target: {spec.target_schema}")
    prepared = {
        spec.source_schema: {
            "target_schema": spec.target_schema,
            "backup": _verify_backup(spec),
            "transform": (
                {"status": "existing_target_validation_only; import transform not rerun"}
                if args.validate_existing
                else _scan_transform(spec, replacements)
            ),
        }
        for spec in specs
    }
    if not args.apply and not args.validate_existing:
        print(json.dumps({"phase": "2A", "dry_run": True, "event_scheduler": event_scheduler, "restores": prepared, "apply_required": True}, indent=2, sort_keys=True))
        return 0
    if not args.validate_existing:
        # Permission Intel first: Erebus views depend on permission-reference objects.
        order = sorted(specs, key=lambda item: 0 if item.source_schema == "android_permission_intel" else 1)
        for spec in order:
            _stream_restore(spec, replacements)
    for spec in specs:
        prepared[spec.source_schema]["validation"] = _validate_schema(spec)
    overall_status = "passed" if all(item["validation"]["status"] == "passed" for item in prepared.values()) else "failed"
    payload = {"phase": "2A", "status": overall_status, "performed_at_utc": _utc_now(), "event_scheduler": event_scheduler, "restores": prepared, "production_and_core_modified": False}
    receipts = _write_receipts(payload)
    print(json.dumps({**payload, "receipt_paths": [str(path) for path in receipts]}, indent=2, sort_keys=True))
    return 0 if overall_status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
