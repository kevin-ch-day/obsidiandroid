# Filename: model_trainer_factory.py
# Purpose  : Train ML classifiers for Android malware classification using a unified factory interface.
#            Supports Random Forest, Logistic Regression, SVM, and XGBoost with label encoding.

from collections import Counter
import hashlib
from pathlib import Path
from typing import Any, Dict, Union

from obsidiandroid.cli.ui import display as du

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import numpy as np

from config import app_config
from obsidiandroid.common import canonicalization, output_hygiene as oh
from .training_helpers import (
    validate_training_inputs,
    get_model_trainer,
    perform_cross_validation,
    apply_smote,
)


def _runtime_training_run_id() -> str:
    """Return the active runtime run identifier for cache scoping."""
    return str(getattr(app_config, "RUNTIME_RUN_ID", "unknown") or "unknown").strip() or "unknown"


def _runtime_training_state() -> dict[str, dict]:
    """Return mutable run-scoped training state stored on runtime config."""
    state = getattr(app_config, "RUNTIME_TRAINING_STATE", None)
    if not isinstance(state, dict):
        state = {"runs": {}}
        setattr(app_config, "RUNTIME_TRAINING_STATE", state)

    runs = state.setdefault("runs", {})
    run_id = _runtime_training_run_id()
    run_state = runs.setdefault(
        run_id,
        {
            "split_cache": {},
            "split_audit_cache": {},
        },
    )
    return run_state


def reset_runtime_training_caches(run_id: str | None = None) -> None:
    """Clear run-scoped training caches for the active run or all runs."""
    state = getattr(app_config, "RUNTIME_TRAINING_STATE", None)
    if not isinstance(state, dict):
        return
    runs = state.setdefault("runs", {})
    if run_id is None:
        runs.clear()
    else:
        runs.pop(str(run_id).strip() or "unknown", None)


