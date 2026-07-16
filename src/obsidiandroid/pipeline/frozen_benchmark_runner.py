"""Dedicated, non-legacy runner for ``android_family_av_abc_v1``.

It accepts only an explicit frozen source provider.  It never imports or calls
the legacy pipeline, parser, wide AV builder, or split selector.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.features.av_detection_contract import fit_av_detection_contract, transform_av_detection_features
from obsidiandroid.features.frozen_abc_features import build_abc_feature_contracts
from obsidiandroid.features.permission_contract import fit_permission_vocabulary, transform_permission_features
from obsidiandroid.governance.frozen_benchmark_config import load_frozen_cohort_profile, load_frozen_experiment
from obsidiandroid.governance.frozen_benchmark_lifecycle import FrozenBenchmarkLifecycle
from obsidiandroid.governance.frozen_benchmark_lock import create_frozen_group_split, freeze_cohort
from obsidiandroid.governance.frozen_benchmark_manifest import fit_sdk_imputation_contract, persist_source_extract, validate_estimator_protocol
from obsidiandroid.governance.frozen_benchmark_sources import FrozenBenchmarkSourceProvider


@dataclass
class FrozenBenchmarkContext:
    profile: dict[str, Any]
    experiment: dict[str, Any]
    lifecycle: FrozenBenchmarkLifecycle
    cohort: pd.DataFrame
    split: pd.DataFrame
    features: dict[str, pd.DataFrame]
    label_order: list[int]
    sdk_contract_hash: str
    model_protocol: dict[str, Any]


def _write(root: Path, name: str, payload: object) -> Path:
    path = root / name
    if isinstance(payload, pd.DataFrame):
        payload.to_csv(path, index=False)
    else:
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def _source_index(provider: FrozenBenchmarkSourceProvider, root: Path) -> Path:
    entries = [
        persist_source_extract("cohort_labels", provider.cohort_rows(), root),
        persist_source_extract("permissions", provider.permission_rows(), root),
        persist_source_extract("vt_engine_rows", provider.vt_rows(), root),
        persist_source_extract("engine_metadata", provider.engine_metadata(), root),
        persist_source_extract("taxonomy_aliases", provider.taxonomy_aliases(), root),
    ]
    return _write(root, "source_snapshot_index.json", entries)


def run_frozen_android_family_av_benchmark(provider: FrozenBenchmarkSourceProvider, *, run_root: Path, experiment_id: str = "android_family_av_abc_v1") -> FrozenBenchmarkContext:
    """Lock all pre-holdout inputs for the frozen experiment and stop."""
    if experiment_id != "android_family_av_abc_v1":
        raise ValueError("Frozen runner only supports android_family_av_abc_v1.")
    profile, experiment = load_frozen_cohort_profile(), load_frozen_experiment(experiment_id)
    lifecycle = FrozenBenchmarkLifecycle(run_root, experiment_id)
    source_path = _source_index(provider, run_root)
    lifecycle.record_artifact("sources", source_path)
    locked = freeze_cohort(provider.cohort_rows(), min_total_support=profile["cohort_policy"]["min_total_support"], max_component_share=profile["cohort_policy"]["max_component_share"])
    cohort = locked.frame
    cohort_path = _write(run_root, "cohort_lock.csv", cohort)
    lifecycle.record_artifact("cohort", cohort_path)
    lifecycle.transition("COHORT_LOCKED", required_artifacts=("cohort", "sources"), metadata=locked.payload)
    split = create_frozen_group_split(locked)
    split_path = _write(run_root, "split_ledger.csv", split)
    lifecycle.record_artifact("split", split_path)
    lifecycle.transition("SPLIT_LOCKED", required_artifacts=("split",))
    train_ids = split.loc[split["split_role"].eq("train"), "sample_id"].astype(int).tolist()
    all_ids = split["sample_id"].astype(int).tolist()
    permissions = provider.permission_rows()
    permission_contract = fit_permission_vocabulary(permissions, train_ids)
    permission_features, _ = transform_permission_features(permissions, all_ids, permission_contract)
    engines = provider.engine_metadata()
    readiness = engines.loc[engines.get("readiness_eligible_flag", pd.Series(0, index=engines.index)).astype(bool), "engine_name"].tolist() if "engine_name" in engines else []
    av_b_contract = fit_av_detection_contract(provider.vt_rows(), train_ids, scope="all_observed")
    av_c_contract = fit_av_detection_contract(provider.vt_rows(), train_ids, scope="readiness_eligible", readiness_eligible_engines=readiness)
    av_b = transform_av_detection_features(provider.vt_rows(), av_b_contract, all_ids)
    av_c = transform_av_detection_features(provider.vt_rows(), av_c_contract, all_ids)
    contracts = build_abc_feature_contracts(permission_features, provider.android_metadata(), av_b, av_c)
    frames = {arm: frame.set_index("sample_id").reindex(all_ids).fillna(0) for arm, frame in contracts.frames.items()}
    metadata = provider.android_metadata().set_index("sample_id").reindex(train_ids)
    sdk = fit_sdk_imputation_contract(metadata.rename(columns={"target_min_version": "target_min_version", "target_sdk_version": "target_sdk_version"}), columns=("target_min_version", "target_sdk_version")) if {"target_min_version", "target_sdk_version"}.issubset(metadata.columns) else fit_sdk_imputation_contract(metadata.rename(columns={"meta__target_min_version": "target_min_version", "meta__target_sdk_version": "target_sdk_version"}))
    feature_payload = {"column_hashes": contracts.column_hashes, "permission_contract": permission_contract.contract_hash, "av_b_contract": av_b_contract.policy_hash, "av_c_contract": av_c_contract.policy_hash, "sdk_contract": sdk.contract_hash}
    feature_path = _write(run_root, "feature_contracts.json", feature_payload)
    lifecycle.record_artifact("features", feature_path)
    lifecycle.transition("FEATURE_CONTRACTS_LOCKED", required_artifacts=("features",))
    models = validate_estimator_protocol()
    models_path = _write(run_root, "model_protocol.json", models)
    lifecycle.record_artifact("models", models_path)
    lifecycle.transition("MODELS_LOCKED", required_artifacts=("models",))
    labels = cohort.set_index("sample_id").loc[all_ids, "family_id"].astype(int).tolist()
    return FrozenBenchmarkContext(profile, experiment, lifecycle, cohort, split, frames, sorted(set(labels)), sdk.contract_hash, models)
