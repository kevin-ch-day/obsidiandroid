# Filename: model_trainer_factory.py
# Purpose  : Train ML classifiers for Android malware classification using a unified factory interface.
#            Supports Random Forest, Logistic Regression, SVM, and XGBoost with label encoding.

from collections import Counter
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Union

from obsidiandroid.cli.ui import display as du

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.preprocessing import LabelEncoder
import numpy as np

from config import app_config
from obsidiandroid.common import canonicalization, output_hygiene as oh
from obsidiandroid.common.cv_fold_config import (
    safe_float_config_value,
    safe_int_config_value,
)
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
    *,
    group_aware_requested: bool,
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
    group_token = (
        int(1)
        if (group_aware_requested and not ablation_lock)
        else int(0)
    )
    return (
        int(len(features_df)),
        n_features_key,
        index_hash,
        label_hash,
        float(test_size),
        int(random_state),
        bool(getattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", False)),
        safe_int_config_value(
            getattr(app_config, "MIN_TEST_SAMPLES_PER_CLASS", 1),
            default=1,
        ),
        group_token,
    )


def _resolve_training_runtime_defaults(
    test_size: float | None,
    random_state: int | None,
) -> tuple[float, int]:
    """Resolve training defaults at call time so runtime overrides take effect."""
    resolved_test_size = (
        safe_float_config_value(getattr(app_config, "TRAIN_TEST_SPLIT", 0.25), default=0.25)
        if test_size is None
        else float(test_size)
    )
    resolved_random_state = (
        safe_int_config_value(getattr(app_config, "RANDOM_STATE", 42), default=42)
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


def _filename_slug(value: str, max_len: int = 64) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    cleaned = cleaned.strip("_") or "unknown"
    return cleaned[:max_len]


def _split_key_hash(split_cache_key: tuple[Any, ...]) -> str:
    payload = json.dumps(list(split_cache_key), default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_lineage_groups_for_split(features_df: pd.DataFrame) -> tuple[np.ndarray | None, str]:
    """Assign integer group IDs for package lineage (fallback: sha256, then sample_id)."""
    meta = _runtime_sample_metadata()
    if meta.empty or "sample_id" not in meta.columns:
        return None, "no_runtime_metadata"
    sid_numeric = pd.to_numeric(features_df.index, errors="coerce")
    if sid_numeric.isna().any():
        return None, "non_numeric_feature_index"
    bridge = pd.DataFrame({"sample_id": sid_numeric.astype(int).values}, index=features_df.index)
    merged = bridge.merge(meta, on="sample_id", how="left")
    merged["sha256"] = merged.get("sha256", pd.Series([""] * len(merged))).fillna("").astype(str).str.strip().str.lower()
    pkg_col = merged.get("package_name")
    if pkg_col is None:
        merged["package_name"] = ""
    else:
        merged["package_name"] = pkg_col.fillna("").astype(str).str.strip().str.lower()

    def _gid(row: pd.Series) -> str:
        if str(row["package_name"]).strip():
            return f"pkg:{row['package_name']}"
        if str(row["sha256"]).strip():
            return f"sha:{row['sha256']}"
        return f"sid:{int(row['sample_id'])}"

    g_series = merged.apply(_gid, axis=1)
    if g_series.nunique() < 2:
        return None, "degenerate_lineage_groups"
    codes, _ = pd.factorize(g_series)
    return codes.astype(np.int64), "ok"


def _partition_sample_hash(rows: list[dict[str, str | int]]) -> str:
    rows_sorted = sorted(rows, key=lambda item: (str(item["sha256"]), int(item["sample_id"])))
    canonical_bytes = canonicalization.canonical_csv_bytes(
        rows=rows_sorted,
        fieldnames=["sample_id", "sha256"],
    )
    return hashlib.sha256(canonical_bytes).hexdigest()


def _export_split_audit(
    *,
    split_cache_key: tuple[Any, ...],
    sample_ids_train: list[int],
    sample_ids_test: list[int],
    random_state: int,
    model_type: str,
    active_class_count: int,
    label_field: str,
    label_target_slug: str,
    feature_set_token: str,
) -> None:
    """Export deterministic split ledger(s) and publish split hash runtime metadata."""
    run_id = _runtime_training_run_id()
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_dir:
        out_dir = Path(runtime_dir)
    else:
        out_dir = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))) / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    ablation = bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False))
    ledger_kind = "ablation" if ablation else "headline"
    ledger_scope: tuple[Any, ...] = (
        ("ablation", str(feature_set_token), str(label_target_slug), str(model_type))
        if ablation
        else ("headline",)
    )
    split_key_hash = _split_key_hash(split_cache_key)

    run_state = _runtime_training_state()
    split_audit_cache = run_state.setdefault("split_audit_cache", {})
    cache_key = (split_cache_key, str(out_dir.resolve()), run_id, ledger_scope)
    cached = split_audit_cache.get(cache_key)
    if cached is not None:
        meta_copy = dict(cached)
        setattr(app_config, "RUNTIME_SPLIT_HASH", meta_copy.get("split_hash"))
        setattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", meta_copy.get("split_audit_path"))
        setattr(app_config, "RUNTIME_SPLIT_METADATA", meta_copy)
        _lk = meta_copy.get("ledger_kind")
        if _lk in (None, "", "headline"):
            setattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", dict(meta_copy))
        if _lk == "ablation":
            idx = getattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", None)
            if not isinstance(idx, dict):
                idx = {}
            idx[
                (
                    run_id,
                    str(meta_copy.get("feature_set", "")),
                    str(meta_copy.get("label_target", "")),
                    str(meta_copy.get("split_model_written_for", "")),
                )
            ] = dict(meta_copy)
            setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", idx)
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

    train_rows_pf: list[dict[str, str | int]] = []
    test_rows_pf: list[dict[str, str | int]] = []
    for row in canonical_rows:
        if row["split_role"] == "train":
            train_rows_pf.append({"sample_id": row["sample_id"], "sha256": row["sha256"]})
        else:
            test_rows_pf.append({"sample_id": row["sample_id"], "sha256": row["sha256"]})
    train_sample_hash = _partition_sample_hash(train_rows_pf)
    test_sample_hash = _partition_sample_hash(test_rows_pf)

    split_df["year"] = _derive_year(split_df)
    for required_col in ("family_id", "family_name", "family_canonical", "package_name"):
        if required_col not in split_df.columns:
            split_df[required_col] = None
    def _lineage_gid_row(row: pd.Series) -> str:
        pk = str(row.get("package_name", "")).strip().lower()
        if pk:
            return f"pkg:{pk}"
        sha = str(row.get("sha256", "")).strip().lower()
        if sha:
            return f"sha:{sha}"
        return f"sid:{int(row['sample_id'])}"

    lineage_tokens = split_df.apply(_lineage_gid_row, axis=1)
    split_df["split_lineage_group_id"] = lineage_tokens.map(
        lambda tok: hashlib.sha256(str(tok).encode("utf-8")).hexdigest()[:16]
    )
    split_algorithm_effective = str(
        getattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", "stratified_seeded") or "stratified_seeded"
    )
    split_df["run_id"] = run_id
    split_df["split_hash"] = split_hash
    split_df["split_seed"] = int(random_state)
    split_df["split_algorithm"] = split_algorithm_effective
    split_df["split_algorithm_version"] = "1.1"
    split_df["label_field"] = str(label_field)
    split_df["label_target"] = str(label_target_slug)
    split_df["active_class_count"] = int(active_class_count)
    split_df["feature_set"] = str(feature_set_token)
    split_df["model"] = str(model_type)
    split_df["split_key_hash"] = split_key_hash
    split_df["train_sample_hash"] = train_sample_hash
    split_df["test_sample_hash"] = test_sample_hash
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
        "label_field",
        "label_target",
        "active_class_count",
        "feature_set",
        "model",
        "split_key_hash",
        "train_sample_hash",
        "test_sample_hash",
    ]
    audit_df = split_df[audit_cols].sort_values(["sha256", "sample_id"]).reset_index(drop=True)
    audit_csv = audit_df.to_csv(index=False)

    if ledger_kind == "headline":
        headline_path_name = f"split_freeze_headline_{run_id}.csv"
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=out_dir,
            run_filename=headline_path_name,
            csv_text=audit_csv,
            global_latest_name="split_freeze_headline.latest.csv",
        )
        legacy_audit_name = f"split_freeze_audit_{run_id}.csv"
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=out_dir,
            run_filename=legacy_audit_name,
            csv_text=audit_csv,
            global_latest_name="split_freeze_audit.latest.csv",
        )
        primary_path = out_dir / headline_path_name
    else:
        ablation_name = (
            "split_freeze_ablation__"
            f"{_filename_slug(feature_set_token)}__{_filename_slug(label_target_slug)}__"
            f"{_filename_slug(model_type)}__{run_id}.csv"
        )
        primary_path = out_dir / ablation_name
        primary_path.write_text(audit_csv, encoding="utf-8")

    meta: dict[str, Any] = {
        "ledger_kind": ledger_kind,
        "split_hash": split_hash,
        "split_audit_path": str(primary_path.resolve()),
        "split_seed": int(random_state),
        "split_algorithm": split_algorithm_effective,
        "split_algorithm_version": "1.1",
        "train_sample_count": int(len(sample_ids_train)),
        "test_sample_count": int(len(sample_ids_test)),
        "split_key_hash": split_key_hash,
        "train_sample_hash": train_sample_hash,
        "test_sample_hash": test_sample_hash,
        "label_field": str(label_field),
        "label_target": str(label_target_slug),
        "active_class_count": int(active_class_count),
        "feature_set": str(feature_set_token),
        "split_model_written_for": str(model_type),
    }
    if ledger_kind == "headline":
        meta["compat_split_audit_path"] = str((out_dir / f"split_freeze_audit_{run_id}.csv").resolve())

    split_audit_cache[cache_key] = dict(meta)
    setattr(app_config, "RUNTIME_SPLIT_HASH", split_hash)
    setattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", str(primary_path.resolve()))
    setattr(app_config, "RUNTIME_SPLIT_METADATA", dict(meta))
    if ledger_kind == "headline":
        setattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", dict(meta))
    else:
        idx = getattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", None)
        if not isinstance(idx, dict):
            idx = {}
        idx[(run_id, str(feature_set_token), str(label_target_slug), str(model_type))] = dict(meta)
        setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", idx)


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
    quiet_train = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))

    if isinstance(labels, pd.Series):
        label_field_resolved = str(labels.name) if labels.name is not None else "label"
    else:
        label_field_resolved = "label"
    label_target_slug = str(
        getattr(app_config, "RUNTIME_ABLATION_LABEL_TARGET_SLUG", "") or label_field_resolved
    ).strip()
    feature_set_token = str(getattr(app_config, "RUNTIME_EXPERIMENT_ID", "") or "").strip()
    _ablation_gate = bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False))
    if _ablation_gate:
        fs_override = str(getattr(app_config, "RUNTIME_ABLATION_FEATURE_SET_NAME", "") or "").strip()
        if fs_override:
            feature_set_token = fs_override
    if not feature_set_token and not _ablation_gate:
        feature_set_token = "headline_pipeline"
    elif not feature_set_token:
        feature_set_token = "ablation_unscoped"

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

    group_aware_cfg = bool(getattr(app_config, "ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT", False))
    ablation_lock = bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False))
    auto_adjust = bool(getattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", False))
    if group_aware_cfg and auto_adjust and not quiet_train:
        du.print_warning(
            "[SPLIT] ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT is ignored while "
            "AUTO_ADJUST_TRAIN_TEST_SPLIT is True (balanced auto split path)."
        )
    group_aware_requested = bool(
        group_aware_cfg
        and (not auto_adjust)
        and (not ablation_lock)
    )

    try:
        split_cache = _runtime_training_state().setdefault("split_cache", {})
        split_cache_key = _build_split_cache_key(
            features_df=features_df,
            encoded_labels=encoded_labels,
            test_size=test_size,
            random_state=random_state,
            group_aware_requested=group_aware_requested,
        )
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
            if not quiet_train:
                du.print_info(
                    "[SPLIT] Reusing cached train/test partition for model consistency "
                    "(cache key includes encoded labels; different label targets use independent splits)."
                )
            cached_meta = getattr(app_config, "RUNTIME_SPLIT_METADATA", None)
            if isinstance(cached_meta, dict) and cached_meta.get("split_algorithm"):
                setattr(
                    app_config,
                    "RUNTIME_LAST_SPLIT_ALGORITHM",
                    str(cached_meta.get("split_algorithm")),
                )
            else:
                setattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", "stratified_seeded")
        else:
            split_algo = "stratified_seeded"
            if getattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", False):
                from .dataset_splitter import balanced_train_test_split

                X_train, X_test, y_train, y_test = balanced_train_test_split(
                    features_df,
                    encoded_labels,
                    test_size=test_size,
                    random_state=random_state,
                    min_test_per_class=getattr(app_config, "MIN_TEST_SAMPLES_PER_CLASS", 1),
                )
                split_algo = "balanced_auto_adjusted_v1"
            elif group_aware_requested:
                groups_arr, group_note = _build_lineage_groups_for_split(features_df)
                if groups_arr is not None:
                    try:
                        gss = GroupShuffleSplit(
                            n_splits=1, test_size=test_size, random_state=random_state
                        )
                        train_pos, test_pos = next(
                            gss.split(features_df, encoded_labels, groups_arr)
                        )
                        X_train = features_df.iloc[train_pos]
                        X_test = features_df.iloc[test_pos]
                        y_train = encoded_labels[train_pos]
                        y_test = encoded_labels[test_pos]
                        split_algo = "group_shuffle_seeded_v1"
                        if not quiet_train:
                            du.print_info(
                                f"[SPLIT] Group-aware lineage split active ({group_note}); "
                                "not label-stratified — review rare-class coverage."
                            )
                    except Exception as exc:
                        if not quiet_train:
                            du.print_warning(
                                f"[SPLIT] Group-aware split failed ({exc}); using stratified split."
                            )
                        groups_arr = None
                if groups_arr is None:
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
            setattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", split_algo)
            if len(split_cache) >= 8:
                split_cache.clear()
            split_cache[split_cache_key] = (X_train, X_test, y_train, y_test)
    except Exception as e:
        raise RuntimeError(f"Train/test split failed: {e}")

    if not quiet_train:
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
        model_type=str(model_type),
        active_class_count=int(len(label_classes)),
        label_field=str(label_field_resolved),
        label_target_slug=str(label_target_slug),
        feature_set_token=str(feature_set_token),
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
    setattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "")
    if use_smote_effective and evidence_or_paper and disable_smote_evidence:
        if not quiet_train:
            du.print_info(
                "[SMOTE] Skipped for evidence/paper run (DISABLE_SMOTE_IN_EVIDENCE_MODE / "
                "OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE)."
            )
        use_smote_effective = False
    elif (
        use_smote_effective
        and evidence_or_paper
        and model_type != "balanced_random_forest"
        and not quiet_train
    ):
        warning_text = (
            "[SMOTE] Synthetic oversampling is enabled in evidence/paper mode; "
            "set OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE=1 to disable for stricter reproducibility."
        )
        du.print_warning(
            warning_text
        )
        setattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", warning_text)

    if use_smote_effective and model_type != "balanced_random_forest":
        X_train, y_train = apply_smote(X_train, y_train, random_state)
        snap = getattr(app_config, "RUNTIME_SMOTE_AUDIT_LAST", None)
        if isinstance(snap, dict):
            snap = dict(snap)
            snap["model_type"] = str(model_type)
            setattr(app_config, "RUNTIME_SMOTE_AUDIT_LAST", snap)
            by_model = getattr(app_config, "RUNTIME_SMOTE_AUDIT_BY_MODEL", None)
            if not isinstance(by_model, dict):
                by_model = {}
            by_model[str(model_type)] = dict(snap)
            setattr(app_config, "RUNTIME_SMOTE_AUDIT_BY_MODEL", by_model)

    prov = getattr(app_config, "RUNTIME_TRAINING_PROVENANCE_SUMMARY", None)
    if not isinstance(prov, dict):
        prov = {}
    cv_active = bool(
        cross_validate or getattr(app_config, "ENABLE_CROSS_VALIDATION", False)
    )
    prov.update(
        {
            "split_policy": str(
                getattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", "") or ""
            ),
            "holdout_train_smote_effective_last_fit": bool(
                use_smote_effective and model_type != "balanced_random_forest"
            ),
            "holdout_train_smote_config_enabled_default": bool(
                getattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True)
            ),
            "cross_validate_eval_enabled": cv_active,
            "model_trainer_model_type": str(model_type),
        }
    )
    setattr(app_config, "RUNTIME_TRAINING_PROVENANCE_SUMMARY", prov)

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
    if quiet_train:
        trainer_args["verbose"] = False
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