def _build_split_cache_key(
    features_df: pd.DataFrame,
    encoded_labels: np.ndarray,
    test_size: float,
    random_state: int,
) -> tuple:
    """Build a deterministic cache key for train/test split reuse."""
    index_hash = int(
        pd.util.hash_pandas_object(pd.Index(features_df.index).to_series(), index=False).sum()
    )
    label_hash = int(pd.util.hash_pandas_object(pd.Series(encoded_labels), index=False).sum())
    # Ablation feature sets differ in column count; use n_features_key=0 so the **same**
    # stratified train/test indices apply across vendor / permission / fused matrices.
    # Cached ``X_train`` / ``X_test`` DataFrames must not be reused directly — only their
    # indices — otherwise later experiments would train on the wrong feature columns.
    ablation_lock = bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False))
    n_features_key = 0 if ablation_lock else int(features_df.shape[1])
    return (
        int(len(features_df)),
        n_features_key,
        index_hash,
        label_hash,
        float(test_size),
        int(random_state),
        bool(getattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", False)),
        int(getattr(app_config, "MIN_TEST_SAMPLES_PER_CLASS", 1)),
    )


def _resolve_training_runtime_defaults(
    test_size: float | None,
    random_state: int | None,
) -> tuple[float, int]:
    """Resolve training defaults at call time so runtime overrides take effect."""
    resolved_test_size = (
        float(getattr(app_config, "TRAIN_TEST_SPLIT", 0.25))
        if test_size is None
        else float(test_size)
    )
    resolved_random_state = (
        int(getattr(app_config, "RANDOM_STATE", 42))
        if random_state is None
        else int(random_state)
    )
    return resolved_test_size, resolved_random_state


def _runtime_sample_metadata() -> pd.DataFrame:
    """Return runtime sample metadata for split audit joins."""
    meta = getattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", None)
    if not isinstance(meta, pd.DataFrame) or meta.empty:
        return pd.DataFrame()
    frame = meta.copy()
    # Normalize index early to avoid merge ambiguity when index name matches a key column.
    frame = frame.reset_index(drop=True)
    if "sample_id" not in frame.columns:
        frame["sample_id"] = frame.index
    frame["sample_id"] = pd.to_numeric(frame["sample_id"], errors="coerce")
    frame = frame.dropna(subset=["sample_id"]).copy()
    frame["sample_id"] = frame["sample_id"].astype(int)
    frame = frame.drop_duplicates("sample_id").reset_index(drop=True)
    return frame


def _derive_year(frame: pd.DataFrame) -> pd.Series:
    """Derive year from preferred effective timestamp columns."""
    for col in (
        "effective_first_seen_at_utc",
        "vt_first_submission_at_utc",
        "vt_first_seen_itw_date",
    ):
        if col in frame.columns:
            dt = pd.to_datetime(frame[col], errors="coerce", utc=True)
            return dt.dt.year
    return pd.Series([None] * len(frame), index=frame.index)


def _export_split_audit(
    *,
    split_cache_key: tuple,
    sample_ids_train: list[int],
    sample_ids_test: list[int],
    random_state: int,
) -> None:
    """Export deterministic split audit and publish split hash runtime metadata."""
    run_id = _runtime_training_run_id()
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_dir:
        out_dir = Path(runtime_dir)
    else:
        out_dir = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))) / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_state = _runtime_training_state()
    split_audit_cache = run_state.setdefault("split_audit_cache", {})
    cache_key = (split_cache_key, str(out_dir.resolve()), run_id)
    cached = split_audit_cache.get(cache_key)
    if cached is not None:
        setattr(app_config, "RUNTIME_SPLIT_HASH", cached.get("split_hash"))
        setattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", cached.get("split_audit_path"))
        setattr(app_config, "RUNTIME_SPLIT_METADATA", dict(cached))
        return

    paper_mode = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))

    split_rows = (
        [{"sample_id": int(sid), "split_role": "train"} for sid in sample_ids_train]
        + [{"sample_id": int(sid), "split_role": "test"} for sid in sample_ids_test]
    )
    split_df = pd.DataFrame(split_rows)
    meta_df = _runtime_sample_metadata()
    if not meta_df.empty:
        split_df = split_df.merge(meta_df, on="sample_id", how="left")
    else:
        split_df["sha256"] = None

    if "sha256" not in split_df.columns:
        split_df["sha256"] = None
    split_df["sha256"] = split_df["sha256"].fillna("").astype(str).str.strip().str.lower()

    if paper_mode and (split_df["sha256"] == "").any():
        missing = int((split_df["sha256"] == "").sum())
        raise RuntimeError(f"[PAPER] Split audit missing sha256 for {missing} sample(s).")

    canonical_rows: list[dict[str, str | int]] = []
    for _, row in split_df.iterrows():
        sha = str(row.get("sha256", "")).strip().lower()
        if paper_mode:
            try:
                sha = canonicalization.normalize_sha256(sha)
            except ValueError as exc:
                raise RuntimeError(f"[PAPER] {exc}") from exc
        canonical_rows.append(
            {
                "sample_id": int(row["sample_id"]),
                "sha256": sha,
                "split_role": str(row["split_role"]),
            }
        )
    canonical_rows.sort(key=lambda item: (item["sha256"], item["sample_id"]))
    canonical_bytes = canonicalization.canonical_csv_bytes(
        rows=canonical_rows,
        fieldnames=["sample_id", "sha256", "split_role"],
    )
    split_hash = hashlib.sha256(canonical_bytes).hexdigest()

    split_df["year"] = _derive_year(split_df)
    for required_col in ("family_id", "family_name", "family_canonical"):
        if required_col not in split_df.columns:
            split_df[required_col] = None
    split_df["run_id"] = run_id
    split_df["split_hash"] = split_hash
    split_df["split_seed"] = int(random_state)
    split_df["split_algorithm"] = "stratified_seeded"
    split_df["split_algorithm_version"] = "1.0"
    train_sha = set(
        split_df.loc[(split_df["split_role"] == "train") & (split_df["sha256"] != ""), "sha256"].tolist()
    )
    test_sha = set(
        split_df.loc[(split_df["split_role"] == "test") & (split_df["sha256"] != ""), "sha256"].tolist()
    )
    overlap_sha = train_sha.intersection(test_sha)
    split_df["duplicate_sha_group_across_splits"] = split_df["sha256"].isin(overlap_sha).astype(int)
    split_df["overlap_flag"] = split_df["duplicate_sha_group_across_splits"].astype(int)
    split_df["sha256_overlap_count"] = int(len(overlap_sha))
    split_df["sha256_overlap_across_split_flag"] = int(len(overlap_sha) > 0)

    audit_cols = [
        "sample_id",
        "sha256",
        "family_id",
        "family_name",
        "family_canonical",
        "year",
        "split_role",
        "run_id",
        "split_hash",
        "split_seed",
        "split_algorithm",
        "split_algorithm_version",
        "overlap_flag",
        "duplicate_sha_group_across_splits",
        "sha256_overlap_count",
        "sha256_overlap_across_split_flag",
    ]
    audit_df = split_df[audit_cols].sort_values(["sha256", "sample_id"]).reset_index(drop=True)
    audit_csv = audit_df.to_csv(index=False)
    split_path = out_dir / f"split_freeze_audit_{run_id}.csv"
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=split_path.name,
        csv_text=audit_csv,
        global_latest_name="split_freeze_audit.latest.csv",
    )

    meta = {
        "split_hash": split_hash,
        "split_audit_path": str(split_path),
        "split_seed": int(random_state),
        "split_algorithm": "stratified_seeded",
        "split_algorithm_version": "1.0",
        "train_sample_count": int(len(sample_ids_train)),
        "test_sample_count": int(len(sample_ids_test)),
    }
    split_audit_cache[cache_key] = meta
    setattr(app_config, "RUNTIME_SPLIT_HASH", split_hash)
    setattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", str(split_path))
    setattr(app_config, "RUNTIME_SPLIT_METADATA", dict(meta))


