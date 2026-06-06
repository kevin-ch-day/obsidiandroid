from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import ml_seed_exports
from obsidiandroid.pipeline.permission_trends.constants import PERMISSION_ALIAS_MAP

pytestmark = pytest.mark.contract


def _write_aligned_features_fixture(
    diagnostics_dir: Path,
    run_id: str,
    *,
    rows: list[dict[str, object]] | None = None,
) -> None:
    default_rows = [
        {
            "sample_id": 1,
            "perm__android_permission_internet": 1,
            "perm__android_permission_read_sms": 0,
            "perm__dangerous_count": 1,
        },
        {
            "sample_id": 2,
            "perm__android_permission_internet": 0,
            "perm__android_permission_read_sms": 1,
            "perm__dangerous_count": 1,
        },
    ]
    frame = pd.DataFrame(rows or default_rows)
    frame.to_csv(
        diagnostics_dir / f"aligned_features_{run_id}.csv.gz",
        index=False,
        compression="gzip",
    )


def _write_canonical_handoff_fixtures(
    diagnostics_dir: Path,
    run_id: str,
    *,
    with_split: bool = False,
) -> None:
    """Minimum on-disk inputs so canonical profiles pass DL handoff hard-fail."""
    alias_path = diagnostics_dir / f"permission_alias_map_{run_id}.json"
    alias_path.write_text(
        json.dumps({"alias_map": {"android.permission.internet": "android.permission.INTERNET"}}),
        encoding="utf-8",
    )
    if with_split:
        (diagnostics_dir / f"split_freeze_headline_{run_id}.csv").write_text(
            "sample_id,split\n1,train\n2,test\n",
            encoding="utf-8",
        )


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
        "dataset_hash": "a" * 64,
        "split": {"split_hash": "abc123"},
        "trained_models": ["logistic_regression"],
    }
    (tmp_path / "v3_label_contract_run_seed.json").write_text("{}", encoding="utf-8")
    (tmp_path / "permission_pattern_contract_run_seed.json").write_text("{}", encoding="utf-8")
    _write_canonical_handoff_fixtures(tmp_path, "run_seed", with_split=True)
    _write_aligned_features_fixture(tmp_path, "run_seed")
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
    refs = ml_manifest["seed_artifact_refs"]
    assert refs["v3_label_contract"] == "v3_label_contract_run_seed.json"
    assert refs["permission_pattern_contract"] == "permission_pattern_contract_run_seed.json"
    assert refs["ml_sample_label_fact"] == "ml_sample_label_fact_run_seed.csv"
    assert refs["ml_permission_vocabulary"] == "ml_permission_vocabulary_run_seed.json"
    assert "ml_permission_pattern_fact" not in refs
    assert ml_manifest["optional_seed_artifact_refs"]["ml_train_validation_test_split"] == (
        "ml_train_validation_test_split_run_seed.csv"
    )
    assert ml_manifest["optional_seed_artifact_refs"]["ml_sample_permission_feature"] == (
        "ml_sample_permission_feature_run_seed.csv"
    )
    assert ml_manifest["sample_label_rows"] == 2
    permission_df = pd.read_csv(tmp_path / "ml_sample_permission_feature_run_seed.csv")
    assert list(permission_df.columns) == list(ml_seed_exports.ML_SAMPLE_PERMISSION_FEATURE_COLUMNS)
    assert set(permission_df["permission_present"].tolist()) == {1}
    assert len(permission_df) == 2
    assert "perm__dangerous_count" not in permission_df["permission_name"].astype(str).tolist()
    handoff = json.loads((tmp_path / "v3_dl_handoff_summary_run_seed.json").read_text(encoding="utf-8"))
    assert handoff["dl_seed_status"] == "ready"


