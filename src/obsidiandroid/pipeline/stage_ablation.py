"""Ablation experiment helpers for leakage sensitivity evaluation.

Canonical implementation (**Pass 70**): ``obsidiandroid.pipeline.stage_ablation``;
The supported import path is ``obsidiandroid.pipeline.stage_ablation``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any
import shutil

import pandas as pd

from config import app_config
from obsidiandroid.common.cv_fold_config import safe_float_config_value, safe_int_config_value
from obsidiandroid.modeling import distribution_reporter
from obsidiandroid.modeling import pipeline_core
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir
from obsidiandroid.common.hash_utils import hash_payload

from obsidiandroid.diagnostics import ablation_cohort_diagnostics
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.reporting.operator_dashboard import format_feature_set_label
from obsidiandroid.pipeline.ablation import registry as ablation_registry


class PaperCohortSource(str, Enum):
    """Source modes for paper cohort sample-id loading."""

    RUNTIME_ONLY = "runtime_only"
    DISK_ONLY = "disk_only"
    AUTO = "auto"


def _diagnostics_dir() -> Path:
    """Resolve diagnostics directory for current runtime context."""
    return resolve_diagnostics_dir()


def _write_ablation_progress_snapshot(
    *,
    diagnostics_dir: Path,
    run_id: str,
    total_combo_count: int,
    current_combo_id: str,
    combo_records: list[dict[str, Any]],
    summary_row_count: int,
    grid_status: str,
) -> Path:
    """Persist a small, atomically replaced progress capsule for a long ablation grid."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    path = diagnostics_dir / f"ablation_progress_{run_id}.json"
    payload = {
        "run_id": str(run_id),
        "grid_status": str(grid_status),
        "total_combo_count": int(total_combo_count),
        "completed_combo_count": int(len(combo_records)),
        "current_combo_id": str(current_combo_id),
        "summary_row_count": int(summary_row_count),
        "combo_records": list(combo_records),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
    return path


def _build_permissions_band_matrix(
    permission_features_df: pd.DataFrame | None, *, subset: str
) -> pd.DataFrame:
    base = _build_permissions_only_matrix(permission_features_df)
    if base.empty:
        return base
    raw_onehot_exclude = {
        "perm__dangerous_count",
        "perm__normal_count",
        "perm__oem_count",
        "perm__total_count",
    }
    if subset == "raw":
        keep = [
            c
            for c in base.columns
            if str(c).startswith("perm__")
            and not str(c).startswith("perm_grp__")
            and str(c) not in raw_onehot_exclude
        ]
    elif subset == "grouped":
        keep = [c for c in base.columns if str(c).startswith("perm_grp__")] + [
            c for c in base.columns if c in raw_onehot_exclude
        ]
    else:
        keep = list(base.columns)
    if not keep:
        return pd.DataFrame(index=base.index)
    subset_df = base[keep].copy()
    subset_df.attrs.update(base.attrs)
    return subset_df


def _build_experiment_matrix_dict(
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    permission_features_df: pd.DataFrame | None,
    pipeline_results: dict[str, Any] | None,
    cohort_sample_ids: list[int] | None,
) -> dict[str, Any]:
    return ablation_registry.build_experiment_matrix_dict(
        weights_df=weights_df,
        parsed_data=parsed_data,
        permission_features_df=permission_features_df,
        pipeline_results=pipeline_results,
        cohort_sample_ids=cohort_sample_ids,
        permissions_band_builder=lambda df, subset: _build_permissions_band_matrix(df, subset=subset),
    )


ABLATION_EXPERIMENT_ORDER: tuple[str, ...] = (
    "vendor_full",
    "vendor_no_parsed_family",
    "vendor_no_family_no_type",
    "vendor_detection_binary_only",
    "vendor_consensus_scores_only",
    "permissions_raw",
    "permissions_grouped",
    "permissions_grouped_plus_vendor_no_family",
    "full_fused",
)

ABLATION_TERMINAL_LABELS: dict[str, str] = {
    "vendor_full": "Vendor (parsed-family fields)",
    "vendor_no_parsed_family": "Vendor-NoFam",
    "vendor_no_family_no_type": "Vendor (no family/type strings)",
    "vendor_detection_binary_only": "Vendor detections only",
    "vendor_consensus_scores_only": "Vendor consensus scores",
    "permissions_raw": "Permissions (raw)",
    "permissions_grouped": "Permissions (grouped)",
    "permissions_grouped_plus_vendor_no_family": "Permissions (grouped) + Vendor-NoFam",
    "full_fused": "Full fused",
}

_PERMISSION_ONLY_EXPERIMENTS = {"permissions_raw", "permissions_grouped"}
_VENDOR_SAFE_EXPERIMENTS = {
    "vendor_no_parsed_family",
    "vendor_detection_binary_only",
    "vendor_consensus_scores_only",
}

# These are intentionally AV-label-informed sensitivity experiments.  They
# must be visibly scoped to ablation, never admitted to the headline feature
# contract, and remain distinguishable from label-independent experiments.
_LABEL_ADJACENT_ABLATION_EXPERIMENTS = {
    "vendor_full",
    "vendor_no_parsed_family",
    "permissions_grouped_plus_vendor_no_family",
    "full_fused",
}


def _format_ablation_terminal_label(experiment: str) -> str:
    return ABLATION_TERMINAL_LABELS.get(str(experiment), format_feature_set_label(str(experiment)))


def _format_ablation_score_cell(experiment: str, model: str, macro_f1: float | None) -> str:
    label = _format_ablation_terminal_label(experiment)
    if macro_f1 is None or pd.isna(macro_f1):
        return f"{label} / {model}"
    return f"{label} / {model} ({float(macro_f1):.4f})"


def _prepare_training_inputs(
    feature_df: pd.DataFrame,
    samples_df: pd.DataFrame,
    *,
    forced_label_column: str | None = None,
) -> tuple[pd.DataFrame | None, pd.Series | None]:
    aligned_features, labels_df = pipeline_core.align_data(
        feature_df,
        samples_df,
        forced_label_column=forced_label_column,
    )
    if aligned_features is None or labels_df is None:
        return None, None

    min_support = int(
        getattr(
            app_config,
            "RUNTIME_MIN_FAMILY_SUPPORT",
            getattr(app_config, "MIN_FAMILY_SUPPORT", 3),
        )
        or 3
    )
    group_label = (
        "other" if bool(getattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False)) else None
    )
    aligned_features, labels_df, _, _, _ = distribution_reporter.apply_min_family_support(
        features_df=aligned_features,
        labels_df=labels_df,
        min_support=min_support,
        group_label=group_label,
    )
    # Train-only selection is applied by model_trainer_factory after its
    # frozen ablation split is established.  Do not use all ablation rows to
    # decide column survival here.
    return aligned_features, labels_df


def _extract_feature_sample_ids(feature_df: pd.DataFrame) -> set[int]:
    """Extract normalized sample IDs from feature matrix index/column."""
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return set()
    if "sample_id" in feature_df.columns:
        ids = pd.to_numeric(feature_df["sample_id"], errors="coerce")
    else:
        ids = pd.to_numeric(pd.Index(feature_df.index), errors="coerce")
    return set(ids.dropna().astype(int).tolist())


