"""Manifest pipeline: atomic writer, deterministic hashing, run-manifest paths."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.pipeline.manifest import hashing
from obsidiandroid.pipeline.manifest import writer
from config import app_config
import obsidiandroid.governance.run_manifest as run_manifest

canonical_csv_bytes = hashing.canonical_csv_bytes
dataset_hash_from_sample_ids = hashing.dataset_hash_from_sample_ids
sha256_hex = hashing.sha256_hex
write_manifest_atomic = writer.write_manifest_atomic


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


def test_export_engine_ranking_tiers_writes_tier_column(tmp_path: Path) -> None:
    """Regression: tier mapping must call the defined rank helper (manifest finalization)."""
    from obsidiandroid.pipeline.manifest import stage_manifest_artifacts

    weights_df = pd.DataFrame(
        {
            "Vendor": ["alpha", "beta"],
            "Leakage Safe Score Raw": [0.9, 0.1],
            "Reliability": [0.5, 0.5],
            "Final ML Score": [0.0, 0.0],
            "Composite Score": [0.0, 0.0],
            "Enrichment Score": [0.0, 0.0],
            "parser_gate_status": ["ok", "ok"],
            "included_in_model": [1, 1],
        }
    )
    out_path, digest = stage_manifest_artifacts.export_engine_ranking_tiers(
        run_root=tmp_path,
        run_id="r_test",
        evidence_mode=False,
        weights_df=weights_df,
    )
    assert out_path is not None and out_path.exists()
    assert digest
    written = pd.read_csv(out_path)
    assert list(written["tier"]) == ["High", "Low"]


def test_write_experiment_contract_snapshot_cv_protocol_hardened(monkeypatch, tmp_path: Path) -> None:
    """Experiment contract must not crash on None CV settings and must floor CV folds."""
    from config import app_config
    from obsidiandroid.pipeline.manifest import stage_manifest_writers

    monkeypatch.setattr(app_config, "CV_FOLDS", None, raising=False)
    monkeypatch.setattr(app_config, "CV_REPEATS", None, raising=False)
    monkeypatch.setattr(app_config, "RANDOM_STATE", None, raising=False)

    diag = tmp_path / "diagnostics"
    diag.mkdir()
    out = stage_manifest_writers.write_experiment_contract_snapshot(
        run_id="r_cv_test",
        diagnostics_dir=diag,
        profile={"profile_id": "test_profile", "cohort_gates": {}},
        manifest_context={"paper_mode": {"resolved_value": False, "source": "test"}},
        manifest={"split": {"split_hash": "deadbeef"}},
    )
    assert out is not None and out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    cv = payload["split_contract"]["cv_protocol"]
    assert cv["stratified_kfold_splits"] == 5
    assert cv["repeats"] == 1
    assert cv["fixed_seed"] == 42

    monkeypatch.setattr(app_config, "CV_FOLDS", 1, raising=False)
    out2 = stage_manifest_writers.write_experiment_contract_snapshot(
        run_id="r_cv_test2",
        diagnostics_dir=diag,
        profile={"profile_id": "test_profile", "cohort_gates": {}},
        manifest_context={"paper_mode": {"resolved_value": False, "source": "test"}},
        manifest={"split": {"split_hash": "cafebabe"}},
    )
    assert out2 is not None
    payload2 = json.loads(out2.read_text(encoding="utf-8"))
    assert payload2["split_contract"]["cv_protocol"]["stratified_kfold_splits"] == 2
