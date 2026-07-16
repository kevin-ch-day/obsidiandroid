"""Dedicated and fail-closed runner for ``android_family_av_abc_v1``.

The runner only locks/contracts synthetic or explicitly supplied frozen source
bundles.  It neither imports the legacy pipeline nor creates a live provider.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, precision_recall_fscore_support, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from obsidiandroid.common.hash_utils import hash_payload, sha256_hex
from obsidiandroid.features.av_detection_contract import fit_av_detection_contract, transform_av_detection_features
from obsidiandroid.features.av_readiness_contract import fit_av_readiness_contract
from obsidiandroid.features.frozen_abc_features import build_abc_feature_contracts
from obsidiandroid.features.permission_contract import (fit_permission_vocabulary, freeze_permission_knowledge_snapshot, load_primary_allowlist, transform_permission_features)
from obsidiandroid.governance.frozen_benchmark_config import load_frozen_cohort_profile, load_frozen_experiment, resolve_frozen_configuration
from obsidiandroid.governance.frozen_benchmark_lifecycle import FrozenBenchmarkLifecycle
from obsidiandroid.governance.frozen_benchmark_lock import create_frozen_group_split, freeze_cohort
from obsidiandroid.governance.frozen_benchmark_manifest import SDKImputationContract, apply_sdk_imputation, fit_sdk_imputation_contract, persist_source_extract, validate_estimator_protocol
from obsidiandroid.governance.frozen_benchmark_sources import FrozenBenchmarkSourceBundle, FrozenBenchmarkSourceProvider, SyntheticFrozenBenchmarkSourceProvider
from obsidiandroid.governance.frozen_label_mapping import FrozenLabelMapping, freeze_label_mapping
from obsidiandroid.evaluation.frozen_abc_comparator import paired_lineage_component_bootstrap


@dataclass
class FrozenBenchmarkContext:
    profile: dict[str, Any]
    experiment: dict[str, Any]
    resolved_configuration: dict[str, Any]
    lifecycle: FrozenBenchmarkLifecycle
    cohort: pd.DataFrame
    split: pd.DataFrame
    features: dict[str, pd.DataFrame]
    label_mapping: FrozenLabelMapping
    sdk_contract: SDKImputationContract
    model_protocol: dict[str, Any]
    source_bundle: FrozenBenchmarkSourceBundle


def _write(root: Path, name: str, payload: object) -> Path:
    path = root / name
    if isinstance(payload, pd.DataFrame):
        payload.to_csv(path, index=False)
    else:
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def _source_index(bundle: FrozenBenchmarkSourceBundle, root: Path, run_id: str, permission_knowledge: dict[str, object]) -> Path:
    entries = [
        persist_source_extract("cohort_labels", bundle.cohort, root),
        persist_source_extract("android_metadata", bundle.metadata, root),
        persist_source_extract("permissions", bundle.permissions, root),
        persist_source_extract("vt_engine_rows", bundle.verdicts, root),
        persist_source_extract("engine_metadata", bundle.engines, root),
        persist_source_extract("taxonomy_aliases", bundle.taxonomy, root),
    ]
    knowledge_path = _write(root / "source_extracts", "permission_knowledge.json", permission_knowledge)
    entries.append({"name": "permission_knowledge", "path": str(knowledge_path), "sha256": sha256_hex(knowledge_path.read_text(encoding="utf-8")), "reconstructable": True, "content_addressed": True})
    return _write(root, "source_snapshot_index.json", [{**entry, "run_id": run_id} for entry in entries])


def _permission_snapshot(bundle: FrozenBenchmarkSourceBundle) -> dict[str, object]:
    knowledge = bundle.permission_knowledge
    frame = lambda key: knowledge.get(key, pd.DataFrame()) if isinstance(knowledge.get(key, pd.DataFrame()), pd.DataFrame) else pd.DataFrame()
    aliases = dict(knowledge.get("alias_map") or {})
    return freeze_permission_knowledge_snapshot(
        permission_dictionary=frame("permission_dictionary"),
        authority_classification=frame("authority_classification"),
        protection_level_classification=frame("protection_level_classification"),
        approved_oem_google_tokens=(knowledge.get("approved_oem_google_tokens") or load_primary_allowlist().keys()),
        alias_map=aliases,
        known_missing_protection_policy=str(knowledge.get("known_missing_protection_policy") or "retain_known_token_in_known_count_exclude_from_protection_group"),
    )


def run_frozen_android_family_av_benchmark(provider: FrozenBenchmarkSourceProvider, *, run_root: Path, experiment_id: str = "android_family_av_abc_v1") -> FrozenBenchmarkContext:
    """Acquire sources once, freeze train-only contracts, and stop pre-holdout."""
    if experiment_id != "android_family_av_abc_v1":
        raise ValueError("Frozen runner only supports android_family_av_abc_v1.")
    profile, experiment = load_frozen_cohort_profile(), load_frozen_experiment(experiment_id)
    resolved = resolve_frozen_configuration(profile, experiment)
    bundle = FrozenBenchmarkSourceBundle.acquire(provider)
    classification = "synthetic_validation" if bool(getattr(provider, "synthetic_only", False)) or isinstance(provider, SyntheticFrozenBenchmarkSourceProvider) else "canonical"
    lifecycle = FrozenBenchmarkLifecycle(run_root, classification=classification)
    knowledge = _permission_snapshot(bundle)
    source_path = _source_index(bundle, run_root, lifecycle.run_id, knowledge)
    lifecycle.record_artifact("sources", source_path)
    snapshot_identity = getattr(provider, "snapshot_identity", None)
    if snapshot_identity:
        snapshot_identity_path = _write(run_root, "sealed_source_snapshot_identity.json", snapshot_identity)
        lifecycle.record_artifact("sealed_source_snapshot", snapshot_identity_path)
    locked = freeze_cohort(bundle.cohort, min_total_support=profile["cohort_policy"]["min_total_support"], max_component_share=profile["cohort_policy"]["max_component_share"], taxonomy=bundle.taxonomy)
    cohort = locked.frame
    cohort_path = _write(run_root, "cohort_lock.csv", cohort)
    lifecycle.record_artifact("cohort", cohort_path)
    lifecycle.transition("COHORT_LOCKED", required_artifacts=("cohort", "sources"), metadata=locked.payload)
    split = create_frozen_group_split(locked, min_train_support=profile["cohort_policy"]["min_train_support"], min_test_support=profile["cohort_policy"]["min_test_support"], min_test_components=profile["cohort_policy"]["min_lineage_components"])
    split_path = _write(run_root, "split_ledger.csv", split)
    lifecycle.record_artifact("split", split_path)
    lifecycle.transition("SPLIT_LOCKED", required_artifacts=("split",))
    train_ids = split.loc[split["split_role"].eq("train"), "sample_id"].astype(int).tolist()
    all_ids = split["sample_id"].astype(int).tolist()
    aliases = dict(bundle.permission_knowledge.get("alias_map") or {})
    allowlist = load_primary_allowlist()
    permission_contract = fit_permission_vocabulary(bundle.permissions, train_ids, aliases=aliases, allowlist=allowlist)
    permission_features, _ = transform_permission_features(bundle.permissions, all_ids, permission_contract)
    av_b_contract = fit_av_detection_contract(bundle.verdicts, train_ids, scope="all_observed")
    readiness = fit_av_readiness_contract(bundle.verdicts, bundle.engines, train_ids)
    if not readiness.eligible_engines:
        raise ValueError("No eligible engines satisfy the frozen outer-train readiness policy.")
    av_c_contract = fit_av_detection_contract(bundle.verdicts, train_ids, scope="readiness_eligible", readiness_eligible_engines=readiness.eligible_engines)
    if not av_c_contract.engine_columns:
        raise ValueError("No readiness-eligible observed engines satisfy arm C.")
    av_b = transform_av_detection_features(bundle.verdicts, av_b_contract, all_ids)
    av_c = transform_av_detection_features(bundle.verdicts, av_c_contract, all_ids)
    contracts = build_abc_feature_contracts(permission_features, bundle.metadata, av_b, av_c, permission_contract=permission_contract, av_b_contract=av_b_contract, av_c_contract=av_c_contract)
    frames = {arm: frame.set_index("sample_id").reindex(all_ids) for arm, frame in contracts.frames.items()}
    sdk_train = bundle.metadata.set_index("sample_id").reindex(train_ids)
    sdk = fit_sdk_imputation_contract(sdk_train, columns=("meta__target_min_version", "meta__target_sdk_version"))
    label_mapping = freeze_label_mapping(cohort)
    feature_payload = {
        "column_hashes": contracts.column_hashes, "permission_contract": permission_contract.contract_hash,
        "permission_knowledge": knowledge, "av_b_contract": av_b_contract.policy_hash,
        "av_c_contract": av_c_contract.policy_hash, "readiness_policy_hash": readiness.policy_hash,
        "readiness_train_id_hash": readiness.train_id_hash, "readiness_eligibility_hash": readiness.eligibility_hash,
        "sdk_contract": sdk.contract_hash, "sdk_medians": sdk.medians,
        "label_map_hash": label_mapping.label_map_hash, "probability_column_hash": label_mapping.probability_column_hash,
        "resolved_configuration_hash": hash_payload(resolved),
    }
    if snapshot_identity:
        # The run-local contract retains the sealed source identity and its
        # explicit mutable-latest-state temporal limitation.
        feature_payload["sealed_source_snapshot"] = snapshot_identity
    feature_path = _write(run_root, "feature_contracts.json", feature_payload)
    readiness_path = _write(run_root, "train_fitted_av_readiness.csv", readiness.ledger)
    label_path = _write(run_root, "frozen_label_mapping.csv", label_mapping.table)
    lifecycle.record_artifact("features", feature_path)
    lifecycle.record_artifact("readiness", readiness_path)
    lifecycle.record_artifact("labels", label_path)
    lifecycle.transition("FEATURE_CONTRACTS_LOCKED", required_artifacts=("features", "readiness", "labels"))
    models = validate_estimator_protocol(experiment["models"])
    models_path = _write(run_root, "model_protocol.json", models)
    lifecycle.record_artifact("models", models_path)
    lifecycle.transition("MODELS_LOCKED", required_artifacts=("models",))
    _write(run_root, "resolved_configuration.json", resolved)
    return FrozenBenchmarkContext(profile, experiment, resolved, lifecycle, cohort, split, frames, label_mapping, sdk, models, bundle)


def _estimator(name: str, classes: int, model_config: dict[str, Any]):
    config = {key: value for key, value in model_config[name].items() if key not in {"scaler", "early_stopping", "calibration"}}
    if name == "random_forest":
        return RandomForestClassifier(**config)
    if name == "logistic_regression":
        return make_pipeline(StandardScaler(with_mean=False), LogisticRegression(**config))
    return XGBClassifier(**{**config, "num_class": classes})


def _metric_payload(y_true: pd.Series, y_pred: pd.Series, labels: list[int]) -> dict[str, Any]:
    precision, recall, family_f1, support = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)), "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "per_family": [{"family_id": int(label), "precision": float(p), "recall": float(r), "f1": float(f), "support": int(s), "predicted_count": int((y_pred == label).sum())} for label, p, r, f, s in zip(labels, precision, recall, family_f1, support)],
        "confusion_matrix": matrix.tolist(), "label_universe": labels,
    }


def evaluate_synthetic_frozen_benchmark(context: FrozenBenchmarkContext, provider: FrozenBenchmarkSourceProvider) -> dict[str, Any]:
    """Execute exactly the predeclared synthetic plan; never a real holdout."""
    if not bool(getattr(provider, "synthetic_only", isinstance(provider, SyntheticFrozenBenchmarkSourceProvider))) or context.lifecycle.payload["classification"] != "synthetic_validation":
        raise RuntimeError("Real heldout evaluation is not authorized by this runner.")
    plan = context.experiment["evaluation_plan"]
    context.lifecycle.authorize(plan=plan, source_commit="synthetic", dependency_hash="synthetic", approved_manifest_hash=hash_payload(plan))
    split = context.split.set_index("sample_id")
    train_ids, test_ids = split.index[split.split_role.eq("train")].tolist(), split.index[split.split_role.eq("test")].tolist()
    family = context.cohort.set_index("sample_id")["family_id"]
    encoded = context.label_mapping.encode(family)
    labels = context.label_mapping.class_indices
    results, ledgers, executed = {}, [], []
    for arm, frame in context.features.items():
        for variant in (["base"] if arm == "A" else ["detection_only", "detection_plus_mask"]):
            selected = frame.copy()
            if variant == "detection_only":
                selected = selected[[column for column in selected if not column.startswith("avobs__")]]
            selected = apply_sdk_imputation(selected, context.sdk_contract)
            for name in plan["models"]:
                model = _estimator(name, len(labels), context.experiment["models"])
                model.fit(selected.loc[train_ids], encoded.loc[train_ids])
                predicted_index = pd.Series(model.predict(selected.loc[test_ids]), index=test_ids)
                probability = model.predict_proba(selected.loc[test_ids])
                classes = model.classes_ if hasattr(model, "classes_") else model.named_steps["logisticregression"].classes_
                if list(classes) != labels or probability.shape[1] != len(labels):
                    raise ValueError("Frozen probability columns do not match the fixed class order.")
                predicted = context.label_mapping.decode(predicted_index).set_axis(test_ids)
                truth = family.loc[test_ids]
                key = f"{arm}:{variant}:{name}"; executed.append(key)
                results[key] = _metric_payload(truth, predicted, context.label_mapping.table["family_id"].tolist())
                for row_index, sample_id in enumerate(test_ids):
                    row = {"sample_id": sample_id, "lineage_component_id": split.loc[sample_id, "lineage_component_id"], "family_id": int(truth.loc[sample_id]), "model": name, "arm": arm, "variant": variant, "y_true": int(truth.loc[sample_id]), "y_pred": int(predicted.loc[sample_id]), "prediction_rank": 1}
                    row.update({f"probability_class_{class_index}__family_{family_id}": float(probability[row_index, class_index]) for class_index, family_id in zip(labels, context.label_mapping.table["family_id"])})
                    ledgers.append(row)
    ledger = pd.DataFrame(ledgers)
    comparisons = []
    comparison_specs = (
        ("B_detection_plus_mask-B_detection_only", "B", "B", ("detection_only", "detection_plus_mask")),
        ("C_detection_plus_mask-C_detection_only", "C", "C", ("detection_only", "detection_plus_mask")),
        ("B-A", "A", "B", ("base", "detection_plus_mask")),
        ("C-A", "A", "C", ("base", "detection_plus_mask")),
        ("C-B", "B", "C", ("detection_plus_mask", "detection_plus_mask")),
    )
    for model in plan["models"]:
        for comparison_name, left, right, variants in comparison_specs:
            part = pd.concat([ledger[(ledger.arm == left) & (ledger.variant == variants[0])].assign(arm="left"), ledger[(ledger.arm == right) & (ledger.variant == variants[1])].assign(arm="right")])
            comparison = paired_lineage_component_bootstrap(part, model=model, left_arm="left", right_arm="right", label_universe=context.label_mapping.table["family_id"].tolist())
            comparison["comparison"] = comparison_name
            comparisons.append(comparison)
    prediction_path, comparison_path, metrics_path = _write(context.lifecycle.root, "heldout_predictions.csv", ledger), _write(context.lifecycle.root, "heldout_comparisons.json", comparisons), _write(context.lifecycle.root, "heldout_metrics.json", results)
    context.lifecycle.complete_evaluation(execution_cells=executed, prediction_path=prediction_path, comparison_path=comparison_path, metrics_path=metrics_path)
    return {"results": results, "comparisons": comparisons, "state": context.lifecycle.payload["state"]}