def reindex_ablation_features_to_frozen_ids(
    feature_df: pd.DataFrame,
    frozen_sorted: list[int],
) -> pd.DataFrame:
    """Reindex a feature matrix to the frozen paper cohort, filling missing rows with 0.

    Decouples ablation **feature effects** from **row drops** when vendor-only matrices omit
    samples that lack parsed top-k vendor rows.
    """
    if not frozen_sorted:
        return pd.DataFrame()
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return pd.DataFrame(index=frozen_sorted)

    work = feature_df.copy()
    if "sample_id" in work.columns:
        work = work.drop_duplicates("sample_id", keep="last")
        sid = pd.to_numeric(work["sample_id"], errors="coerce")
        work = work.assign(_abl_sid=sid).dropna(subset=["_abl_sid"])
        work["_abl_sid"] = work["_abl_sid"].astype(int)
        work = work.set_index("_abl_sid")
        drop_cols = [c for c in work.columns if str(c).startswith("_abl_")]
        if drop_cols:
            work = work.drop(columns=drop_cols, errors="ignore")
    else:
        work.index = pd.to_numeric(work.index, errors="coerce")
        work = work[~pd.Index(work.index).isna()]
        work = work[~work.index.duplicated(keep="last")]

    work = work.reindex(frozen_sorted)
    return work.fillna(0)


def _print_ablation_cohort_integrity_table(rows: list[dict[str, Any]]) -> None:
    """Operator/debug ablation cohort integrity summary."""
    if not rows or ml_console.is_minimal():
        return
    all_ok = all(str(row.get("status", "")).strip().upper() == "OK" for row in rows)
    aligned_ids = max(int(row.get("final_aligned_ids", 0) or 0) for row in rows)
    missing_ids = 0 if all_ok else sum(int(row.get("missing_vs_expected", 0) or 0) for row in rows)
    if all_ok and not ml_console.is_debug():
        from obsidiandroid.evaluation.ml_terminal_presentation import print_ablation_cohort_integrity_summary

        print_ablation_cohort_integrity_summary(
            aligned_feature_sets=len(rows),
            total_feature_sets=len(rows),
            aligned_samples=aligned_ids,
            missing_ids=missing_ids,
        )
        return
    frame = pd.DataFrame(rows)
    rename_map = {
        "feature_set": "Feature Set",
        "expected_ids": "Expected IDs",
        "raw_matrix_ids": "Matrix IDs",
        "missing_vs_expected": "Missing IDs",
        "final_aligned_ids": "Final Aligned IDs",
        "status": "Status",
    }
    cols = [c for c in rename_map if c in frame.columns]
    if not cols:
        return
    du.print_table(
        frame[cols].rename(columns=rename_map),
        title="Ablation cohort integrity (pre-train)",
        show_index=False,
    )


def _print_ablation_combo_summary(
    experiment_name: str,
    label_slug: str,
    results: dict[str, dict],
) -> None:
    """Emit one compact progress line per ablation combo instead of per-model timing spam."""
    if not results or not ml_console.is_debug():
        return

    rows: list[dict[str, float | str]] = []
    for model_name, result in sorted(results.items()):
        evaluation = result.get("evaluation", {}) if isinstance(result, dict) else {}
        macro_f1 = pd.to_numeric(evaluation.get("macro_f1_score"), errors="coerce")
        train_time = pd.to_numeric(evaluation.get("train_time"), errors="coerce")
        rows.append(
            {
                "model": str(model_name),
                "macro_f1_score": float(macro_f1) if pd.notna(macro_f1) else float("nan"),
                "train_time": float(train_time) if pd.notna(train_time) else float("nan"),
            }
        )

    if not rows:
        return

    best_row = max(
        rows,
        key=lambda item: item["macro_f1_score"]
        if pd.notna(item["macro_f1_score"])
        else float("-inf"),
    )
    slowest_row = max(
        rows,
        key=lambda item: item["train_time"]
        if pd.notna(item["train_time"])
        else float("-inf"),
    )
    total_fit_seconds = sum(
        float(item["train_time"]) for item in rows if pd.notna(item["train_time"])
    )
    du.print_info(
        "[ABLATION] "
        f"{experiment_name} / {label_slug}: "
        f"{len(rows)} model(s) | "
        f"best={best_row['model']} MacroF1={best_row['macro_f1_score']:.4f} | "
        f"fit_total={total_fit_seconds:.2f}s | "
        f"slowest={slowest_row['model']} {slowest_row['train_time']:.2f}s"
    )


def _print_ablation_combo_progress(
    *,
    completed: int,
    total: int,
    experiment_name: str,
    label_slug: str,
    status: str,
    detail: str,
) -> None:
    """Emit one durable, human-readable checkpoint for a long ablation grid."""
    if ml_console.is_minimal():
        return
    finished = max(0, int(completed))
    planned = max(0, int(total))
    percent = (100.0 * finished / planned) if planned else 0.0
    label = _format_ablation_terminal_label(experiment_name)
    context = f"{label} / {label_slug}"
    line = f"[ABLATION] Progress {finished}/{planned} ({percent:.0f}%) — {context}: {status}"
    if detail:
        line += f" ({detail})"
    if str(status).lower() in {"failed", "skipped", "interrupted_or_aborted"}:
        du.print_warning(line)
    else:
        du.print_info(line)


def _build_ablation_feature_set_summary_rows(
    *,
    experiment_order: list[str],
    built_matrices: dict[str, pd.DataFrame],
    skipped_experiments: list[dict[str, str]],
) -> list[dict[str, Any]]:
    skipped_map = {str(row.get("feature_set", "")): dict(row) for row in skipped_experiments}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for experiment_name in experiment_order:
        seen.add(str(experiment_name))
        matrix = built_matrices.get(experiment_name)
        skipped = skipped_map.get(experiment_name)
        selected_vendors = "—"
        effective_top_k = "—"
        columns = 0
        status = "SKIPPED" if skipped is not None else "OK"
        skip_reason = str(skipped.get("reason", "")) if skipped is not None else ""
        if isinstance(matrix, pd.DataFrame) and not matrix.empty:
            columns = int(matrix.shape[1])
            selected_vendor_list = matrix.attrs.get("selected_vendors", [])
            if isinstance(selected_vendor_list, list) and selected_vendor_list:
                selected_vendors = str(len(selected_vendor_list))
            eff_top_k = matrix.attrs.get("feature_effective_top_k")
            if eff_top_k not in (None, "", 0):
                effective_top_k = str(int(eff_top_k))
        rows.append(
            {
                "feature_set": _format_ablation_terminal_label(experiment_name),
                "columns": columns,
                "selected_vendors": selected_vendors,
                "effective_top_k": effective_top_k,
                "status": status,
                "skip_reason": skip_reason or "—",
            }
        )
    for experiment_name, skipped in skipped_map.items():
        if experiment_name in seen:
            continue
        rows.append(
            {
                "feature_set": _format_ablation_terminal_label(experiment_name),
                "columns": 0,
                "selected_vendors": "—",
                "effective_top_k": "—",
                "status": "SKIPPED",
                "skip_reason": str(skipped.get("reason", "") or "—"),
            }
        )
    return rows


def _has_variable_predictive_column(feature_df: pd.DataFrame) -> bool:
    """Return whether an ablation matrix contains at least one usable signal column.

    The normal train-only selector correctly rejects a matrix whose columns are
    all constant.  Detecting that case here avoids needlessly invoking every
    model for every label target and prevents a skipped feature set from
    flooding the operator terminal with repeated training failures.
    """
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return False
    for column in feature_df.columns:
        if str(column) == "sample_id":
            continue
        try:
            if int(feature_df[column].nunique(dropna=False)) > 1:
                return True
        except (TypeError, ValueError):
            # A column that cannot be counted is left to the normal feature
            # contract validator rather than silently discarded here.
            return True
    return False