def test_export_ml_seed_artifacts_rebuilds_label_fact_from_aligned_labels(tmp_path: Path) -> None:
    run_id = "run_aligned"
    (tmp_path / f"aligned_labels_{run_id}.csv").write_text(
        "sample_id,family_id,family_canonical,type_slug,sha256,sample_label_kind\n"
        "1,10,Alpha,banker,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,family_or_common_name\n",
        encoding="utf-8",
    )
    (tmp_path / f"v3_label_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"permission_pattern_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    _write_canonical_handoff_fixtures(tmp_path, run_id)

    paths = ml_seed_exports.export_ml_seed_artifacts(
        diagnostics_dir=tmp_path,
        run_id=run_id,
        profile={"profile_id": "android_malware_major_families", "training_label_field": "family_id"},
        samples_df=None,
        manifest={"cohort_size": 1, "dataset_hash": "b" * 64},
        manifest_context={},
    )

    assert any(p.endswith(f"ml_sample_label_fact_{run_id}.csv") for p in paths)
    label_df = pd.read_csv(tmp_path / f"ml_sample_label_fact_{run_id}.csv")
    assert len(label_df) == 1
    assert label_df["supervised_label_namespace"].iloc[0] == "malware_family"


def test_export_ml_seed_artifacts_rebuilds_from_cohort_membership_csv(tmp_path: Path) -> None:
    run_id = "run_cohort"
    (tmp_path / "cohort_membership.csv").write_text(
        "sample_id,family_id,family_canonical,type_slug\n2,11,Beta,rat\n",
        encoding="utf-8",
    )
    (tmp_path / f"v3_label_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"permission_pattern_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    _write_canonical_handoff_fixtures(tmp_path, run_id)

    paths = ml_seed_exports.export_ml_seed_artifacts(
        diagnostics_dir=tmp_path,
        run_id=run_id,
        profile={"profile_id": "android_malware_major_families"},
        samples_df=None,
        manifest={"cohort_size": 1, "dataset_hash": "c" * 64},
        manifest_context={},
    )

    label_df = pd.read_csv(tmp_path / f"ml_sample_label_fact_{run_id}.csv")
    assert len(label_df) == 1
    assert any(p.endswith(f"ml_sample_label_fact_{run_id}.csv") for p in paths)


def test_export_ml_seed_artifacts_rejects_empty_samples(tmp_path: Path) -> None:
    with pytest.raises(ml_seed_exports.MlSeedExportError):
        ml_seed_exports.export_ml_seed_artifacts(
            diagnostics_dir=tmp_path,
            run_id="run_empty",
            profile={"profile_id": "android_malware_major_families"},
            samples_df=pd.DataFrame(),
            manifest={},
            manifest_context={},
        )


def test_ensure_ml_split_export_writes_csv_from_split_freeze_headline(tmp_path: Path) -> None:
    run_id = "run_split_ensure"
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (diagnostics_dir / f"split_freeze_headline_{run_id}.csv").write_text(
        "sample_id,split\n1,train\n2,test\n",
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps({"optional_seed_artifact_refs": {}}),
        encoding="utf-8",
    )

    split_path = ml_seed_exports.ensure_ml_split_export(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        manifest={"split": {"split_hash": "abc123"}},
    )

    assert split_path is not None
    assert split_path.name == f"ml_train_validation_test_split_{run_id}.csv"
    manifest = json.loads((diagnostics_dir / f"ml_run_manifest_{run_id}.json").read_text(encoding="utf-8"))
    assert manifest["optional_seed_artifact_refs"]["ml_train_validation_test_split"] == split_path.name


def test_sync_ml_run_manifest_seed_counters_copies_dataset_hash(tmp_path: Path) -> None:
    run_id = "run_sync_hash"
    run_root = tmp_path / "output" / "runs" / "slot"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"dataset_hash": "abc123deadbeef"}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps({"vocabulary_entry_count": 1}),
        encoding="utf-8",
    )

    synced = ml_seed_exports.sync_ml_run_manifest_seed_counters(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        vocabulary_entry_count=2,
    )

    assert synced is not None
    payload = json.loads(synced.read_text(encoding="utf-8"))
    assert payload["dataset_hash"] == "abc123deadbeef"
    assert payload["vocabulary_entry_count"] == 2


def test_sync_ml_run_manifest_seed_counters_updates_vocabulary_count(tmp_path: Path) -> None:
    run_id = "run_sync_manifest"
    run_root = tmp_path / "output" / "runs" / "slot"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps({"vocabulary_entry_count": 1, "sample_label_rows": 1}),
        encoding="utf-8",
    )
    tables_dir = run_root / "bundles" / "permission_trends" / "tables"
    tables_dir.mkdir(parents=True)
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text(
        "type_slug,permission,n_samples,permission_positive_count,prevalence_pct\n"
        "banker,android.permission.internet,10,8,80.0\n"
        "banker,android.permission.camera,10,1,10.0\n",
        encoding="utf-8",
    )

    synced = ml_seed_exports.sync_ml_run_manifest_seed_counters(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    )

    assert synced is not None
    payload = json.loads(synced.read_text(encoding="utf-8"))
    assert payload["vocabulary_entry_count"] == 2


