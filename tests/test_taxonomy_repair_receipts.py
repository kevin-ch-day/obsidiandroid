"""Tests for version-controlled taxonomy-repair receipts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from obsidiandroid.governance.taxonomy_repair_receipts import (
    receipt_set_hash,
    validate_receipt_package,
    validate_receipt_root,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_ROOT = REPOSITORY_ROOT / "governance" / "taxonomy_repairs"


def test_committed_taxonomy_repair_receipts_validate() -> None:
    """Every committed repair package is complete, hashed, and reviewable."""
    results = validate_receipt_root(RECEIPT_ROOT)
    assert results, "expected at least one committed taxonomy-repair receipt"
    assert all(result.valid for result in results), results


def test_receipt_validator_rejects_prohibited_sensitive_json_key(tmp_path: Path) -> None:
    """Receipt metadata must not place raw sample identifiers in Git."""
    source = RECEIPT_ROOT / "2026-07-16_spymax-stale-alias"
    package = tmp_path / source.name
    shutil.copytree(source, package)
    receipt_path = package / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["sample_ids"] = [123]
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = validate_receipt_package(package)

    assert not result.valid
    assert any("prohibited sensitive receipt key" in error for error in result.errors)


def test_receipt_root_rejects_partial_package_directory(tmp_path: Path) -> None:
    """A repair directory without a receipt must not be silently ignored."""
    (tmp_path / "2026-07-17_partial-repair").mkdir()

    results = validate_receipt_root(tmp_path)

    assert len(results) == 1
    assert not results[0].valid
    assert any("missing required files" in error for error in results[0].errors)


def test_receipt_root_rejects_duplicate_repair_ids(tmp_path: Path) -> None:
    """Two complete packages cannot claim the same repair identifier."""
    source = RECEIPT_ROOT / "2026-07-16_spymax-stale-alias"
    shutil.copytree(source, tmp_path / "first")
    shutil.copytree(source, tmp_path / "second")

    results = validate_receipt_root(tmp_path)

    assert len(results) == 2
    assert all(not result.valid for result in results)
    assert all(any("duplicate repair_id" in error for error in result.errors) for result in results)


def test_receipt_set_hash_is_stable_for_valid_root() -> None:
    """The complete receipt tree has a deterministic governance digest."""
    first = receipt_set_hash(RECEIPT_ROOT)
    second = receipt_set_hash(RECEIPT_ROOT)

    assert len(first) == 64
    assert first == second


def test_receipt_set_hash_rejects_invalid_receipt_root(tmp_path: Path) -> None:
    """An invalid receipt must block a misleading empty governance digest."""
    (tmp_path / "2026-07-17_partial-repair").mkdir()

    with pytest.raises(ValueError, match="Cannot hash invalid taxonomy-repair receipt"):
        receipt_set_hash(tmp_path)
