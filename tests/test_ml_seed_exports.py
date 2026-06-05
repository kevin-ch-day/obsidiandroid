from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import ml_seed_exports

pytestmark = pytest.mark.contract


def test_export_ml_seed_artifacts_writes_minimum_tables(tmp_path: Path) -> None:
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_id": [10, 11],
            "family_canonical": ["Alpha", "Beta"],
            "type_slug": ["banker", "rat"],
            "sha256": ["a" * 64, "b" * 64],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
        }
    )
    manifest = {
        "cohort_size": 2,
        "train_sample_count": 1,
        "test_sample_count": 1,
        "split": {"split_hash": "abc123"},
        "trained_models": ["logistic_regression"],
    }
    paths = ml_seed_exports.export_ml_seed_artifacts(
        diagnostics_dir=tmp_path,
        run_id="run_seed",
        profile={"profile_id": "android_malware_type_taxonomy", "training_label_field": "type_slug"},
        samples_df=samples_df,
        manifest=manifest,
        manifest_context={"claim_surface": "authoritative_type_benchmark"},
    )
    assert any(p.endswith("ml_sample_label_fact_run_seed.csv") for p in paths)
    assert any(p.endswith("ml_permission_vocabulary_run_seed.json") for p in paths)
    assert any(p.endswith("ml_run_manifest_run_seed.json") for p in paths)

    label_df = pd.read_csv(tmp_path / "ml_sample_label_fact_run_seed.csv")
    assert label_df["supervised_label_namespace"].iloc[0] == "malware_type_slug"
    ml_manifest = json.loads((tmp_path / "ml_run_manifest_run_seed.json").read_text(encoding="utf-8"))
    assert ml_manifest["downstream_phase"] == "neptune_iapetus_deep_learning_prep"
    assert "v3_label_contract_run_seed.json" in ml_manifest["seed_artifact_refs"]["v3_label_contract"]