def _load_paper_cohort_sample_ids(
    samples_df: pd.DataFrame,
    source: PaperCohortSource = PaperCohortSource.AUTO,
    cohort_path: Path | None = None,
) -> set[int]:
    """Load paper cohort IDs from runtime rows and/or frozen disk snapshot.

    Args:
        samples_df: Runtime sample frame.
        source: Loading source mode.
        cohort_path: Optional explicit cohort path when disk loading is used.

    Returns:
        Set of normalized sample IDs.
    """
    resolved_path = cohort_path or Path(
        str(
            getattr(
                app_config,
                "PAPER_COHORT_SAMPLE_IDS_FILE",
                "output/diagnostics/paper_cohort_sample_ids.csv",
            )
        )
    )
    allow_disk = source in {PaperCohortSource.AUTO, PaperCohortSource.DISK_ONLY}
    if allow_disk and resolved_path.exists():
        try:
            df = pd.read_csv(resolved_path)
            if "sample_id" in df.columns:
                ids = pd.to_numeric(df["sample_id"], errors="coerce").dropna().astype(int)
                return set(ids.tolist())
        except Exception:
            if source == PaperCohortSource.DISK_ONLY:
                return set()
    if source == PaperCohortSource.DISK_ONLY:
        return set()
    if "sample_id" not in samples_df.columns:
        return set()
    ids = pd.to_numeric(samples_df["sample_id"], errors="coerce").dropna().astype(int)
    return set(ids.tolist())


def _copy_confusion_matrix_artifact(
    source_path: str | None,
    run_id: str,
    experiment: str,
    model_name: str,
    *,
    label_target: str | None = None,
) -> str | None:
    """Copy confusion matrix to a run/experiment-specific filename to avoid overwrite."""
    if not source_path:
        return None
    src = Path(str(source_path))
    if not src.exists():
        return source_path
    # If source is already run-scoped (Phase A), reuse it directly.
    run_scoped_token = str(Path("runs") / run_id).replace("\\", "/").lower()
    if run_scoped_token in str(src).replace("\\", "/").lower():
        return str(src)
    rr = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if rr:
        out_dir = Path(rr) / "conf_matrices"
    else:
        out_dir = Path(app_config.DEFAULT_OUTPUT_DIR) / "runs" / run_id / "conf_matrices"
    out_dir.mkdir(parents=True, exist_ok=True)
    exp_slug = f"{experiment}__lt_{label_target}" if label_target else experiment
    dst = out_dir / f"confusion_matrix_{run_id}__{exp_slug}__{model_name}.png"
    try:
        shutil.copyfile(src, dst)
        return str(dst)
    except Exception:
        return source_path


