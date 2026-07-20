"""Offline package-writing checks for the future Phase 2C reader command."""

from __future__ import annotations

import gzip
from hashlib import sha256
from pathlib import Path

from obsidiandroid.core_migration.mapping import CoreImportError, SOURCE_SURFACES
from obsidiandroid.core_migration.source_extracts import load_verified_source_extract_package, validate_source_extract_manifest
from scripts.core_migration.create_phase2c_source_extract import _write_package


def _source_rows() -> dict[str, list[dict]]:
    return {
        "analysis_run": [{"run_id": "20260718T032717Z__a8cf01", "profile_id": "android_malware_all_current"}],
        "analysis_snapshot": [{"run_id": "20260718T032717Z__a8cf01"}],
        "analysis_snapshot_sample": [{"run_id": "20260718T032717Z__a8cf01", "sha256": "a" * 64, "sample_id": 1}],
        "analysis_artifact": [{"run_id": "20260718T032717Z__a8cf01", "artifact_key": "fixture", "artifact_path": "/fixture/artifact.csv"}],
        "snapshot_label_conflict": [],
    }


def test_phase2c_source_extract_package_is_private_complete_and_content_addressed(tmp_path: Path) -> None:
    output = tmp_path / "fixture-extract"
    manifest = _write_package(
        output_dir=output,
        run_id="20260718T032717Z__a8cf01",
        observed_at_utc="2026-07-19T12:00:00Z",
        source_rows=_source_rows(),
    )
    assert validate_source_extract_manifest(manifest) == manifest["extract_manifest_sha256"]
    assert {entry["source_table"] for entry in manifest["extracts"]} == set(SOURCE_SURFACES)
    assert output.stat().st_mode & 0o777 == 0o700
    conflict = next(entry for entry in manifest["extracts"] if entry["source_table"] == "snapshot_label_conflict")
    assert conflict["row_count"] == 0
    for entry in manifest["extracts"]:
        path = output / entry["relative_path"]
        assert path.stat().st_mode & 0o777 == 0o600
        assert sha256(path.read_bytes()).hexdigest() == entry["compressed_file_sha256"]
        with gzip.open(path, "rb") as handle:
            assert sha256(handle.read()).hexdigest() == entry["content_sha256"]
    assert (output / "SHA256SUMS").is_file()
    loaded_manifest, rows = load_verified_source_extract_package(output)
    assert loaded_manifest["extract_manifest_sha256"] == manifest["extract_manifest_sha256"]
    assert rows["analysis_snapshot_sample"][0]["sha256"] == "a" * 64


def test_phase2c_source_extract_refuses_to_overwrite_an_existing_package(tmp_path: Path) -> None:
    output = tmp_path / "fixture-extract"
    _write_package(
        output_dir=output,
        run_id="20260718T032717Z__a8cf01",
        observed_at_utc="2026-07-19T12:00:00Z",
        source_rows=_source_rows(),
    )
    try:
        _write_package(
            output_dir=output,
            run_id="20260718T032717Z__a8cf01",
            observed_at_utc="2026-07-19T12:00:00Z",
            source_rows=_source_rows(),
        )
    except RuntimeError as exc:
        assert "overwrite" in str(exc)
    else:
        raise AssertionError("existing package was unexpectedly overwritten")


def test_phase2c_source_extract_reader_rejects_a_tampered_payload(tmp_path: Path) -> None:
    output = tmp_path / "fixture-extract"
    manifest = _write_package(
        output_dir=output,
        run_id="20260718T032717Z__a8cf01",
        observed_at_utc="2026-07-19T12:00:00Z",
        source_rows=_source_rows(),
    )
    target = output / next(entry["relative_path"] for entry in manifest["extracts"] if entry["source_table"] == "analysis_run")
    target.write_bytes(target.read_bytes() + b"tampered")
    try:
        load_verified_source_extract_package(output)
    except CoreImportError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered source payload was unexpectedly accepted")
