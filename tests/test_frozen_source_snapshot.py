import json

import pandas as pd
import pytest

from obsidiandroid.governance.frozen_benchmark_sources import SealedSnapshotFrozenBenchmarkSourceProvider
from obsidiandroid.governance.frozen_source_snapshot import (
    _manifest_integrity,
    create_synthetic_sealed_snapshot,
    derive_normalized_vt_rows,
    govern_duplicate_authority_rows,
    validate_sealed_snapshot,
)


def _entry(root, name):
    manifest = json.loads((root / "source_snapshot_manifest.json").read_text())
    return next(item for item in manifest["extracts"] if item["name"] == name)


def _write_internal_consistent_manifest(path, manifest):
    """Simulate a structurally valid package in an invalid lifecycle state."""
    manifest["manifest_integrity_hash"] = _manifest_integrity(manifest)
    path.write_text(json.dumps(manifest, sort_keys=True))


def test_wide_vt_derivative_is_reproducible_and_row_bound(tmp_path):
    root = tmp_path / "sealed"
    snapshot = create_synthetic_sealed_snapshot(root)
    wide = pd.read_csv(root / _entry(root, "vt_wide_rows")["path"], compression="gzip")
    observed = pd.read_csv(root / _entry(root, "vt_long_normalized")["path"], compression="gzip")
    derived = derive_normalized_vt_rows(
        wide, snapshot_id=snapshot.manifest["snapshot_id"],
        engine_columns=["alpha_engine", "beta_engine"], engine_aliases={},
        snapshot_created_at_utc=snapshot.manifest["created_at_utc"],
    )
    pd.testing.assert_frame_equal(observed, derived)
    assert observed.groupby("sample_id")["source_wide_row_hash"].nunique().eq(1).all()
    assert observed.groupby("sample_id")["snapshot_row_id"].nunique().eq(1).all()


def test_snapshot_provider_is_repeatable_and_rejects_tampering(tmp_path):
    root = tmp_path / "sealed"
    create_synthetic_sealed_snapshot(root)
    provider = SealedSnapshotFrozenBenchmarkSourceProvider(root)
    pd.testing.assert_frame_equal(provider.cohort_rows(), provider.cohort_rows())
    path = root / _entry(root, "android_metadata")["path"]
    with path.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        SealedSnapshotFrozenBenchmarkSourceProvider(root)


def test_unsealed_missing_and_window_policy_fail_closed(tmp_path):
    root = tmp_path / "sealed"
    create_synthetic_sealed_snapshot(root)
    manifest_path = root / "source_snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["state"] = "VALIDATED"
    _write_internal_consistent_manifest(manifest_path, manifest)
    with pytest.raises(ValueError, match="SEALED"):
        validate_sealed_snapshot(root)
    manifest["state"] = "SEALED"
    manifest["classification"] = "canonical"
    manifest["cross_database_extraction_window_seconds"] = 301
    _write_internal_consistent_manifest(manifest_path, manifest)
    with pytest.raises(ValueError, match="window"):
        validate_sealed_snapshot(root)
    manifest["cross_database_extraction_window_seconds"] = 5
    _write_internal_consistent_manifest(manifest_path, manifest)
    (root / _entry(root, "engine_metadata")["path"]).unlink()
    with pytest.raises(ValueError, match="missing"):
        validate_sealed_snapshot(root)


def test_manifest_tampering_and_lifecycle_reordering_fail_closed(tmp_path):
    root = tmp_path / "sealed"
    create_synthetic_sealed_snapshot(root)
    manifest_path = root / "source_snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["extracts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_sealed_snapshot(root)
    create_synthetic_sealed_snapshot(tmp_path / "other")
    other_path = tmp_path / "other" / "source_snapshot_manifest.json"
    other = json.loads(other_path.read_text())
    other["lifecycle_history"].reverse()
    _write_internal_consistent_manifest(other_path, other)
    with pytest.raises(ValueError, match="lifecycle history"):
        validate_sealed_snapshot(tmp_path / "other")


def test_symlinked_evidence_is_rejected(tmp_path):
    root = tmp_path / "sealed"
    create_synthetic_sealed_snapshot(root)
    target = root / _entry(root, "engine_metadata")["path"]
    replacement = root / "replacement.csv.gz"
    target.rename(replacement)
    target.symlink_to(replacement.name)
    with pytest.raises(ValueError, match="non-symlink"):
        validate_sealed_snapshot(root)


def test_duplicate_authority_conflicts_are_rejected():
    rows = pd.DataFrame([
        {"sample_id": 1, "family_id": 10, "family_canonical": "alpha"},
        {"sample_id": 1, "family_id": 20, "family_canonical": "bravo"},
    ])
    with pytest.raises(ValueError, match="DUPLICATE_AUTHORITY_CONFLICT"):
        govern_duplicate_authority_rows(rows)
