"""Authorization and evidence contracts for the frozen A/B/C benchmark.

This module cannot run a model or inspect held-out predictions.  It validates
the record that must exist before one atomic held-out execution is authorized.
"""

from __future__ import annotations

import subprocess
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload, sha256_hex


ARMS = ("A", "B", "C")
MODELS = ("random_forest", "logistic_regression", "xgboost")
SENSITIVITIES = ("detection_only", "detection_plus_mask")
COMPARISONS = ("B-A", "C-A", "C-B")
REQUIRED_SNAPSHOT_NAMES = frozenset({"cohort_labels", "permissions", "vt_engine_rows", "engine_metadata", "taxonomy_aliases"})


@dataclass(frozen=True)
class SDKImputationContract:
    columns: tuple[str, ...]
    medians: dict[str, float]
    contract_hash: str


def fit_sdk_imputation_contract(outer_train: pd.DataFrame, columns: Iterable[str] = ("target_min_version", "target_sdk_version")) -> SDKImputationContract:
    """Fit the shared SDK medians on outer-train only."""
    names = tuple(columns)
    missing = set(names).difference(outer_train.columns)
    if missing:
        raise ValueError(f"SDK imputation columns missing from outer train: {sorted(missing)}")
    medians: dict[str, float] = {}
    for name in names:
        values = pd.to_numeric(outer_train[name], errors="coerce").dropna()
        if values.empty:
            raise ValueError(f"SDK imputation cannot fit all-missing column: {name}")
        medians[name] = float(values.median())
    return SDKImputationContract(names, medians, hash_payload({"columns": names, "medians": medians, "fit_partition": "outer_train_only"}))


def apply_sdk_imputation(frame: pd.DataFrame, contract: SDKImputationContract) -> pd.DataFrame:
    """Apply one frozen imputation contract before every model run."""
    out = frame.copy()
    for name in contract.columns:
        if name not in out:
            raise ValueError(f"SDK column absent during transform: {name}")
        out[name] = pd.to_numeric(out[name], errors="coerce").fillna(contract.medians[name])
    return out


def persist_source_extract(name: str, frame: pd.DataFrame, evidence_root: Path) -> dict[str, object]:
    """Create a minimal content-addressed extract, not only a provenance hash."""
    safe = "".join(char if char.isalnum() or char in "_-" else "_" for char in name)
    content = frame.sort_index(axis=1).to_csv(index=False, lineterminator="\n").encode("utf-8")
    digest = sha256_hex(content.decode("utf-8"))
    path = Path(evidence_root) / "source_extracts" / f"{safe}_{digest[:16]}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"name": name, "path": str(path), "sha256": digest, "reconstructable": True, "content_addressed": True}


def snapshot_metadata(name: str, payload: object, *, reconstructable: bool, source_path: str | None = None) -> dict[str, object]:
    """Describe hash-only inputs honestly when local preservation is impossible."""
    result = {"name": name, "sha256": hash_payload(payload), "reconstructable": bool(reconstructable), "content_addressed": False}
    if source_path:
        result["source_path"] = source_path
    return result


def validate_atomic_evaluation_plan(plan: dict[str, Any]) -> None:
    if tuple(plan.get("arms", ())) != ARMS or tuple(plan.get("models", ())) != MODELS:
        raise ValueError("Atomic heldout plan must enumerate A/B/C and all three frozen models.")
    expected_sensitivities = {(arm, sensitivity) for arm in ("B", "C") for sensitivity in SENSITIVITIES}
    if {tuple(value) for value in plan.get("sensitivity_contrasts", ())} != expected_sensitivities:
        raise ValueError("Atomic heldout plan must declare B/C detection-only and detection-plus-mask sensitivity contrasts.")
    if tuple(plan.get("paired_comparisons", ())) != COMPARISONS or not plan.get("metrics"):
        raise ValueError("Atomic heldout plan must declare comparisons and metrics before authorization.")


def validate_estimator_protocol() -> dict[str, dict[str, Any]]:
    """Build estimators in the installed environment and reject ignored params."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from xgboost import XGBClassifier

    lr_supports_multi_class = "multi_class" in inspect.signature(LogisticRegression).parameters
    expected = {
        "random_forest": {"n_estimators": 180, "max_depth": 12, "min_samples_leaf": 2, "class_weight": "balanced", "random_state": 42, "n_jobs": 1},
        "logistic_regression": {"C": 1.0, "max_iter": 2000, "class_weight": "balanced", "solver": "lbfgs", "random_state": 42},
        "xgboost": {"n_estimators": 180, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.85, "colsample_bytree": 0.85, "reg_lambda": 1.0, "objective": "multi:softprob", "eval_metric": "mlogloss", "random_state": 42, "n_jobs": 1},
    }
    if lr_supports_multi_class:
        expected["logistic_regression"]["multi_class"] = "auto"
    estimators = {
        "random_forest": RandomForestClassifier(**expected["random_forest"]),
        "logistic_regression": LogisticRegression(**expected["logistic_regression"]),
        "xgboost": XGBClassifier(**expected["xgboost"]),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, estimator in estimators.items():
        resolved = estimator.get_params(deep=False)
        mismatch = {key: (value, resolved.get(key)) for key, value in expected[name].items() if resolved.get(key) != value}
        if mismatch:
            raise ValueError(f"Frozen estimator parameters unresolved for {name}: {mismatch}")
        result[name] = {"explicit": expected[name], "inherited_defaults": sorted(set(resolved).difference(expected[name])), "ignored": [], "resolved_hash": hash_payload(resolved)}
    result["logistic_regression"]["multiclass_resolution"] = (
        "explicit_auto" if lr_supports_multi_class else "automatic_by_lbfgs_api_multi_class_parameter_removed"
    )
    return result


def clean_tree(repo_root: Path) -> bool:
    return subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, check=True, capture_output=True, text=True).stdout == ""


def authorize_heldout(manifest: dict[str, Any], *, repo_root: Path, dirty_tree_override: bool = False) -> dict[str, Any]:
    """Canonical authorization requires clean sources; overrides are exploratory."""
    validate_atomic_evaluation_plan(manifest.get("evaluation_plan", {}))
    names = {entry.get("name") for entry in manifest.get("source_snapshots", [])}
    missing = REQUIRED_SNAPSHOT_NAMES.difference(names)
    if missing or any(not entry.get("sha256") for entry in manifest.get("source_snapshots", [])):
        raise ValueError(f"Canonical authorization missing complete source snapshots: {sorted(missing)}")
    required = ("source_commit", "dependency_hash", "approved_manifest_hash")
    absent = [key for key in required if not manifest.get(key)]
    if absent:
        raise ValueError(f"Canonical authorization missing: {absent}")
    is_clean = clean_tree(repo_root)
    if not is_clean and not dirty_tree_override:
        raise ValueError("HELDOUT_AUTHORIZED requires dirty_tree=false.")
    result = dict(manifest)
    result["dirty_tree"] = is_clean
    result["authorization_state"] = "HELDOUT_AUTHORIZED" if is_clean and not dirty_tree_override else "EXPLORATORY_UNAUTHORIZED"
    return result
