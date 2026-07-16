"""Strict loaders for the isolated Android-family A/B/C benchmark."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from obsidiandroid.common.hash_utils import hash_payload


_ROOT = Path(__file__).resolve().parents[3]
PROFILE_REQUIRED = {"profile_id", "schema_version", "cohort_contract_id", "label_policy", "cohort_policy"}
EXPERIMENT_REQUIRED = {"experiment_id", "schema_version", "cohort_profile_id", "parser_policy", "permission_contract_id", "av_contract_id", "feature_contracts", "allowed_sdk_columns", "models", "holdout", "evaluation_plan", "bootstrap"}


def _load(path: Path, required: set[str]) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Frozen benchmark configuration not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"Frozen benchmark configuration missing fields: {sorted(missing)}")
    return payload


def load_frozen_cohort_profile(profile_id: str = "android_malware_major_families_frozen_n20_v1") -> dict[str, Any]:
    payload = _load(_ROOT / "profiles" / f"{profile_id}.yaml", PROFILE_REQUIRED)
    policy, labels = payload["cohort_policy"], payload["label_policy"]
    required_policy = {"min_total_support", "min_train_support", "min_test_support", "min_lineage_components", "max_component_share", "duplicate_sha_policy", "cross_family_component_policy", "package_validation", "split_policy"}
    if policy.keys() < required_policy or labels.keys() < {"target", "canonical_label", "reject_placeholders", "taxonomy_snapshot_required", "alias_snapshot_required"}:
        raise ValueError("Frozen cohort profile has an incomplete policy.")
    if payload["profile_id"] != profile_id or policy["split_policy"] != "stratified_group_kfold_holdout_v1_no_fallback":
        raise ValueError("Frozen cohort profile identity or split policy is invalid.")
    return payload


def load_frozen_experiment(experiment_id: str = "android_family_av_abc_v1") -> dict[str, Any]:
    payload = _load(_ROOT / "experiments" / f"{experiment_id}.yaml", EXPERIMENT_REQUIRED)
    if payload["experiment_id"] != experiment_id or payload["parser_policy"] != "disabled":
        raise ValueError("Frozen experiment identity or parser policy is invalid.")
    if set(payload["feature_contracts"]) != {"A", "B", "C"} or payload["vt_aggregate_features"] != "prohibited":
        raise ValueError("Frozen experiment feature contracts are incomplete.")
    if payload["resampling"] != "prohibited" or payload["tuning"] != "prohibited":
        raise ValueError("Frozen experiment must prohibit tuning and resampling.")
    return payload


def resolve_frozen_configuration(profile: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    """Create the single run configuration and reject cross-file drift."""
    if experiment["cohort_profile_id"] != profile["profile_id"]:
        raise ValueError("Frozen experiment/profile identity drift.")
    resolved = {"profile": profile, "experiment": experiment}
    resolved["resolved_configuration_hash"] = hash_payload(resolved)
    return resolved
