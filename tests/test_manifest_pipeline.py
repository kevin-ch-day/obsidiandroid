"""Manifest pipeline: atomic writer, deterministic hashing, run-manifest paths."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.pipeline.manifest.hashing import (
    canonical_csv_bytes,
    dataset_hash_from_sample_ids,
    sha256_hex,
)
from analysis.pipeline.manifest.writer import write_manifest_atomic
from config import app_config
import obsidiandroid.governance.run_manifest as run_manifest


def test_write_manifest_atomic_creates_file(tmp_path: Path) -> None:
    """Atomic writer should create manifest file with expected payload."""
    target = tmp_path / "run_manifest.json"
    payload = {"run_id": "r1", "value": 1}
    out = write_manifest_atomic(target_path=target, payload=payload)
    assert out == target
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == payload


def test_write_manifest_atomic_replaces_existing_file(tmp_path: Path) -> None:
    """Atomic writer should replace existing target content."""
    target = tmp_path / "run_manifest.json"
    target.write_text('{"run_id":"old"}', encoding="utf-8")
    payload = {"run_id": "new", "value": 2}
    write_manifest_atomic(target_path=target, payload=payload)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["run_id"] == "new"
    assert data["value"] == 2


def test_dataset_hash_from_sample_ids_is_order_stable() -> None:
    """Dataset hash should be independent of input order."""
    left = dataset_hash_from_sample_ids([3, 1, 2])
    right = dataset_hash_from_sample_ids([2, 3, 1])
    assert left == right


def test_canonical_csv_bytes_is_stable_for_same_values() -> None:
    """Canonical CSV bytes should be deterministic."""
    frame = pd.DataFrame(
        [
            {"rank": 1, "engine_id": "a", "score": 0.5},
            {"rank": 2, "engine_id": "b", "score": 0.1},
        ]
    )
    one = canonical_csv_bytes(
        frame,
        columns=["rank", "engine_id", "score"],
        float_format="%.6f",
        lineterminator="\n",
    )
    two = canonical_csv_bytes(
        frame[["rank", "engine_id", "score"]],
        float_format="%.6f",
        lineterminator="\n",
    )
    assert one == two
    assert b"\r\n" not in one


def test_sha256_hex_matches_canonical_bytes() -> None:
    """Hash helper should produce stable digest from canonical bytes."""
    frame = pd.DataFrame([{"x": 1.23456789}, {"x": 2.0}])
    payload = canonical_csv_bytes(frame, float_format="%.6f", lineterminator="\n")
    digest = sha256_hex(payload)
    assert len(digest) == 64
    assert digest == sha256_hex(payload)


def test_write_run_manifest_uses_current_default_output_dir(monkeypatch, tmp_path: Path) -> None:
    """Manifest writes should follow runtime output-root overrides by default."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)

    path = run_manifest.write_run_manifest({"run_id": "r1"})

    expected = output_root / "diagnostics" / "run_manifest.latest.json"
    assert path == expected
    assert expected.exists()
    payload = json.loads(expected.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