def test_refresh_persisted_permission_vocabulary_rewrites_json(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "slot"
    diagnostics_dir = run_root / "diagnostics"
    tables_dir = run_root / "bundles" / "permission_trends" / "tables"
    tables_dir.mkdir(parents=True)
    run_id = "run_refresh"
    stale_path = diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json"
    stale_path.parent.mkdir(parents=True)
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps({"vocabulary_entry_count": 0}),
        encoding="utf-8",
    )
    stale_path.write_text(
        json.dumps({"vocabulary_version": "ml_permission_vocabulary_v1", "entry_count": 0, "entries": []}),
        encoding="utf-8",
    )
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text(
        "type_slug,permission,n_samples,permission_positive_count,prevalence_pct\n"
        "banker,android.permission.internet,10,8,80.0\n",
        encoding="utf-8",
    )

    refreshed = ml_seed_exports.refresh_persisted_permission_vocabulary(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    )
    payload = json.loads(refreshed.read_text(encoding="utf-8"))
    manifest = json.loads((diagnostics_dir / f"ml_run_manifest_{run_id}.json").read_text(encoding="utf-8"))

    assert payload["vocabulary_version"] == "ml_permission_vocabulary_v2"
    assert payload["permission_entry_count"] == 1
    assert payload["entry_count"] == 1
    assert manifest["vocabulary_entry_count"] == 1


def test_permission_vocabulary_reads_bundle_contracts_alias_map(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "majorfam_benchmark"
    diagnostics_dir = run_root / "diagnostics"
    contracts_dir = run_root / "bundles" / "permission_trends" / "contracts"
    contracts_dir.mkdir(parents=True)
    run_id = "run_bundle_vocab"
    (contracts_dir / f"permission_alias_map_{run_id}.json").write_text(
        json.dumps(
            {
                "permission_alias_map_version": "perm_alias_v1",
                "alias_map": dict(PERMISSION_ALIAS_MAP),
            }
        ),
        encoding="utf-8",
    )

    vocab = ml_seed_exports._build_permission_vocabulary(diagnostics_dir, run_id)

    assert vocab["alias_entry_count"] == len(PERMISSION_ALIAS_MAP)
    assert vocab["entry_count"] == len(PERMISSION_ALIAS_MAP)
    assert vocab["entries"][0]["alias_from"] in PERMISSION_ALIAS_MAP
    assert vocab["entries"][0]["entry_kind"] == "alias"


def test_build_sample_permission_feature_is_present_only_sparse(tmp_path: Path) -> None:
    run_id = "run_perm_sparse"
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    _write_aligned_features_fixture(diagnostics_dir, run_id)
    (diagnostics_dir.parent / "bundles" / "permission_trends" / "tables").mkdir(parents=True, exist_ok=True)
    tables_dir = diagnostics_dir.parent / "bundles" / "permission_trends" / "tables"
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text(
        "type_slug,permission,n_samples,permission_positive_count,prevalence_pct\n"
        "banker,android.permission.internet,10,8,80.0\n"
        "banker,android.permission.read_sms,10,3,30.0\n",
        encoding="utf-8",
    )
    label_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
        }
    )

    permission_df = ml_seed_exports._build_sample_permission_feature(
        diagnostics_dir,
        run_id,
        profile={"profile_id": "android_malware_major_families"},
        label_df=label_df,
    )

    assert list(permission_df.columns) == list(ml_seed_exports.ML_SAMPLE_PERMISSION_FEATURE_COLUMNS)
    assert len(permission_df) == 2
    assert set(permission_df["permission_present"].tolist()) == {1}
    assert set(permission_df["permission_name"].tolist()) == {
        "android.permission.internet",
        "android.permission.read_sms",
    }
    assert permission_df.loc[permission_df["sample_id"] == 1, "sha256"].iloc[0] == "a" * 64


def test_build_sample_permission_feature_returns_empty_without_aligned_features(tmp_path: Path) -> None:
    permission_df = ml_seed_exports._build_sample_permission_feature(
        tmp_path,
        "run_missing",
        profile={"profile_id": "android_malware_major_families"},
        label_df=pd.DataFrame({"sample_id": [1], "sha256": ["c" * 64]}),
    )

    assert permission_df.empty


def test_permission_vocabulary_reads_bundle_tables_enrichment_for_pattern_fact(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "typelevel_benchmark"
    diagnostics_dir = run_root / "diagnostics"
    tables_dir = run_root / "bundles" / "permission_trends" / "tables"
    tables_dir.mkdir(parents=True)
    run_id = "run_bundle_tables"
    (tables_dir / f"permission_type_enrichment_{run_id}.csv").write_text(
        "permission,pattern_score,pattern_level\nandroid.permission.internet,7,7\n",
        encoding="utf-8",
    )

    pattern_df = ml_seed_exports._build_permission_pattern_fact(diagnostics_dir, run_id)

    assert not pattern_df.empty
    assert pattern_df["comparison_scope"].iloc[0] == "type_vs_global"
