"""Tests for strict paper-evidence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.pipeline import stage_manifest
from obsidiandroid.pipeline.manifest.paper_evidence import (
    build_feature_set_glossary_payload,
    build_promoted_paper_model_binding,
    validate_paper_contract_bundle,
    validate_perturbation_summary_rows,
)


def test_validate_paper_contract_bundle_detects_count_mismatch(tmp_path: Path) -> None:
    """Mismatched paper constants should fail validation."""
    paper_constants_path = tmp_path / "paper_constants.json"
    manuscript_constants_path = tmp_path / "manuscript_constants.json"
    paper_constants_path.write_text(
        json.dumps(
            {
                "sample_count": 1226,
                "family_count": 39,
                "malware_type_count": 6,
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    manuscript_constants_path.write_text(
        json.dumps(
            {
                "sample_count": 1187,
                "family_count": 39,
                "type_count": 6,
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
                "label_vocabulary": {
                    "training_label_field": "family_id",
                    "display_label_field": "family_canonical",
                },
            }
        ),
        encoding="utf-8",
    )
    payload = validate_paper_contract_bundle(
        profile={
            "profile_id": "malicious_temporal_stability_locked",
            "paper_lock": {
                "expected_sample_count": 1226,
                "expected_family_count": 39,
                "expected_type_count": 6,
                "time_window_start_utc": "2020-01-01T00:00:00Z",
                "time_window_end_utc": "2026-01-01T00:00:00Z",
            },
        },
        manifest={
            "paper_cohort_summary": {
                "sample_count": 1226,
                "family_count": 39,
                "type_count": 6,
            }
        },
        paper_constants_path=paper_constants_path,
        manuscript_constants_path=manuscript_constants_path,
    )
    assert payload["passed"] is False
    failed_fields = {row["field"] for row in payload["checks"] if not row["passed"]}
    assert "sample_count" in failed_fields


def test_validate_perturbation_summary_rows_requires_split_and_cohort_hash() -> None:
    """Perturbation rows must carry split_hash and cohort_hash."""
    with pytest.raises(ValueError, match="split_hash/cohort_hash"):
        validate_perturbation_summary_rows(
            [
                {
                    "run_id": "r1",
                    "profile_id": "paper2_primary",
                    "split_hash": "",
                    "cohort_hash": "cohort123",
                }
            ]
        )


def test_build_promoted_paper_model_binding_requires_matching_prediction_split_hash(tmp_path: Path) -> None:
    """Promoted prediction CSV split hash must match manifest split hash."""
    run_id = "r1"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "confusion_matrix_primary.png").write_bytes(b"png")
    pd.DataFrame(
        [
            {"sample_id": 1, "split_hash": "bad", "predicted_label_name": "FamA", "true_label_name": "FamA"},
        ]
    ).to_csv(diagnostics_dir / f"headline_test_predictions_{run_id}.csv", index=False)
    (diagnostics_dir / f"headline_test_errors_{run_id}.csv").write_text("", encoding="utf-8")
    (diagnostics_dir / f"evaluation_contract_{run_id}.json").write_text(
        json.dumps({"feature_contract": {"headline_feature_column_hash": "feat123"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="prediction split_hash mismatch"):
        build_promoted_paper_model_binding(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            manifest={
                "run_id": run_id,
                "split": {"split_hash": "good"},
                "model_summary": {"top_model": "xgboost"},
                "cohort_contract": {"sample_id_lock": {"cohort_hash": "cohort123", "taxonomy_hash": "tax123"}},
            },
            evidence_mode=False,
        )


def test_build_promoted_paper_model_binding_records_manifest_split_hash(tmp_path: Path) -> None:
    """Promoted binding should preserve manifest split hash for confusion/prediction evidence."""
    run_id = "r2"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "confusion_matrix_primary.png").write_bytes(b"png")
    pd.DataFrame(
        [
            {"sample_id": 1, "split_hash": "aa" * 32, "predicted_label_name": "FamA", "true_label_name": "FamA"},
        ]
    ).to_csv(diagnostics_dir / f"headline_test_predictions_{run_id}.csv", index=False)
    (diagnostics_dir / f"headline_test_errors_{run_id}.csv").write_text("", encoding="utf-8")
    (diagnostics_dir / f"evaluation_contract_{run_id}.json").write_text(
        json.dumps({"feature_contract": {"headline_feature_column_hash": "feat123"}}),
        encoding="utf-8",
    )
    payload = build_promoted_paper_model_binding(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        manifest={
            "run_id": run_id,
            "split": {"split_hash": "aa" * 32, "split_audit_path": "split.csv"},
            "model_summary": {"top_model": "xgboost"},
            "model_config_hash": "model123",
            "cohort_contract": {"sample_id_lock": {"cohort_hash": "cohort123", "taxonomy_hash": "tax123"}},
        },
        evidence_mode=False,
    )
    assert payload["split_hash"] == "aa" * 32
    assert payload["confusion_matrix_split_hash"] == "aa" * 32
    assert payload["heldout_predictions_split_hash"] == "aa" * 32
    assert payload["label_target"] == "family_id"
    assert payload["display_label_field"] == "family_canonical"


def test_feature_set_glossary_uses_paper_label_vocabulary() -> None:
    """Paper-facing glossary should keep family_id/family_canonical vocabulary."""
    payload = build_feature_set_glossary_payload()
    assert payload["label_vocabulary"]["training_label_field"] == "family_id"
    assert payload["label_vocabulary"]["display_label_field"] == "family_canonical"
    names = {row["paper_feature_set"] for row in payload["feature_sets"]}
    assert names == {"permissions_only", "vendor_only", "vendor_permissions_fused"}


def test_write_evaluation_contract_json_preserves_promoted_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Evaluation contract should surface the promoted paper-model binding."""
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "feat123", raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_HEADLINE_FEATURE_CONTRACT_PATH", "feature_contract.json", raising=False)
    out_path = stage_manifest._write_evaluation_contract_json(  # pylint: disable=protected-access
        diagnostics_dir=diagnostics_dir,
        run_id="r3",
        manifest={
            "split": {"split_hash": "aa" * 32},
            "promoted_paper_model": {
                "model": "xgboost",
                "split_hash": "aa" * 32,
                "confusion_matrix_path": "/tmp/conf.png",
                "heldout_predictions_csv": "/tmp/preds.csv",
            },
        },
        manifest_context={"label_authority": {"training_label_field": "family_id"}},
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["promoted_paper_model"]["model"] == "xgboost"
    assert payload["promoted_paper_model"]["split_hash"] == "aa" * 32
