"""Validate version-controlled taxonomy-repair receipt packages.

Receipt packages document approved, narrow database repairs without placing
credentials, raw sample identifiers, package names, or APK hashes in Git.
They are evidence and review artifacts; this module never opens a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA_VERSION = "taxonomy_repair_receipt_v1"
REQUIRED_FILES = frozenset(
    {
        "receipt.json",
        "evidence.md",
        "before.sql",
        "apply.sql",
        "validate.sql",
        "rollback.sql",
        "SHA256SUMS",
    }
)
REQUIRED_FIELDS = frozenset(
    {
        "repair_id",
        "schema_version",
        "repair_type",
        "database_name",
        "operator",
        "applied_at_utc",
        "receipt_created_at_utc",
        "source_commit_at_application",
        "source_commit_at_receipt_creation",
        "affected_family_ids",
        "affected_alias_ids",
        "affected_mapping_table_surfaces",
        "affected_sample_count",
        "before_state_capture_mode",
        "reason",
        "evidence_sources",
        "applied_sql_hash",
        "validation_sql_hash",
        "rollback_sql_hash",
        "post_change_validation",
        "integrity_status",
        "limitations",
    }
)
ALLOWED_BEFORE_STATE_CAPTURE_MODES = frozenset(
    {
        "CONTEMPORANEOUS",
        "RECONSTRUCTED_FROM_QUERY_OUTPUT",
        "RECONSTRUCTED_FROM_BACKUP",
        "PARTIALLY_RECONSTRUCTED",
    }
)
SQL_HASH_FIELDS = {
    "apply.sql": "applied_sql_hash",
    "validate.sql": "validation_sql_hash",
    "rollback.sql": "rollback_sql_hash",
}
PROHIBITED_RECEIPT_KEYS = frozenset(
    {
        "sample_id",
        "sample_ids",
        "package_name",
        "package_names",
        "apk_hash",
        "apk_hashes",
        "apk_sha256",
        "apk_sha256s",
        "raw_sample_id",
        "raw_sample_ids",
    }
)
EVIDENCE_LOCATOR_RE = re.compile(r"(?:https?|database)://[^\s)]+")


@dataclass(frozen=True)
class ReceiptValidationResult:
    """Validation outcome for one taxonomy-repair package."""

    package: Path
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        """Return whether no validation errors were found."""
        return not self.errors


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of *path* without loading it all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_prohibited_keys(value: Any, location: str = "") -> list[str]:
    if isinstance(value, dict):
        errors: list[str] = []
        for key, nested_value in value.items():
            nested_location = f"{location}.{key}" if location else key
            if key.lower() in PROHIBITED_RECEIPT_KEYS:
                errors.append(f"prohibited sensitive receipt key: {nested_location}")
            errors.extend(_find_prohibited_keys(nested_value, nested_location))
        return errors
    if isinstance(value, list):
        return [
            error
            for index, nested_value in enumerate(value)
            for error in _find_prohibited_keys(nested_value, f"{location}[{index}]")
        ]
    return []


def _read_checksums(path: Path) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", raw_line)
        if not match:
            errors.append(f"SHA256SUMS line {line_number} is not canonical")
            continue
        digest, filename = match.groups()
        if filename in entries:
            errors.append(f"SHA256SUMS duplicates {filename}")
        entries[filename] = digest
    return entries, errors


def validate_receipt_package(package: Path) -> ReceiptValidationResult:
    """Validate a single receipt package without executing any SQL."""
    errors: list[str] = []
    present_files = {path.name for path in package.iterdir()} if package.is_dir() else set()
    missing_files = sorted(REQUIRED_FILES - present_files)
    if missing_files:
        errors.append(f"missing required files: {', '.join(missing_files)}")
        return ReceiptValidationResult(package=package, errors=tuple(errors))

    try:
        receipt = json.loads((package / "receipt.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ReceiptValidationResult(
            package=package,
            errors=(f"receipt.json is not valid JSON: {exc.msg}",),
        )

    if not isinstance(receipt, dict):
        errors.append("receipt.json must contain an object")
    else:
        missing_fields = sorted(REQUIRED_FIELDS - set(receipt))
        if missing_fields:
            errors.append(f"receipt.json missing fields: {', '.join(missing_fields)}")
        if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            errors.append("receipt.json has an unsupported schema_version")
        if receipt.get("before_state_capture_mode") not in ALLOWED_BEFORE_STATE_CAPTURE_MODES:
            errors.append("receipt.json has an invalid before_state_capture_mode")
        if not receipt.get("evidence_sources"):
            errors.append("receipt.json must list at least one evidence source")
        if not EVIDENCE_LOCATOR_RE.search(
            (package / "evidence.md").read_text(encoding="utf-8")
        ):
            errors.append("evidence.md must contain an evidence URL or database locator")
        errors.extend(_find_prohibited_keys(receipt))
        for filename, field in SQL_HASH_FIELDS.items():
            expected_hash = receipt.get(field)
            actual_hash = sha256_file(package / filename)
            if expected_hash != actual_hash:
                errors.append(f"{field} does not match {filename}")

    checksums, checksum_errors = _read_checksums(package / "SHA256SUMS")
    errors.extend(checksum_errors)
    expected_checksum_files = REQUIRED_FILES - {"SHA256SUMS"}
    if set(checksums) != expected_checksum_files:
        errors.append("SHA256SUMS must cover every receipt file except itself")
    for filename, expected_hash in checksums.items():
        file_path = package / filename
        if file_path.exists() and sha256_file(file_path) != expected_hash:
            errors.append(f"SHA256SUMS hash mismatch for {filename}")

    return ReceiptValidationResult(package=package, errors=tuple(errors))


def validate_receipt_root(root: Path) -> tuple[ReceiptValidationResult, ...]:
    """Validate each immediate child package containing ``receipt.json``."""
    packages = sorted(path for path in root.iterdir() if (path / "receipt.json").is_file())
    return tuple(validate_receipt_package(package) for package in packages)


def main() -> int:
    """Run receipt validation from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="directory containing receipt packages")
    args = parser.parse_args()
    results = validate_receipt_root(args.root)
    if not results:
        print(f"[FAIL] No receipt packages found under {args.root}")
        return 1
    for result in results:
        if result.valid:
            print(f"[PASS] {result.package}")
        else:
            print(f"[FAIL] {result.package}")
            for error in result.errors:
                print(f"  - {error}")
    return 0 if all(result.valid for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