def train_model_factory(
    features_df: pd.DataFrame,
    labels: Union[list, pd.Series],
    model_type: str = "random_forest",
    test_size: float | None = None,
    random_state: int | None = None,
    enable_grid_search: bool = False,
    cross_validate: bool = False,
    use_smote: bool | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Trains an ML classifier using a unified interface.
    Returns model, test splits, encoders, and metadata.
    """
    validate_training_inputs(features_df, labels)
    test_size, random_state = _resolve_training_runtime_defaults(test_size, random_state)

    label_encoder = LabelEncoder()
    encoded_labels = label_encoder.fit_transform(labels)
    label_classes = list(label_encoder.classes_)

    cv_scores = None
    if cross_validate or getattr(app_config, "ENABLE_CROSS_VALIDATION", False):
        cv_scores = perform_cross_validation(
            features_df,
            encoded_labels,
            model_type,
            random_state,
        )

    try:
        split_cache = _runtime_training_state().setdefault("split_cache", {})
        split_cache_key = _build_split_cache_key(
            features_df=features_df,
            encoded_labels=encoded_labels,
            test_size=test_size,
            random_state=random_state,
        )
        ablation_lock = bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False))
        cached_split = split_cache.get(split_cache_key)
        if cached_split is not None:
            X_train, X_test, y_train, y_test = cached_split
            if ablation_lock:
                try:
                    X_train = features_df.loc[X_train.index]
                    X_test = features_df.loc[X_test.index]
                except KeyError as exc:
                    raise RuntimeError(
                        "[ABLATION] Split cache indices are missing from the current feature matrix; "
                        "cannot align cached train/test rows to this feature set."
                    ) from exc
            du.print_info(
                "[SPLIT] Reusing cached train/test partition for model consistency "
                "(cache key includes encoded labels; different label targets use independent splits)."
            )
        else:
            if getattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", False):
                from ml_classification.ml_utils import dataset_splitter
                X_train, X_test, y_train, y_test = dataset_splitter.balanced_train_test_split(
                    features_df,
                    encoded_labels,
                    test_size=test_size,
                    random_state=random_state,
                    min_test_per_class=getattr(app_config, "MIN_TEST_SAMPLES_PER_CLASS", 1),
                )
            else:
                label_counts = Counter(encoded_labels)
                min_support = min(label_counts.values()) if label_counts else 0
                stratify_y = encoded_labels if min_support >= 2 else None
                if stratify_y is None and len(label_counts) > 1:
                    du.print_warning(
                        "[SPLIT] Stratification disabled: at least one class has fewer than 2 "
                        "samples (sklearn stratified split requirement). Using a random split."
                    )
                X_train, X_test, y_train, y_test = train_test_split(
                    features_df,
                    encoded_labels,
                    test_size=test_size,
                    stratify=stratify_y,
                    random_state=random_state,
                )
            if len(split_cache) >= 8:
                split_cache.clear()
            split_cache[split_cache_key] = (X_train, X_test, y_train, y_test)
    except Exception as e:
        raise RuntimeError(f"Train/test split failed: {e}")

    du.print_info(
        f"[SPLIT] Train size: {len(X_train)} | Test size: {len(X_test)}"
    )
    train_dist = {int(k): int(v) for k, v in Counter(y_train).items()}
    test_dist = {int(k): int(v) for k, v in Counter(y_test).items()}
    du.print_debug(f"[SPLIT] Train dist: {train_dist}")
    du.print_debug(f"[SPLIT] Test dist: {test_dist}")

    # Split audit must be computed on the original deterministic split universe
    # before any synthetic resampling (e.g., SMOTE) mutates the training index.
    sample_ids_train = X_train.index.tolist()
    sample_ids_test = X_test.index.tolist()
    _export_split_audit(
        split_cache_key=split_cache_key,
        sample_ids_train=sample_ids_train,
        sample_ids_test=sample_ids_test,
        random_state=random_state,
    )

    use_smote_effective = (
        bool(getattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True))
        if use_smote is None
        else bool(use_smote)
    )
    evidence_or_paper = bool(
        getattr(app_config, "RUNTIME_EVIDENCE_MODE", False)
        or getattr(app_config, "PAPER_MODE_ENABLED", False)
    )
    disable_smote_evidence = bool(getattr(app_config, "DISABLE_SMOTE_IN_EVIDENCE_MODE", False))
    if use_smote_effective and evidence_or_paper and disable_smote_evidence:
        du.print_info(
            "[SMOTE] Skipped for evidence/paper run (DISABLE_SMOTE_IN_EVIDENCE_MODE / "
            "OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE)."
        )
        use_smote_effective = False
    elif use_smote_effective and evidence_or_paper and model_type != "balanced_random_forest":
        du.print_warning(
            "[SMOTE] Synthetic oversampling is enabled in evidence/paper mode; "
            "set OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE=1 to disable for stricter reproducibility."
        )

    if use_smote_effective and model_type != "balanced_random_forest":
        X_train, y_train = apply_smote(X_train, y_train, random_state)

    trainer = get_model_trainer(model_type)
    grid_search_flag = enable_grid_search
    if model_type == "random_forest":
        grid_search_flag = grid_search_flag or getattr(app_config, "ENABLE_RF_GRID_SEARCH", False)
    elif model_type == "svm":
        grid_search_flag = grid_search_flag or getattr(app_config, "ENABLE_SVM_GRID_SEARCH", False)
    elif model_type == "logistic_regression":
        grid_search_flag = grid_search_flag or getattr(app_config, "ENABLE_LR_GRID_SEARCH", False)
    elif model_type == "xgboost":
        grid_search_flag = grid_search_flag or getattr(app_config, "ENABLE_XGB_GRID_SEARCH", False)

    trainer_args = {
        "X_train": X_train,
        "y_train": y_train,
        "X_test": X_test,
        "y_test": y_test,
        "sample_ids": sample_ids_test,
        "label_encoder": label_encoder,
        "random_state": random_state,
        **kwargs,
    }
    if model_type in {"random_forest", "svm", "logistic_regression", "xgboost"}:
        trainer_args["grid_search"] = grid_search_flag

    try:
        model, result = trainer(**trainer_args)
    except Exception as e:
        raise RuntimeError(f"Training failed for '{model_type}': {e}")

    if not isinstance(result, dict):
        raise RuntimeError("Trainer returned invalid result structure")

    return {
        "model": model,
        "X_test": X_test,
        "y_test": y_test,
        "label_classes": label_classes,
        "label_encoder": label_encoder,
        "sample_ids_train": sample_ids_train,
        "sample_ids_test": sample_ids_test,
        "cv_scores": cv_scores,
        "cv_score_mean": float(np.mean(cv_scores)) if cv_scores is not None else None,
        **result,
    }


