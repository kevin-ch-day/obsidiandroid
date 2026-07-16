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
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.features.av_detection_contract import fit_av_detection_contract, transform_av_detection_features
from obsidiandroid.features.frozen_abc_features import build_abc_feature_contracts
from obsidiandroid.features.permission_contract import fit_permission_vocabulary, transform_permission_features
from obsidiandroid.governance.frozen_benchmark_config import load_frozen_cohort_profile, load_frozen_experiment
from obsidiandroid.governance.frozen_benchmark_lifecycle import FrozenBenchmarkLifecycle
from obsidiandroid.governance.frozen_benchmark_lock import create_frozen_group_split, freeze_cohort
from obsidiandroid.governance.frozen_benchmark_manifest import SDKImputationContract, apply_sdk_imputation, fit_sdk_imputation_contract, persist_source_extract, validate_estimator_protocol
from obsidiandroid.governance.frozen_benchmark_sources import FrozenBenchmarkSourceProvider, SyntheticFrozenBenchmarkSourceProvider
from obsidiandroid.evaluation.frozen_abc_comparator import paired_lineage_component_bootstrap


@dataclass
class FrozenBenchmarkContext:
    profile: dict[str, Any]
    experiment: dict[str, Any]
    lifecycle: FrozenBenchmarkLifecycle
    cohort: pd.DataFrame
    split: pd.DataFrame
    features: dict[str, pd.DataFrame]
    label_order: list[int]
    sdk_contract: SDKImputationContract
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
    sdk = fit_sdk_imputation_contract(metadata, columns=("meta__target_min_version", "meta__target_sdk_version"))
    feature_payload = {"column_hashes": contracts.column_hashes, "permission_contract": permission_contract.contract_hash, "av_b_contract": av_b_contract.policy_hash, "av_c_contract": av_c_contract.policy_hash, "sdk_contract": sdk.contract_hash}
    feature_path = _write(run_root, "feature_contracts.json", feature_payload)
    lifecycle.record_artifact("features", feature_path)
    lifecycle.transition("FEATURE_CONTRACTS_LOCKED", required_artifacts=("features",))
    models = validate_estimator_protocol()
    models_path = _write(run_root, "model_protocol.json", models)
    lifecycle.record_artifact("models", models_path)
    lifecycle.transition("MODELS_LOCKED", required_artifacts=("models",))
    labels = cohort.set_index("sample_id").loc[all_ids, "family_id"].astype(int).tolist()
    return FrozenBenchmarkContext(profile, experiment, lifecycle, cohort, split, frames, sorted(set(labels)), sdk, models)


def _cells() -> set[str]:
    return {f"{arm}:{variant}:{model}" for arm in ("A", "B", "C") for variant in (["base"] if arm == "A" else ["detection_only", "detection_plus_mask"]) for model in ("random_forest", "logistic_regression", "xgboost")}


def _estimator(name: str, classes: int):
    if name == "random_forest":
        return RandomForestClassifier(n_estimators=180, max_depth=12, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=1)
    if name == "logistic_regression":
        return make_pipeline(StandardScaler(with_mean=False), LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced", solver="lbfgs", random_state=42))
    return XGBClassifier(n_estimators=180, max_depth=6, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, reg_lambda=1.0, objective="multi:softprob", eval_metric="mlogloss", num_class=classes, random_state=42, n_jobs=1)


def evaluate_synthetic_frozen_benchmark(context: FrozenBenchmarkContext, provider: SyntheticFrozenBenchmarkSourceProvider) -> dict[str, Any]:
    """Execute the complete declared plan for synthetic fixtures only."""
    if not isinstance(provider, SyntheticFrozenBenchmarkSourceProvider):
        raise RuntimeError("Real heldout evaluation is not authorized by this runner.")
    plan = context.experiment["evaluation_plan"]
    context.lifecycle.authorize(plan=plan, clean_tree=True, source_commit="synthetic", dependency_hash="synthetic", approved_manifest_hash=hash_payload(plan))
    split = context.split.set_index("sample_id")
    train_ids = split.index[split.split_role.eq("train")].tolist()
    test_ids = split.index[split.split_role.eq("test")].tolist()
    labels = context.cohort.set_index("sample_id")["family_id"]
    results, ledgers, executed = {}, [], set()
    for arm, frame in context.features.items():
        for variant in (["base"] if arm == "A" else ["detection_only", "detection_plus_mask"]):
            selected = frame.copy()
            if variant == "detection_only":
                selected = selected[[column for column in selected if not column.startswith("avobs__")]]
            selected = apply_sdk_imputation(selected, context.sdk_contract)
            X_train, X_test = selected.loc[train_ids], selected.loc[test_ids]
            for name in context.experiment["evaluation_plan"]["models"]:
                model = _estimator(name, len(context.label_order))
                model.fit(X_train, labels.loc[train_ids])
                predicted = model.predict(X_test)
                probability = model.predict_proba(X_test)
                classes = model.classes_ if hasattr(model, "classes_") else model.named_steps["logisticregression"].classes_
                if list(classes) != context.label_order or probability.shape[1] != len(context.label_order):
                    raise ValueError("Frozen probability columns do not match the fixed class order.")
                key = f"{arm}:{variant}:{name}"
                executed.add(key)
                results[key] = {"macro_f1": float(f1_score(labels.loc[test_ids], predicted, labels=context.label_order, average="macro", zero_division=0)), "accuracy": float(accuracy_score(labels.loc[test_ids], predicted))}
                for sample_id, prediction in zip(test_ids, predicted):
                    ledgers.append({"sample_id": sample_id, "lineage_component_id": split.loc[sample_id, "lineage_component_id"], "family_id": int(labels.loc[sample_id]), "model": name, "arm": arm, "variant": variant, "y_true": int(labels.loc[sample_id]), "y_pred": int(prediction)})
    ledger = pd.DataFrame(ledgers)
    comparison_ledger = ledger[((ledger["arm"] == "A") & (ledger["variant"] == "base")) | ((ledger["arm"].isin(["B", "C"])) & (ledger["variant"] == "detection_plus_mask"))].drop(columns="variant")
    comparisons = [paired_lineage_component_bootstrap(comparison_ledger, model=name, left_arm=left, right_arm=right) for name in plan["models"] for left, right in (("A", "B"), ("A", "C"), ("B", "C"))]
    prediction_path, comparison_path = _write(context.lifecycle.root, "heldout_predictions.csv", ledger), _write(context.lifecycle.root, "heldout_comparisons.json", comparisons)
    context.lifecycle.complete_evaluation(execution_cells=executed, required_cells=_cells(), prediction_path=prediction_path, comparison_path=comparison_path)
    return {"results": results, "comparisons": comparisons, "state": context.lifecycle.payload["state"]}