def _collect_experiment_rows(
    experiment: str,
    results: dict[str, dict],
    run_id: str,
    *,
    label_target: str = "family_canonical_default",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows: list[dict[str, Any]] = []
    per_family_rows: list[dict[str, Any]] = []

    for model_name, result in sorted(results.items()):
        evaluation = result.get("evaluation", {}) if isinstance(result, dict) else {}
        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        class_report = metadata.get("classification_report", {}) if isinstance(metadata, dict) else {}
        idx = getattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", None)
        row_ledger: dict[str, Any] = {}
        if isinstance(idx, dict):
            row_ledger = dict(
                idx.get((str(run_id), str(experiment), str(label_target), str(model_name))) or {}
            )
        mdl = result.get("model")
        fit_h = ""
        if mdl is not None and hasattr(mdl, "feature_names_in_"):
            fit_h = hash_payload(sorted(str(x) for x in mdl.feature_names_in_))
        cm_path_raw = _copy_confusion_matrix_artifact(
            source_path=evaluation.get("confusion_matrix_path"),
            run_id=run_id,
            experiment=experiment,
            model_name=model_name,
            label_target=None if label_target == "family_canonical_default" else label_target,
        )
        cm_p = Path(cm_path_raw) if cm_path_raw else None
        matrix_retained = bool(cm_p is not None and cm_p.is_file())
        matrix_status = "materialized" if matrix_retained else ("missing" if not cm_path_raw else "pruned_or_missing")
        summary_rows.append(
            {
                "experiment": experiment,
                "label_target": label_target,
                "model": model_name,
                "accuracy": evaluation.get("accuracy"),
                "weighted_f1_score": evaluation.get("f1_score"),
                "macro_f1_score": evaluation.get("macro_f1_score"),
                "macro_precision": evaluation.get("macro_precision"),
                "macro_recall": evaluation.get("macro_recall"),
                "samples_tested": evaluation.get("samples_tested"),
                "split_hash": row_ledger.get("split_hash"),
                "split_ledger_path": row_ledger.get("split_audit_path"),
                "feature_column_hash": fit_h,
                "confusion_matrix_path": cm_path_raw,
                "matrix_retained": int(matrix_retained),
                "matrix_path_status": matrix_status,
            }
        )

        if isinstance(class_report, dict):
            for family, metrics in class_report.items():
                if not isinstance(metrics, dict):
                    continue
                if family in {"accuracy", "macro avg", "weighted avg"}:
                    continue
                per_family_rows.append(
                    {
                        "experiment": experiment,
                        "label_target": label_target,
                        "model": model_name,
                        "family": str(family),
                        "precision": metrics.get("precision"),
                        "recall": metrics.get("recall"),
                        "f1_score": metrics.get("f1-score"),
                        "support": metrics.get("support"),
                    }
                )
    return summary_rows, per_family_rows


def _ablation_label_target_stats(
    samples_label_basis: pd.DataFrame,
    label_targets: list[tuple[str, str | None]],
) -> list[dict[str, Any]]:
    """Per ablation label target: class cardinality and support spread (training universe)."""
    out: list[dict[str, Any]] = []
    for slug, forced_col in label_targets:
        col = forced_col
        if slug == "family_canonical_default":
            col = "family_canonical"
        if not col or col not in samples_label_basis.columns:
            continue
        ser = samples_label_basis[col].dropna()
        if ser.empty:
            continue
        vc = ser.astype(str).str.strip().value_counts()
        out.append(
            {
                "label_target": slug,
                "column": col,
                "class_count": int(vc.shape[0]),
                "min_class_support": int(vc.min()),
                "max_class_support": int(vc.max()),
            }
        )
    return out


def run_ablation_experiments(
    samples_df: pd.DataFrame,
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    permission_features_df: pd.DataFrame | None,
    model_list: list[str] | None,
    run_id: str,
    pipeline_results: dict[str, Any] | None = None,
    manifest_context: dict[str, Any] | None = None,
) -> list[str]:
    """Run methodology ablations and export summary artifacts."""
    artifact_paths: list[str] = []
    ablation_model_override = getattr(app_config, "ABLATION_MODEL_LIST", None)
    if isinstance(ablation_model_override, list) and len(ablation_model_override) > 0:
        selected_models = [str(m).strip() for m in ablation_model_override if str(m).strip()]
    else:
        selected_models = list(model_list or []) or []
    if not selected_models:
        du.print_warning("[ABLATION] No models resolved for ablations (check model_list / ablation_model_list).")
        return artifact_paths
    ablation_cv_enabled = bool(getattr(app_config, "ENABLE_ABLATION_CROSS_VALIDATION", False))
    ablation_save_models = bool(getattr(app_config, "ENABLE_ABLATION_MODEL_EXPORT", False))
    summary_rows: list[dict[str, Any]] = []
    per_family_rows: list[dict[str, Any]] = []
    skipped_experiments: list[dict[str, str]] = []
    skipped_label_target_runs: list[dict[str, str]] = []

    reindex_zero_fill = bool(getattr(app_config, "ABLATION_COHORT_REINDEX_ZERO_FILL", True))
    strict_evidence = bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))
    paper_mode = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
    if (strict_evidence or paper_mode) and not reindex_zero_fill:
        du.print_error(
            "[ABLATION] Evidence/paper mode requires ABLATION_COHORT_REINDEX_ZERO_FILL=True "
            "so ablations do not mix row-drop effects with feature ablations."
        )
        return artifact_paths

    base_ids = _load_paper_cohort_sample_ids(samples_df)
    if not base_ids:
        du.print_warning("[ABLATION] Empty frozen cohort — skipping ablations.")
        return artifact_paths

    frozen_sorted = sorted(base_ids)

    if not ml_console.is_minimal():
        from obsidiandroid.evaluation.ml_terminal_presentation import print_ablation_experiments_header

        headline_vendor_k = getattr(
            app_config,
            "RUNTIME_EFFECTIVE_TOP_K",
            getattr(app_config, "RUNTIME_K_REQUESTED", "—"),
        )
        ablation_vendor_k = safe_int_config_value(
            getattr(app_config, "FEATURE_TOP_K", 8),
            default=8,
        )
        print_ablation_experiments_header(
            cohort_n=len(base_ids),
            headline_selected_vendors=headline_vendor_k,
            ablation_requested_top_k=ablation_vendor_k,
        )

    if not ml_console.is_minimal() and ml_console.is_compact() and not ml_console.is_debug():
        du.print_info("Building ablation feature sets...")

    experiment_matrices_raw: dict[str, pd.DataFrame] = {}
    previous_feature_build_active = bool(
        getattr(app_config, "RUNTIME_ABLATION_FEATURE_BUILD_ACTIVE", False)
    )
    setattr(app_config, "RUNTIME_ABLATION_FEATURE_BUILD_ACTIVE", True)
    try:
        builders = _build_experiment_matrix_dict(
            weights_df,
            parsed_data,
            permission_features_df,
            pipeline_results,
            cohort_sample_ids=frozen_sorted,
        )
        experiments = [
            (name, builders[name])
            for name in ABLATION_EXPERIMENT_ORDER
            if name in builders and callable(builders[name])
        ]
        for experiment_name, builder in experiments:
            try:
                feature_df = builder()
                if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
                    empty_reason = "empty_feature_matrix"
                    empty_detail = "Builder returned a non-DataFrame or empty feature matrix."
                    if isinstance(feature_df, pd.DataFrame):
                        declared_reason = str(feature_df.attrs.get("ablation_empty_reason", "") or "").strip()
                        if declared_reason:
                            empty_reason = declared_reason
                            empty_detail = (
                                "This ablation removed every retained predictive field "
                                "under its declared semantic exclusion."
                            )
                    skipped_experiments.append(
                        {
                            "feature_set": str(experiment_name),
                            "reason": empty_reason,
                            "detail": empty_detail,
                        }
                    )
                    if ml_console.is_debug():
                        du.print_warning(f"[ABLATION] Skipping '{experiment_name}' due to empty feature matrix.")
                    continue
                experiment_matrices_raw[experiment_name] = feature_df
            except Exception as exc:
                skipped_experiments.append(
                    {
                        "feature_set": str(experiment_name),
                        "reason": "build_failed",
                        "detail": str(exc),
                    }
                )
                if ml_console.is_debug():
                    du.print_warning(f"[ABLATION] '{experiment_name}' failed during build: {exc}")
    finally:
        setattr(app_config, "RUNTIME_ABLATION_FEATURE_BUILD_ACTIVE", previous_feature_build_active)

    if not experiment_matrices_raw:
        return artifact_paths

    gap_table_rows: list[dict[str, Any]] = []
    missing_long_rows: list[dict[str, Any]] = []
    for exp_name, raw_df in experiment_matrices_raw.items():
        raw_ids = _extract_feature_sample_ids(raw_df)
        missing_ct = len(set(base_ids) - raw_ids)
        gap_table_rows.append(
            {
                "feature_set": exp_name,
                "expected_ids": len(base_ids),
                "raw_matrix_ids": len(raw_ids),
                "missing_vs_expected": missing_ct,
                "final_aligned_ids": len(frozen_sorted) if reindex_zero_fill else None,
                "status": "reindex_zero_fill" if reindex_zero_fill else "raw_matrix_only",
            }
        )
        for sid in sorted(set(base_ids) - raw_ids):
            missing_long_rows.append({"feature_set": exp_name, "sample_id": sid})

    missing_df = pd.DataFrame(missing_long_rows) if missing_long_rows else pd.DataFrame()

    experiment_matrices: dict[str, pd.DataFrame] = {}
    if reindex_zero_fill:
        if ml_console.is_debug():
            du.print_info(
                "[ABLATION] Reindexing all feature sets to frozen cohort with zero-fill "
                f"({len(frozen_sorted)} sample_ids)."
            )
        for exp_name, raw_df in experiment_matrices_raw.items():
            reindexed = reindex_ablation_features_to_frozen_ids(raw_df, frozen_sorted)
            if reindexed.shape[1] == 0:
                skipped_experiments.append(
                    {
                        "feature_set": str(exp_name),
                        "reason": "zero_columns_after_reindex",
                        "detail": "Feature matrix retained no columns after frozen-cohort reindex.",
                    }
                )
                if ml_console.is_debug():
                    du.print_warning(f"[ABLATION] '{exp_name}' has zero columns after reindex — skipping.")
                continue
            if not _has_variable_predictive_column(reindexed):
                skipped_experiments.append(
                    {
                        "feature_set": str(exp_name),
                        "reason": "no_variable_feature_columns",
                        "detail": (
                            "All predictive columns are constant on the frozen cohort; "
                            "skipping futile per-model training."
                        ),
                    }
                )
                du.print_warning(
                    f"[ABLATION] '{exp_name}' has no variable predictive columns on the frozen cohort — skipping."
                )
                continue
            experiment_matrices[exp_name] = reindexed
        for exp_name, df in list(experiment_matrices.items()):
            idx_set = set(pd.to_numeric(df.index, errors="coerce").dropna().astype(int).tolist())
            if idx_set != set(frozen_sorted) or len(df) != len(frozen_sorted):
                msg = (
                    f"[ABLATION] Post-reindex index mismatch for '{exp_name}': "
                    f"rows={len(df)} expected={len(frozen_sorted)}."
                )
                if strict_evidence or paper_mode:
                    du.print_error(msg)
                    return artifact_paths
                du.print_warning(msg)
        common_ids = set(frozen_sorted)
    else:
        experiment_matrices = dict(experiment_matrices_raw)
        common_ids = set(base_ids)
        for df in experiment_matrices.values():
            common_ids &= _extract_feature_sample_ids(df)
        require_frozen_universe = bool(getattr(app_config, "ABLATION_REQUIRE_FROZEN_UNIVERSE", True))
        if require_frozen_universe and common_ids != base_ids:
            mismatch_count = max(0, len(base_ids) - len(common_ids))
            base_count = max(1, len(base_ids))
            mismatch_ratio = mismatch_count / base_count
            allowed_ratio = safe_float_config_value(
                getattr(app_config, "ABLATION_MAX_MISMATCH_RATIO", 0.01),
                default=0.01,
            )
            if mismatch_ratio > allowed_ratio:
                du.print_error(
                    "[ABLATION] Frozen cohort mismatch detected. "
                    f"base_ids={len(base_ids)} common_ids={len(common_ids)} "
                    f"mismatch={mismatch_count} ({mismatch_ratio:.2%}). "
                    "Enable ABLATION_COHORT_REINDEX_ZERO_FILL=True or raise ABLATION_MAX_MISMATCH_RATIO."
                )
                return artifact_paths
            du.print_warning(
                "[ABLATION] Minor frozen-cohort mismatch tolerated. "
                f"base_ids={len(base_ids)} common_ids={len(common_ids)} "
                f"mismatch={mismatch_count} ({mismatch_ratio:.2%})"
            )
        if not common_ids:
            du.print_warning("[ABLATION] No common sample_id universe across experiments.")
            return artifact_paths

    from obsidiandroid.evaluation.ml_terminal_presentation import print_ablation_feature_sets_built

    feature_set_rows = _build_ablation_feature_set_summary_rows(
        experiment_order=list(ABLATION_EXPERIMENT_ORDER),
        built_matrices=experiment_matrices,
        skipped_experiments=skipped_experiments,
    )
    built_ok = sum(1 for row in feature_set_rows if str(row.get("status", "")).upper() == "OK")
    skipped_count = sum(1 for row in feature_set_rows if str(row.get("status", "")).upper() == "SKIPPED")
    print_ablation_feature_sets_built(
        rows=feature_set_rows,
        built_ok=built_ok,
        built_total=len(feature_set_rows),
        skipped_count=skipped_count,
    )

    for row in gap_table_rows:
        row["final_aligned_ids"] = len(common_ids)
        row["input_label_sample_ids"] = len(base_ids)
        if reindex_zero_fill:
            row["status"] = "OK"

    gap_summary_payload = {
        "ablation_cohort_reindex_zero_fill": reindex_zero_fill,
        "strict_evidence_or_paper_mode": bool(strict_evidence or paper_mode),
        "expected_frozen_cohort_size": len(base_ids),
        "final_training_universe_size": len(common_ids),
        "train_test_split_cache_scoping": (
            "Per-run train/test splits are cached under a key that hashes the feature index, "
            "encoded label vector, test_size, random_state, and split policy — different ablation "
            "label targets therefore do not reuse each other's y assignments."
        ),
        "experiment_matrix_row_counts": [
            {"feature_set": row.get("feature_set"), "raw_matrix_ids": row.get("raw_matrix_ids")}
            for row in gap_table_rows
        ],
        "skipped_experiments": list(skipped_experiments),
    }
    if isinstance(manifest_context, dict):
        manifest_context["_ablation_cohort_gap_summary"] = gap_summary_payload
    json_p, md_p, csv_p = ablation_cohort_diagnostics.write_ablation_cohort_gap_artifacts(
        diagnostics_dir=_diagnostics_dir(),
        run_id=run_id,
        gap_table_rows=gap_table_rows,
        summary=gap_summary_payload,
        missing_ids_long=missing_df if not missing_df.empty else None,
    )
    artifact_paths.append(str(json_p))
    artifact_paths.append(str(md_p))
    if csv_p is not None:
        artifact_paths.append(str(csv_p))

    _print_ablation_cohort_integrity_table(gap_table_rows)

    samples_work = samples_df.copy()
    samples_work["sample_id"] = pd.to_numeric(samples_work["sample_id"], errors="coerce")
    samples_work = samples_work[samples_work["sample_id"].isin(common_ids)].copy()
    samples_label_basis = samples_work.copy()
    if {"family_canonical", "type_slug"} <= set(samples_label_basis.columns):
        samples_label_basis["family_within_type"] = (
            samples_label_basis["type_slug"].fillna("unknown").astype(str).str.strip()
            + "::"
            + samples_label_basis["family_canonical"].fillna("unknown").astype(str).str.strip()
        )

    label_targets: list[tuple[str, str | None]] = []
    has_family_id = "family_id" in samples_label_basis.columns
    if has_family_id:
        label_targets.append(("family_id", "family_id"))
    else:
        label_targets.append(("family_canonical_default", None))
    if bool(getattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", True)):
        if has_family_id:
            label_targets.append(("family_canonical_default", None))
        if "type_slug" in samples_label_basis.columns:
            label_targets.append(("type_slug", "type_slug"))
        if "family_within_type" in samples_label_basis.columns:
            label_targets.append(("family_within_type", "family_within_type"))

    label_stats_snapshot = _ablation_label_target_stats(samples_label_basis, label_targets)
    if isinstance(manifest_context, dict):
        manifest_context["_ablation_label_target_stats"] = label_stats_snapshot

    planned_combo_count = len(experiment_matrices) * len(label_targets)
    planned_model_fit_upper_bound = planned_combo_count * len(selected_models)
    du.print_info(
        "[ABLATION] Plan: "
        f"{len(experiment_matrices)} feature set(s) × {len(label_targets)} label target(s) "
        f"× {len(selected_models)} model(s) = up to {planned_model_fit_upper_bound} fits."
    )

    previous_cv = bool(getattr(app_config, "ENABLE_CROSS_VALIDATION", False))
    previous_cv_rebalance = bool(getattr(app_config, "ENABLE_CV_REBALANCING", False))
    previous_quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    previous_label_adjacent_allowed = bool(
        getattr(app_config, "RUNTIME_ABLATION_ALLOW_LABEL_ADJACENT_FEATURES", False)
    )
    if not ablation_cv_enabled:
        setattr(app_config, "ENABLE_CROSS_VALIDATION", False)
        setattr(app_config, "ENABLE_CV_REBALANCING", False)
    setattr(app_config, "RUNTIME_QUIET_TRAINING", True)
    setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True)
    setattr(app_config, "RUNTIME_ABLATION_PROGRESS_ROWS", [])
    setattr(app_config, "RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS", [])
    setattr(app_config, "RUNTIME_ABLATION_AUTHORITY_NOTE_EMITTED", False)
    setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", {})

    audit_cols = [
        "feature_set",
        "model",
        "fit_column_count",
        "fit_feature_column_hash",
        "predict_column_count",
        "missing_at_predict_count",
        "extra_at_predict_count",
        "status",
    ]

    schema_audit_snapshot: list[dict[str, Any]] = []
    ablation_grid_exc: BaseException | None = None
    progress_records: list[dict[str, Any]] = []
    progress_path = _write_ablation_progress_snapshot(
        diagnostics_dir=_diagnostics_dir(),
        run_id=run_id,
        total_combo_count=planned_combo_count,
        current_combo_id="",
        combo_records=progress_records,
        summary_row_count=0,
        grid_status="running",
    )
    artifact_paths.append(str(progress_path))
    try:
        with pipeline_core._suppress_known_sklearn_parallel_warning():
            for experiment_name, feature_df in experiment_matrices.items():
                for label_slug, forced_col in label_targets:
                    combo_id = f"{experiment_name}__lt_{label_slug}"
                    combo_status = "running"
                    combo_detail = ""
                    combo_rows_before = len(summary_rows)
                    _write_ablation_progress_snapshot(
                        diagnostics_dir=_diagnostics_dir(),
                        run_id=run_id,
                        total_combo_count=planned_combo_count,
                        current_combo_id=combo_id,
                        combo_records=progress_records,
                        summary_row_count=len(summary_rows),
                        grid_status="running",
                    )
                    try:
                        setattr(app_config, "RUNTIME_ABLATION_FEATURE_SET_NAME", experiment_name)
                        setattr(app_config, "RUNTIME_ABLATION_LABEL_TARGET_SLUG", label_slug)
                        setattr(app_config, "RUNTIME_EXPERIMENT_ID", combo_id)
                        setattr(
                            app_config,
                            "RUNTIME_ABLATION_ALLOW_LABEL_ADJACENT_FEATURES",
                            experiment_name in _LABEL_ADJACENT_ABLATION_EXPERIMENTS,
                        )
                        work_df = feature_df.copy()
                        if not reindex_zero_fill:
                            if "sample_id" in work_df.columns:
                                work_df["sample_id"] = pd.to_numeric(
                                    work_df["sample_id"], errors="coerce"
                                )
                                work_df = work_df[work_df["sample_id"].isin(common_ids)].copy()
                            else:
                                idx_series = pd.Series(
                                    pd.to_numeric(pd.Index(work_df.index), errors="coerce"),
                                    index=work_df.index,
                                )
                                work_df = work_df.loc[idx_series.isin(common_ids)].copy()
                        if work_df.empty:
                            combo_status = "skipped"
                            combo_detail = "empty_filtered_feature_matrix"
                            skipped_label_target_runs.append(
                                {
                                    "feature_set": str(experiment_name),
                                    "label_target": str(label_slug),
                                    "reason": "empty_filtered_feature_matrix",
                                    "detail": "Filtered feature matrix became empty before training.",
                                }
                            )
                            if ml_console.is_debug():
                                du.print_warning(
                                    f"[ABLATION] Skipping '{experiment_name}'/'{label_slug}' "
                                    "due to empty filtered feature matrix."
                                )
                            continue
                        x_train, y_train = _prepare_training_inputs(
                            work_df,
                            samples_label_basis,
                            forced_label_column=forced_col,
                        )
                        if x_train is None or y_train is None or x_train.empty:
                            combo_status = "skipped"
                            combo_detail = "alignment_failure"
                            skipped_label_target_runs.append(
                                {
                                    "feature_set": str(experiment_name),
                                    "label_target": str(label_slug),
                                    "reason": "alignment_failure",
                                    "detail": "Feature/label alignment failed or produced an empty training matrix.",
                                }
                            )
                            if ml_console.is_debug():
                                du.print_warning(
                                    f"[ABLATION] Skipping '{experiment_name}'/'{label_slug}' due to alignment failure."
                                )
                            continue
                        results, skipped_models = pipeline_core.train_models(
                            x_train,
                            y_train,
                            models=selected_models or None,
                            save_model=ablation_save_models,
                        )
                        if not results:
                            combo_status = "skipped"
                            combo_detail = "no_valid_model_results"
                            skipped_label_target_runs.append(
                                {
                                    "feature_set": str(experiment_name),
                                    "label_target": str(label_slug),
                                    "reason": "no_valid_model_results",
                                    "detail": (
                                        "No valid model result was returned for this feature/label combination"
                                        + (
                                            f"; skipped_models={','.join(map(str, skipped_models))}."
                                            if skipped_models
                                            else "."
                                        )
                                    ),
                                }
                            )
                            du.print_warning(
                                f"[ABLATION] '{experiment_name}'/'{label_slug}' produced no valid model results — "
                                "recorded as skipped."
                            )
                            continue
                        _print_ablation_combo_summary(experiment_name, label_slug, results)
                        rows, family_rows = _collect_experiment_rows(
                            experiment_name,
                            results,
                            run_id=run_id,
                            label_target=label_slug,
                        )
                        summary_rows.extend(rows)
                        per_family_rows.extend(family_rows)
                        combo_status = "complete"
                        combo_detail = f"model_rows={len(rows)}"
                    except Exception as exc:
                        combo_status = "failed"
                        combo_detail = str(exc)
                        skipped_label_target_runs.append(
                            {
                                "feature_set": str(experiment_name),
                                "label_target": str(label_slug),
                                "reason": "combo_failed",
                                "detail": str(exc),
                            }
                        )
                        if ml_console.is_debug():
                            du.print_warning(f"[ABLATION] '{experiment_name}'/'{label_slug}' failed: {exc}")
                    finally:
                        if combo_status == "running":
                            combo_status = "interrupted_or_aborted"
                        progress_records.append(
                            {
                                "combo_id": combo_id,
                                "feature_set": str(experiment_name),
                                "label_target": str(label_slug),
                                "status": combo_status,
                                "detail": combo_detail,
                                "model_rows_written": len(summary_rows) - combo_rows_before,
                            }
                        )
                        _write_ablation_progress_snapshot(
                            diagnostics_dir=_diagnostics_dir(),
                            run_id=run_id,
                            total_combo_count=planned_combo_count,
                            current_combo_id="",
                            combo_records=progress_records,
                            summary_row_count=len(summary_rows),
                            grid_status="running",
                        )
                        _print_ablation_combo_progress(
                            completed=len(progress_records),
                            total=planned_combo_count,
                            experiment_name=experiment_name,
                            label_slug=label_slug,
                            status=combo_status,
                            detail=combo_detail,
                        )
                        setattr(app_config, "RUNTIME_EXPERIMENT_ID", "")
                        setattr(app_config, "RUNTIME_ABLATION_FEATURE_SET_NAME", "")
                        setattr(app_config, "RUNTIME_ABLATION_ALLOW_LABEL_ADJACENT_FEATURES", False)
    except BaseException as exc:
        ablation_grid_exc = exc
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            du.print_warning(
                "[ABLATION] Interrupt/SystemExit inside ablation grid — schema audit "
                "and partial summary (if any) will still be flushed."
            )
        else:
            du.print_warning(f"[ABLATION] Ablation grid aborted by {type(exc).__name__}: {exc}")
    finally:
        terminal_progress_status = (
            "complete"
            if ablation_grid_exc is None
            else "interrupted"
            if isinstance(ablation_grid_exc, (KeyboardInterrupt, SystemExit))
            else "failed"
        )
        _write_ablation_progress_snapshot(
            diagnostics_dir=_diagnostics_dir(),
            run_id=run_id,
            total_combo_count=planned_combo_count,
            current_combo_id="",
            combo_records=progress_records,
            summary_row_count=len(summary_rows),
            grid_status=terminal_progress_status,
        )
        raw_audit = getattr(app_config, "RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS", None)
        if isinstance(raw_audit, list):
            schema_audit_snapshot = list(raw_audit)
        setattr(app_config, "ENABLE_CROSS_VALIDATION", previous_cv)
        setattr(app_config, "ENABLE_CV_REBALANCING", previous_cv_rebalance)
        setattr(app_config, "RUNTIME_QUIET_TRAINING", previous_quiet)
        setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)
        setattr(app_config, "RUNTIME_ABLATION_PROGRESS_ROWS", [])
        setattr(app_config, "RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS", [])
        setattr(app_config, "RUNTIME_ABLATION_AUTHORITY_NOTE_EMITTED", False)
        setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", None)
        setattr(app_config, "RUNTIME_ABLATION_LABEL_TARGET_SLUG", "")
        setattr(app_config, "RUNTIME_ABLATION_FEATURE_SET_NAME", "")
        setattr(
            app_config,
            "RUNTIME_ABLATION_ALLOW_LABEL_ADJACENT_FEATURES",
            previous_label_adjacent_allowed,
        )

    audit_df = (
        pd.DataFrame(schema_audit_snapshot)
        if schema_audit_snapshot
        else pd.DataFrame(columns=audit_cols)
    )
    if not audit_df.empty:
        audit_df = audit_df.reindex(columns=audit_cols)
    else:
        audit_df = pd.DataFrame(columns=audit_cols)
    audit_path = _diagnostics_dir() / "ablation_feature_schema_audit.csv"
    audit_df.to_csv(audit_path, index=False)
    artifact_paths.append(str(audit_path))
    du.print_debug(f"[ABLATION] Feature schema audit: {audit_path.name}")

    out_dir = _diagnostics_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ablation_run = str(getattr(app_config, "RUNTIME_RUN_ID", run_id) or run_id)

    grid_status = "complete"
    if ablation_grid_exc is not None:
        grid_status = "interrupted" if isinstance(ablation_grid_exc, (KeyboardInterrupt, SystemExit)) else "failed"
    outcome_payload: dict[str, Any] = {
        "run_id": ablation_run,
        "ablation_grid_status": grid_status,
        "exception_type": type(ablation_grid_exc).__name__ if ablation_grid_exc else "",
        "exception_message": str(ablation_grid_exc) if ablation_grid_exc else "",
        "summary_row_count": len(summary_rows),
        "trainable_experiments": len(experiment_matrices),
        "planned_combo_count": planned_combo_count,
        "planned_model_fit_upper_bound": planned_model_fit_upper_bound,
        "completed_combo_count": len(progress_records),
        "skipped_experiment_count": len(skipped_experiments),
        "skipped_experiments": list(skipped_experiments),
        "skipped_label_target_run_count": len(skipped_label_target_runs),
        "skipped_label_target_runs": list(skipped_label_target_runs),
        "models": list(selected_models),
    }
    if isinstance(manifest_context, dict):
        manifest_context["_ablation_skipped_experiments"] = list(skipped_experiments)
        manifest_context["_ablation_skipped_label_target_runs"] = list(skipped_label_target_runs)
    outcome_path = out_dir / f"ablation_run_outcome_{ablation_run}.json"
    outcome_path.write_text(json.dumps(outcome_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_paths.append(str(outcome_path))

    if not summary_rows:
        if ablation_grid_exc is not None:
            du.print_warning("[ABLATION] No summary rows exported before abort (see ablation_run_outcome_*.json).")
            raise ablation_grid_exc
        return artifact_paths

    summary_df = pd.DataFrame(summary_rows)
    summary_df = _apply_leakage_delta(summary_df)
    summary_df = _apply_full_fused_delta(summary_df)
    per_family_df = pd.DataFrame(per_family_rows)
    sum_csv = summary_df.to_csv(index=False)

    summary_run_basename = f"ablation_summary_{ablation_run}.csv"
    global_latest_name = "ablation_summary.latest.csv"
    if ablation_grid_exc is not None:
        summary_run_basename = f"ablation_summary_partial_{ablation_run}.csv"
        # Do not overwrite a complete global latest snapshot with interrupted grid output.
        global_latest_name = "ablation_summary_partial.latest.csv"

    summary_mirror = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=summary_run_basename,
        csv_text=sum_csv,
        global_latest_name=global_latest_name,
    )
    summary_path = summary_mirror[0]

    summary_status_obs = "complete"
    if ablation_grid_exc is not None:
        summary_status_obs = "partial_before_abort"
        du.print_warning(
            f"[ABLATION] Partial methodology summary written ({summary_path}). "
            "Evidence runs should rerun until ablation_grid_status=complete in ablation_run_outcome_*.json."
        )

    _print_ablation_terminal_summary(summary_df)
    if not per_family_df.empty:
        pf_basename = f"ablation_per_family_{ablation_run}.csv"
        pf_latest = "ablation_per_family.latest.csv"
        if ablation_grid_exc is not None:
            pf_basename = f"ablation_per_family_partial_{ablation_run}.csv"
            pf_latest = "ablation_per_family_partial.latest.csv"
        pf_csv = per_family_df.to_csv(index=False)
        pf_mirror = oh.mirror_csv_text_run_then_global(
            diagnostics_dir=out_dir,
            run_filename=pf_basename,
            csv_text=pf_csv,
            global_latest_name=pf_latest,
        )
        artifact_paths.append(str(pf_mirror[0]))
    artifact_paths.extend([str(summary_path)])
    du.print_info(f"[ABLATION] Summary CSV: {summary_path.name} (see diagnostics/)")
    if isinstance(manifest_context, dict):
        from obsidiandroid.observability.pipeline_observability import api as obs_api

        obs_api.record_ablation_summary(
            manifest_context,
            frozen_cohort_ids=len(base_ids),
            training_universe_ids=len(common_ids),
            experiments_built=len(experiment_matrices),
            label_target_stats=label_stats_snapshot,
            summary_csv_path=str(summary_path),
            summary_status=summary_status_obs,
            skipped_experiments=skipped_experiments,
            skipped_label_target_runs=skipped_label_target_runs,
        )
    if ablation_grid_exc is not None:
        raise ablation_grid_exc
    return artifact_paths


def _build_permissions_only_matrix(permission_features_df: pd.DataFrame | None) -> pd.DataFrame:
    if not isinstance(permission_features_df, pd.DataFrame) or permission_features_df.empty:
        return pd.DataFrame()
    if "sample_id" not in permission_features_df.columns:
        return pd.DataFrame()
    matrix = permission_features_df.drop_duplicates("sample_id").set_index("sample_id").copy()
    for col in matrix.columns:
        matrix[col] = pd.to_numeric(matrix[col], errors="coerce").fillna(0)
    return matrix


def _apply_leakage_delta(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty or "macro_f1_score" not in summary_df.columns:
        return summary_df
    out = summary_df.copy()
    out["leakage_sensitivity_delta"] = None
    out["vendor_leakage_delta_vs_vendor_safe"] = None
    out["vendor_leakage_delta_vs_vendor_full"] = None

    def _baseline_frame(frame: pd.DataFrame) -> pd.DataFrame:
        baseline = frame[frame["experiment"] == "vendor_no_parsed_family"][["model", "macro_f1_score"]]
        if baseline.empty:
            baseline = frame[frame["experiment"] == "vendor_only"][["model", "macro_f1_score"]]
        if baseline.empty:
            baseline = frame[frame["experiment"] == "vendor_full"][["model", "macro_f1_score"]]
        return baseline

    if "label_target" not in out.columns:
        baseline = _baseline_frame(out)
        if not baseline.empty:
            baseline_map = {
                str(row["model"]): float(row["macro_f1_score"])
                for _, row in baseline.iterrows()
                if pd.notna(row["macro_f1_score"])
            }
            for idx, row in out.iterrows():
                model = str(row.get("model", ""))
                macro_f1 = row.get("macro_f1_score")
                if model in baseline_map and pd.notna(macro_f1):
                    delta = round(float(macro_f1) - baseline_map[model], 6)
                    out.at[idx, "leakage_sensitivity_delta"] = delta
                    out.at[idx, "vendor_leakage_delta_vs_vendor_safe"] = delta
                    out.at[idx, "vendor_leakage_delta_vs_vendor_full"] = delta
        return out

    for lt_label in sorted(out["label_target"].dropna().unique()):
        lt_frame = out[out["label_target"] == lt_label]
        baseline = _baseline_frame(lt_frame)
        if baseline.empty:
            continue
        baseline_map = {
            str(row["model"]): float(row["macro_f1_score"])
            for _, row in baseline.iterrows()
            if pd.notna(row["macro_f1_score"])
        }
        for idx, row in out.iterrows():
            if row.get("label_target") != lt_label:
                continue
            model = str(row.get("model", ""))
            macro_f1 = row.get("macro_f1_score")
            if model in baseline_map and pd.notna(macro_f1):
                delta = round(float(macro_f1) - baseline_map[model], 6)
                out.at[idx, "leakage_sensitivity_delta"] = delta
                out.at[idx, "vendor_leakage_delta_vs_vendor_safe"] = delta
                out.at[idx, "vendor_leakage_delta_vs_vendor_full"] = delta
    return out


def _apply_full_fused_delta(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Per row: Macro-F1 minus same-model full_fused baseline (same label target)."""
    if summary_df.empty or "macro_f1_score" not in summary_df.columns:
        return summary_df
    out = summary_df.copy()
    out["delta_vs_full_fused"] = None
    has_lt = "label_target" in out.columns

    def _apply_partition(part: pd.DataFrame) -> None:
        ff = part[part["experiment"] == "full_fused"]
        if ff.empty:
            return
        baseline_map: dict[str, float] = {}
        for _, row in ff.iterrows():
            m = str(row.get("model", ""))
            mf = row.get("macro_f1_score")
            if m and mf is not None and pd.notna(mf):
                baseline_map[m] = float(mf)

        for idx, row in part.iterrows():
            exp = row.get("experiment")
            if exp == "full_fused":
                out.at[idx, "delta_vs_full_fused"] = 0.0
                continue
            model = str(row.get("model", ""))
            macro = row.get("macro_f1_score")
            if model in baseline_map and macro is not None and pd.notna(macro):
                out.at[idx, "delta_vs_full_fused"] = round(float(macro) - baseline_map[model], 6)

    if has_lt:
        for lt_label in sorted(out["label_target"].dropna().unique()):
            sub = out[out["label_target"] == lt_label]
            _apply_partition(sub)
    else:
        _apply_partition(out)
    return out


def _print_ablation_terminal_summary(summary_df: pd.DataFrame) -> None:
    """Operator/research/debug terminal rendering for ablation results."""
    if summary_df.empty or ml_console.is_minimal():
        return
    work = summary_df.copy()
    for col in ("macro_f1_score", "accuracy", "weighted_f1_score", "delta_vs_full_fused"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["macro_f1_score"])
    if work.empty:
        return

    label_targets = (
        list(work["label_target"].dropna().astype(str).unique())
        if "label_target" in work.columns
        else ["family_canonical_default"]
    )
    leaderboard_rows: list[dict[str, Any]] = []
    interpretation_lines: list[str] = []

    def _best_row(frame: pd.DataFrame) -> pd.Series | None:
        if frame.empty:
            return None
        idx = frame["macro_f1_score"].idxmax()
        return frame.loc[idx]

    for label_target in label_targets:
        target_df = (
            work[work["label_target"].astype(str) == str(label_target)].copy()
            if "label_target" in work.columns
            else work.copy()
        )
        overall = _best_row(target_df)
        if overall is None:
            continue
        permission_only = _best_row(target_df[target_df["experiment"].astype(str).isin(_PERMISSION_ONLY_EXPERIMENTS)])
        vendor_safe = _best_row(target_df[target_df["experiment"].astype(str).isin(_VENDOR_SAFE_EXPERIMENTS)])
        full_fused = _best_row(target_df[target_df["experiment"].astype(str) == "full_fused"])
        vendor_parsed = _best_row(target_df[target_df["experiment"].astype(str) == "vendor_full"])
        parsed_gap: float | None = None
        if vendor_parsed is not None and vendor_safe is not None:
            parsed_gap = round(
                float(vendor_parsed["macro_f1_score"]) - float(vendor_safe["macro_f1_score"]),
                4,
            )
        perm_delta: float | None = None
        if permission_only is not None and full_fused is not None:
            perm_delta = round(
                float(permission_only["macro_f1_score"]) - float(full_fused["macro_f1_score"]),
                4,
            )
        leaderboard_rows.append(
            {
                "label_target": str(label_target),
                "best_feature_set": _format_ablation_terminal_label(str(overall["experiment"])),
                "best_model": str(overall.get("model", "")),
                "best_macro_f1": round(float(overall["macro_f1_score"]), 4),
                "permission_only": _format_ablation_score_cell(
                    str(permission_only["experiment"]),
                    str(permission_only.get("model", "")),
                    float(permission_only["macro_f1_score"]),
                )
                if permission_only is not None
                else "—",
                "vendor_safe": _format_ablation_score_cell(
                    str(vendor_safe["experiment"]),
                    str(vendor_safe.get("model", "")),
                    float(vendor_safe["macro_f1_score"]),
                )
                if vendor_safe is not None
                else "—",
                "full_fused": _format_ablation_score_cell(
                    str(full_fused["experiment"]),
                    str(full_fused.get("model", "")),
                    float(full_fused["macro_f1_score"]),
                )
                if full_fused is not None
                else "—",
                "delta_permission_vs_full_fused": round(perm_delta, 4) if perm_delta is not None else None,
                "parsed_family_gap": round(parsed_gap, 4) if parsed_gap is not None else None,
            }
        )

        lt = str(label_target)
        if permission_only is not None:
            interpretation_lines.append(
                "[ABLATION] Permissions carry strong independent family/type signal: "
                f"{lt} best permission-only={float(permission_only['macro_f1_score']):.4f} "
                f"({_format_ablation_terminal_label(str(permission_only['experiment']))})."
            )
        if parsed_gap is not None and parsed_gap > 0:
            interpretation_lines.append(
                "[ABLATION] Parsed vendor family strings are leakage-sensitive: "
                f"{lt} vendor_parsed_full exceeds vendor_without_family_strings by {parsed_gap:.4f} Macro-F1."
            )

    if not leaderboard_rows:
        return

    from obsidiandroid.evaluation.ml_terminal_presentation import (
        print_ablation_interpretation_summary,
        print_ablation_leaderboard_compact,
    )

    leaderboard_df = pd.DataFrame(leaderboard_rows).sort_values(["label_target"], kind="stable")
    if ml_console.is_compact() and not ml_console.is_debug():
        print_ablation_leaderboard_compact(leaderboard_rows)
    else:
        du.print_section("ABLATION LEADERBOARD")
        du.print_table(leaderboard_df, show_index=False)

    print_ablation_interpretation_summary(summary_df)

    by_target = {str(row["label_target"]): row for row in leaderboard_rows}
    type_row = by_target.get("type_slug")
    family_row = by_target.get("family_id") or by_target.get("family_canonical_default")
    if type_row is not None and family_row is not None:
        type_best = float(type_row["best_macro_f1"])
        family_best = float(family_row["best_macro_f1"])
        if type_best > family_best + 1e-4:
            interpretation_lines.append(
                "[ABLATION] type_slug is easier than family_id: "
                f"type_slug best={type_best:.4f} vs family best={family_best:.4f}."
            )
        elif type_best < family_best - 1e-4:
            interpretation_lines.append(
                "[ABLATION] family_id is easier than type_slug: "
                f"family best={family_best:.4f} vs type_slug best={type_best:.4f}."
            )
        else:
            interpretation_lines.append(
                "[ABLATION] type_slug and family_id are comparable on best Macro-F1: "
                f"type_slug best={type_best:.4f}; family best={family_best:.4f}."
            )
    family_within_type_row = by_target.get("family_within_type")
    if family_within_type_row is not None and type_row is not None:
        fwt_best = float(family_within_type_row["best_macro_f1"])
        type_best = float(type_row["best_macro_f1"])
        if fwt_best < type_best - 1e-4:
            interpretation_lines.append(
                "[ABLATION] family_within_type remains harder than type_slug: "
                f"family_within_type best={fwt_best:.4f} vs type_slug best={type_best:.4f}."
            )
        elif fwt_best > type_best + 1e-4:
            interpretation_lines.append(
                "[ABLATION] family_within_type exceeds type_slug on best Macro-F1: "
                f"family_within_type best={fwt_best:.4f} vs type_slug best={type_best:.4f}."
            )
        else:
            interpretation_lines.append(
                "[ABLATION] family_within_type and type_slug are comparable on best Macro-F1: "
                f"family_within_type best={fwt_best:.4f}; type_slug best={type_best:.4f}."
            )

    if ml_console.is_debug():
        seen_lines: set[str] = set()
        for line in interpretation_lines:
            if line in seen_lines:
                continue
            seen_lines.add(line)
            du.print_info(line)

    if not ml_console.is_debug() and not ml_console.is_minimal():
        du.print_info("[ABLATION] Full experiment grid remains in diagnostics CSV/Markdown summaries.")
