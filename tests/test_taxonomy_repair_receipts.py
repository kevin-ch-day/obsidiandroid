"""Tests for version-controlled taxonomy-repair receipts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from obsidiandroid.governance.taxonomy_repair_receipts import (
    validate_receipt_package,
    validate_receipt_root,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_ROOT = REPOSITORY_ROOT / "governance" / "taxonomy_repairs"


def test_committed_taxonomy_repair_receipts_validate() -> None:
    """Every committed repair package is complete, hashed, and reviewable."""
    results = validate_receipt_root(RECEIPT_ROOT)
    assert len(results) == 3
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
