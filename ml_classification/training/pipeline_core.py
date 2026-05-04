# Filename: pipeline_core.py
# Purpose : Central controller for training, comparing, and promoting ML models

from __future__ import annotations

import contextlib
import io
import json
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import app_config
from data_inspect import inspect_classification_results as inspector
from ml_classification.ml_utils import (
    distribution_reporter,
    ml_comparator_summary as comparator,
    ml_result_validator,
)
from utils import display_utils as du
from utils import ml_console
from utils import export_manager as em
from utils.logging import get_logger, log_event
from analysis.diagnostics.feature_build_coverage_export import _normalize_sample_ids
from analysis.diagnostics.feature_column_survival_export import (
    export_feature_column_survival_matrix,
    nonzero_counts_for_columns,
)
from analysis.diagnostics.permission_training_survival_audit import (
    export_permission_training_survival_audit,
    perm_prefix_nonzero_stats,
)
from analysis.orchestration.methodology_artifacts import (
    export_feature_contract,
    export_leakage_assessment,
)

from . import data_alignment
from . import pipeline_result_promoter
from . import train_model_executor

# === Constants === #
ALL_SUPPORTED_MODELS = [
    "random_forest",
    "balanced_random_forest",
    "svm",
    "xgboost",
    "logistic_regression",
]
DEFAULT_MODEL_KEY = "xgboost"
PIPELINE_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.ml.pipeline_core",
    "ml",
)


def _prune_low_information_features(features_df: pd.DataFrame) -> pd.DataFrame:
    """Drop no-variance columns to reduce noise and model complexity."""
    if features_df is None or features_df.empty:
        setattr(app_config, "RUNTIME_LOW_INFORMATION_PRUNED_COLUMNS", [])
        return features_df

    low_info_cols = [
        col for col in features_df.columns if features_df[col].nunique(dropna=False) <= 1
    ]
    if not low_info_cols:
        setattr(app_config, "RUNTIME_LOW_INFORMATION_PRUNED_COLUMNS", [])
        return features_df

    setattr(app_config, "RUNTIME_LOW_INFORMATION_PRUNED_COLUMNS", list(low_info_cols))
    du.print_warning(
        f"[FEATURES] Dropping {len(low_info_cols)} low-information column(s) before training."
    )
    du.print_debug(f"[FEATURES] Dropped columns: {low_info_cols}")
    return features_df.drop(columns=low_info_cols, errors="ignore")


def _collect_leakage_pruning_audit(
    features_df: pd.DataFrame,
    labels_df: pd.Series,
) -> list[dict[str, Any]]:
    """Inspect features for likely leakage and return audit rows with reason codes."""
    if features_df is None or features_df.empty:
        return []

    audit_rows: list[dict[str, Any]] = []
    blocked_exact = {
        "sample_id",
        "true_family",
        "predicted_family",
        "classification_label",
        "family_name",
    }
    idx_as_str = features_df.index.map(str)

    for col in features_df.columns:
        col_name = str(col)
        reason = None
        details = ""

        if col_name.lower() in blocked_exact:
            reason = "blocked_exact_name"
            details = "column name matches known identifier or label field"
        else:
            try:
                if features_df[col].map(str).equals(idx_as_str):
                    reason = "matches_sample_id_index"
                    details = "column values match normalized feature index exactly"
            except Exception:
                continue

        if reason is None and bool(
            getattr(app_config, "ENABLE_AGGRESSIVE_LEAKAGE_PRUNING", False)
        ):
            try:
                pairs = pd.DataFrame({"feature_value": features_df[col], "label": labels_df})
                mapping_conflicts = pairs.groupby("feature_value")["label"].nunique(dropna=False)
                if (
                    not mapping_conflicts.empty
                    and mapping_conflicts.max() == 1
                    and pairs["feature_value"].nunique() >= 10
                ):
                    reason = "unique_feature_to_label_mapping"
                    details = (
                        "feature values map to exactly one label across observed rows "
                        f"(unique_values={int(pairs['feature_value'].nunique())})"
                    )
            except Exception:
                continue

        if reason is not None:
            audit_rows.append(
                {
                    "column_name": col_name,
                    "reason_code": reason,
                    "details": details,
                }
            )

    return audit_rows


def _prune_potential_leakage_features(
    features_df: pd.DataFrame,
    labels_df: pd.Series,
) -> pd.DataFrame:
    """Drop columns likely to leak labels or sample identity."""
    if features_df is None or features_df.empty:
        return features_df

    audit_rows = _collect_leakage_pruning_audit(features_df, labels_df)
    setattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", list(audit_rows))
    drop_cols = [row["column_name"] for row in audit_rows]
    if not drop_cols:
        return features_df

    drop_cols = sorted(set(drop_cols))
    du.print_warning(
        f"[FEATURES] Dropping {len(drop_cols)} potential leakage column(s)."
    )
    du.print_debug(f"[FEATURES] Leakage columns: {drop_cols}")
    return features_df.drop(columns=drop_cols, errors="ignore")


def _diagnostics_dir() -> Path:
    """Resolve the diagnostics directory for the current runtime context."""
    return Path(
        str(
            getattr(
                app_config,
                "RUNTIME_DIAGNOSTICS_DIR",
                Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics",
            )
        )
    )


def _index_to_int_sample_ids(index: Any) -> list[int]:
    """Stable sorted unique integer sample ids from a feature matrix index."""
    return sorted(_normalize_sample_ids(index))


def _perm_training_survival_bundle(features_df: pd.DataFrame) -> tuple[dict[str, int], int]:
    """Nonzero permission-bag counts and row count for survival auditing."""
    return (perm_prefix_nonzero_stats(features_df), int(len(features_df)))


def _export_label_name_map(labels_df: pd.Series, diagnostics_dir: Path) -> str | None:
    """Persist the active label-name map for downstream export/reporting stages."""
    label_name_map = getattr(labels_df, "attrs", {}).get("label_name_map", {})
    requires_map = bool(
        isinstance(labels_df, pd.Series)
        and not labels_df.empty
        and labels_df.astype(str).str.strip().str.isdigit().any()
    )
    if not isinstance(label_name_map, dict) or not label_name_map:
        setattr(app_config, "RUNTIME_LABEL_NAME_MAP", {})
        if requires_map and bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
            raise RuntimeError(
                "[LABELS] Missing label_name_map for the current training run."
            )
        return None

    normalized = {
        str(key): str(value).strip()
        for key, value in label_name_map.items()
        if str(key).strip() and str(value).strip()
    }
    setattr(app_config, "RUNTIME_LABEL_NAME_MAP", dict(normalized))
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    out_path = diagnostics_dir / f"label_name_map_{run_id}.json"
    latest_path = diagnostics_dir / "label_name_map.latest.json"
    payload = {
        "run_id": run_id,
        "label_name_map": normalized,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    out_path.write_text(encoded, encoding="utf-8")
    latest_path.write_text(encoded, encoding="utf-8")
    return str(out_path)


def _export_leakage_pruning_audit(diagnostics_dir: Path) -> str | None:
    """Persist detailed leakage-pruning reasons for dropped feature columns."""
    audit_rows = getattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", [])
    if not isinstance(audit_rows, list):
        return None

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    audit_df = pd.DataFrame(audit_rows)
    if audit_df.empty:
        audit_df = pd.DataFrame(columns=["column_name", "reason_code", "details"])
    out_path = diagnostics_dir / f"leakage_pruning_audit_{run_id}.csv"
    latest_path = diagnostics_dir / "leakage_pruning_audit.latest.csv"
    audit_df.to_csv(out_path, index=False)
    audit_df.to_csv(latest_path, index=False)
    setattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT_PATH", str(out_path))
    return str(out_path)


def _get_configured_models(models: Optional[List[str]] = None) -> List[str]:
    """Return the active model list for this run."""
    if models:
        return models
    if getattr(app_config, "ENABLE_BENCHMARK_MODELS", False):
        configured = list(
            getattr(app_config, "BENCHMARK_TRAINING_MODELS", ALL_SUPPORTED_MODELS)
        )
    else:
        configured = list(
            getattr(app_config, "DEFAULT_TRAINING_MODELS", [DEFAULT_MODEL_KEY])
        )

    valid = [m for m in configured if m in ALL_SUPPORTED_MODELS]
    if not valid:
        du.print_warning(
            "[TRAINING] Configured model list was invalid; using default model."
        )
        return [DEFAULT_MODEL_KEY]
    return valid


def align_data(
    features_df: pd.DataFrame,
    samples_df: pd.DataFrame,
    *,
    forced_label_column: str | None = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Align AV feature matrix with supervised labels by sample ID."""
    try:
        log_event(PIPELINE_LOGGER, "align_data_start", event_id="ML_ALIGN_001")
        aligned_features, labels = data_alignment.extract_aligned_labels(
            features_df=features_df,
            samples_df=samples_df,
            drop_low_support=False,
            verbose=True,
            forced_label_column=forced_label_column,
        )
        if labels is not None and not isinstance(labels, pd.Series):
            labels = pd.Series(labels)
        log_event(
            PIPELINE_LOGGER,
            "align_data_complete",
            event_id="ML_ALIGN_002",
            feature_rows=int(len(aligned_features)) if aligned_features is not None else 0,
            label_rows=int(len(labels)) if labels is not None else 0,
        )
        return aligned_features, labels
    except data_alignment.DataAlignmentError as exc:
        du.print_error(f"[PIPELINE] Alignment error: {exc}")
        log_event(
            PIPELINE_LOGGER,
            "align_data_failed",
            event_id="ML_ALIGN_500",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise


def train_models(
    features_df: pd.DataFrame,
    labels_df: pd.Series,
    models: Optional[List[str]] = None,
    save_model: bool = True,
) -> Tuple[Dict[str, dict], List[str]]:
    """Train/evaluate configured models and return results plus skipped model names."""
    results: Dict[str, dict] = {}
    skipped: List[str] = []
    models = _get_configured_models(models)
    log_event(
        PIPELINE_LOGGER,
        "train_models_start",
        event_id="ML_TRAIN_001",
        requested_models=models,
        rows=int(len(features_df)) if isinstance(features_df, pd.DataFrame) else 0,
        feature_count=int(features_df.shape[1]) if isinstance(features_df, pd.DataFrame) else 0,
    )

    for model_name in models:
        quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
        if not quiet and not ml_console.is_minimal():
            du.print_subheader(f"[TRAINING] {model_name.upper()}")

        try:
            result = train_model_executor.train_and_evaluate_model(
                model_type=model_name,
                features_df=features_df,
                labels=labels_df,
                save_model=bool(save_model),
            )

            if not isinstance(result, dict):
                du.print_error(f"[TRAINING] {model_name} result is invalid.")
                skipped.append(model_name)
                log_event(
                    PIPELINE_LOGGER,
                    "train_model_invalid_result",
                    event_id="ML_TRAIN_410",
                    model=model_name,
                )
                continue

            if not ml_result_validator.validate_result_structure(result):
                du.print_warning(
                    f"[TRAINING] {model_name} result failed structure validation."
                )
                skipped.append(model_name)
                log_event(
                    PIPELINE_LOGGER,
                    "train_model_validation_failed",
                    event_id="ML_TRAIN_411",
                    model=model_name,
                )
                continue

            if result.get("label_encoder") is None:
                du.print_error(f"[TRAINING] {model_name} is missing label_encoder.")
                skipped.append(model_name)
                log_event(
                    PIPELINE_LOGGER,
                    "train_model_missing_label_encoder",
                    event_id="ML_TRAIN_412",
                    model=model_name,
                )
                continue

            results[model_name] = result
            log_event(
                PIPELINE_LOGGER,
                "train_model_complete",
                event_id="ML_TRAIN_200",
                model=model_name,
            )

        except Exception as exc:
            du.print_error(
                f"[TRAINING] {model_name} failed: {type(exc).__name__} - {exc}"
            )
            du.print_debug(traceback.format_exc())
            skipped.append(model_name)
            log_event(
                PIPELINE_LOGGER,
                "train_model_failed",
                event_id="ML_TRAIN_500",
                model=model_name,
                error=str(exc),
            )

    log_event(
        PIPELINE_LOGGER,
        "train_models_complete",
        event_id="ML_TRAIN_002",
        succeeded_models=sorted(results.keys()),
        skipped_models=skipped,
    )
    return results, skipped


def summarize_models(results: Dict[str, dict]) -> Optional[str]:
    """Generate/export model comparison summary and return promoted model key."""
    if not results:
        du.print_warning("[SUMMARY] No valid model results to summarize.")
        log_event(PIPELINE_LOGGER, "summarize_models_skipped", event_id="ML_SUMMARY_404")
        return None

    try:
        log_event(PIPELINE_LOGGER, "summarize_models_start", event_id="ML_SUMMARY_001")
        summary_df = comparator.compare_model_performance(results)
        summary_df = _apply_paper_model_summary_policy(summary_df)
        run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
        runtime_diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
        if runtime_diag:
            diagnostics_dir = Path(runtime_diag)
        else:
            diagnostics_dir = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))) / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)

        if bool(getattr(app_config, "ENABLE_MODEL_COMPARISON_CSV_EXPORT", True)):
            csv_path = diagnostics_dir / f"model_comparison_summary_{run_id}.csv"
            summary_df.to_csv(csv_path, index=False)
            du.print_info(f"[SUMMARY] Exported comparison summary CSV to: {csv_path}")

        if bool(getattr(app_config, "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT", False)):
            export_path = OUTPUT_DIR / "model_comparison_summary.xlsx"
            exported_path = em.export_dataframe_to_excel(
                df=summary_df,
                filename=export_path.name,
                sheet_name="Model_Comparison",
                preview_rows=0,
            )
            du.print_info(f"[SUMMARY] Exported comparison summary workbook to: {exported_path}")

        top_model_key = None
        if isinstance(summary_df, pd.DataFrame) and not summary_df.empty:
            top_model_key = str(summary_df.iloc[0]["Model"])

        active_model_key = top_model_key if top_model_key in results else DEFAULT_MODEL_KEY
        active_eval = results.get(active_model_key, {}).get("evaluation", {})
        if active_eval:
            if bool(getattr(app_config, "ML_SHOW_CLASSIFIER_SUMMARY_TERMINAL", False)):
                inspector.generate_classification_summary(
                    accuracy=active_eval.get("accuracy"),
                    report_path=active_eval.get("confusion_matrix_path", "N/A"),
                    model_path="N/A",
                    metadata=active_eval,
                    model_name=active_model_key,
                )
            else:
                # Keep report artifact generation but suppress verbose narrative in terminal.
                with contextlib.redirect_stdout(io.StringIO()):
                    inspector.generate_classification_summary(
                        accuracy=active_eval.get("accuracy"),
                        report_path=active_eval.get("confusion_matrix_path", "N/A"),
                        model_path="N/A",
                        metadata=active_eval,
                        model_name=active_model_key,
                    )
                du.print_info(
                    "[SUMMARY] Classification narrative report written to run diagnostics "
                    "(terminal view suppressed in compact mode)."
                )

        log_event(
            PIPELINE_LOGGER,
            "summarize_models_complete",
            event_id="ML_SUMMARY_200",
            active_model=active_model_key,
            summary_rows=int(len(summary_df)) if isinstance(summary_df, pd.DataFrame) else 0,
        )
        return active_model_key
    except Exception as exc:
        du.print_error(f"[SUMMARY] Failed during model comparison export: {exc}")
        du.print_debug(traceback.format_exc())
        log_event(
            PIPELINE_LOGGER,
            "summarize_models_failed",
            event_id="ML_SUMMARY_500",
            error=str(exc),
        )
        return None


def _apply_paper_model_summary_policy(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Restrict paper-mode model summary to RF/XGB/LR for policy consistency."""
    if not isinstance(summary_df, pd.DataFrame) or summary_df.empty:
        return summary_df
    if not bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
        return summary_df
    if "Model" not in summary_df.columns:
        return summary_df

    keep_models = {"random_forest", "xgboost", "logistic_regression"}
    filtered = summary_df[summary_df["Model"].astype(str).isin(keep_models)].copy()
    if filtered.empty:
        return summary_df
    return filtered.reset_index(drop=True)


def promote_default_model(results: Dict[str, dict], model_key: str = DEFAULT_MODEL_KEY) -> None:
    """Promote one model's outputs for top-level consumption."""
    try:
        log_event(
            PIPELINE_LOGGER,
            "promotion_start",
            event_id="ML_PROMOTE_001",
            model_key=model_key,
        )
        if model_key not in results:
            du.print_warning(
                f"[PROMOTION] Model '{model_key}' not found - skipping promotion."
            )
            log_event(
                PIPELINE_LOGGER,
                "promotion_skipped",
                event_id="ML_PROMOTE_404",
                model_key=model_key,
            )
            return

        pipeline_result_promoter.promote_model_outputs_to_top_level(
            results,
            model_key=model_key,
        )
        du.print_success(f"[PROMOTION] Promoted outputs from model: {model_key}")
        log_event(
            PIPELINE_LOGGER,
            "promotion_complete",
            event_id="ML_PROMOTE_200",
            model_key=model_key,
        )
    except Exception as exc:
        du.print_warning(f"[PROMOTION] Failed during promotion step: {exc}")
        du.print_debug(traceback.format_exc())
        log_event(
            PIPELINE_LOGGER,
            "promotion_failed",
            event_id="ML_PROMOTE_500",
            model_key=model_key,
            error=str(exc),
        )


def run_classifier_pipeline(
    features_df: pd.DataFrame,
    samples_df: pd.DataFrame,
    save_model: bool = True,
    models: Optional[List[str]] = None,
) -> Dict[str, dict]:
    """Run full classifier pipeline: align, filter, train, summarize, promote."""
    du.print_section("ML CLASSIFICATION PIPELINE")
    log_event(
        PIPELINE_LOGGER,
        "classifier_pipeline_start",
        event_id="ML_PIPELINE_001",
        feature_rows=int(len(features_df)) if isinstance(features_df, pd.DataFrame) else 0,
        sample_rows=int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0,
        save_model=bool(save_model),
    )

    cohort_fused_attrs: dict[str, Any] = {}
    if isinstance(features_df, pd.DataFrame) and hasattr(features_df, "attrs"):
        cohort_fused_attrs = dict(features_df.attrs)
    setattr(
        app_config,
        "RUNTIME_FEATURE_NONZERO_COHORT_FUSED",
        nonzero_counts_for_columns(features_df),
    )

    du.print_info("[STEP 1] Aligning features and labels")
    if isinstance(samples_df, pd.DataFrame) and not samples_df.empty:
        split_meta_cols = [
            col
            for col in (
                "sample_id",
                "sha256",
                "family_id",
                "family_name",
                "family_canonical",
                "type_slug",
                "type_slug_expected",
                "effective_first_seen_at_utc",
                "vt_first_submission_at_utc",
                "vt_first_seen_itw_date",
            )
            if col in samples_df.columns
        ]
        if split_meta_cols:
            setattr(
                app_config,
                "RUNTIME_SPLIT_SAMPLE_METADATA",
                samples_df[split_meta_cols].copy(),
            )

    try:
        features_df, labels_df = align_data(features_df, samples_df)
        setattr(
            app_config,
            "RUNTIME_FEATURE_NONZERO_AFTER_ALIGN",
            nonzero_counts_for_columns(features_df),
        )
    except data_alignment.DataAlignmentError as exc:
        du.print_error("[PIPELINE] Alignment failed - aborting.")
        log_event(
            PIPELINE_LOGGER,
            "classifier_pipeline_failed",
            event_id="ML_PIPELINE_500",
            stage="alignment",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {}

    diagnostics_dir = _diagnostics_dir()
    setattr(
        app_config,
        "RUNTIME_ALIGNED_ROWS_BEFORE_LOW_SUPPORT_FILTER",
        int(len(features_df)) if isinstance(features_df, pd.DataFrame) else 0,
    )
    setattr(
        app_config,
        "RUNTIME_ALIGNED_SUPERVISED_SAMPLE_IDS",
        _index_to_int_sample_ids(features_df.index),
    )
    perm_surv_after_align = _perm_training_survival_bundle(features_df)
    perm_surv_after_family = perm_surv_after_align

    try:
        du.print_info("[STEP 2] Family label distribution (pre-training)")
        distribution_reporter.print_family_distribution(
            labels_df,
            label_type="All",
            verbose=app_config.DEBUG_MODE,
        )
    except Exception as exc:
        du.print_warning(f"[PIPELINE] Skipped family distribution report: {exc}")
        log_event(
            PIPELINE_LOGGER,
            "distribution_report_skipped",
            event_id="ML_PIPELINE_210",
            error=str(exc),
        )

    try:
        du.print_info("[STEP 3] Filtering low-support families")
        label_name_map = dict(getattr(labels_df, "attrs", {}).get("label_name_map", {}))
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
        features_df, labels_df, affected, fams = distribution_reporter.apply_min_family_support(
            features_df=features_df,
            labels_df=labels_df,
            min_support=min_support,
            group_label=group_label,
        )
        if label_name_map:
            if group_label:
                filtered_map = {
                    str(key): str(value)
                    for key, value in label_name_map.items()
                }
            else:
                active_keys = {str(value) for value in labels_df.astype(str).unique().tolist()}
                filtered_map = {
                    str(key): str(value)
                    for key, value in label_name_map.items()
                    if str(key) in active_keys
                }
            labels_df.attrs["label_name_map"] = filtered_map
        if fams:
            action = "grouped as 'other'" if group_label else "dropped"
            du.print_info(f"[FILTER] {affected} samples {action} from families: {fams}")
        distribution_reporter.print_family_distribution(
            labels_df,
            label_type="Filtered",
            verbose=app_config.DEBUG_MODE,
        )
        setattr(
            app_config,
            "RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS",
            int(len(features_df)) if isinstance(features_df, pd.DataFrame) else 0,
        )
        setattr(
            app_config,
            "RUNTIME_POST_FAMILY_SUPPORT_TRAINABLE_SAMPLE_IDS",
            _index_to_int_sample_ids(features_df.index),
        )
        setattr(
            app_config,
            "RUNTIME_TRAINING_LABEL_CLASS_COUNT",
            int(pd.Series(labels_df).nunique()),
        )
        perm_surv_after_family = _perm_training_survival_bundle(features_df)
        setattr(
            app_config,
            "RUNTIME_FEATURE_NONZERO_AFTER_FAMILY_SUPPORT",
            nonzero_counts_for_columns(features_df),
        )
    except Exception as exc:
        du.print_warning(f"[PIPELINE] Family support filtering failed: {exc}")
        log_event(
            PIPELINE_LOGGER,
            "family_filter_failed",
            event_id="ML_PIPELINE_211",
            error=str(exc),
        )

    label_map_path = _export_label_name_map(labels_df, diagnostics_dir)
    if label_map_path:
        du.print_info(f"[ARTIFACT] Training label map exported: {label_map_path}")

    features_df = _prune_low_information_features(features_df)
    setattr(
        app_config,
        "RUNTIME_FEATURE_NONZERO_AFTER_LOW_INFORMATION",
        nonzero_counts_for_columns(features_df),
    )
    perm_surv_after_low_info = _perm_training_survival_bundle(features_df)
    features_df = _prune_potential_leakage_features(features_df, labels_df)
    setattr(
        app_config,
        "RUNTIME_FEATURE_NONZERO_FINAL_TRAINING",
        nonzero_counts_for_columns(features_df),
    )
    perm_surv_after_leakage = _perm_training_survival_bundle(features_df)
    cohort_fused_bundle = getattr(app_config, "RUNTIME_PERM_SURVIVAL_COHORT_FUSED_BUNDLE", None)
    cf_pair: tuple[dict[str, int], int] | None = None
    if (
        isinstance(cohort_fused_bundle, tuple)
        and len(cohort_fused_bundle) == 2
        and isinstance(cohort_fused_bundle[0], dict)
    ):
        cf_pair = (cohort_fused_bundle[0], int(cohort_fused_bundle[1]))
    surv_path = export_permission_training_survival_audit(
        after_align=perm_surv_after_align,
        after_family_support=perm_surv_after_family,
        after_low_information_prune=perm_surv_after_low_info,
        after_leakage_prune=perm_surv_after_leakage,
        cohort_fused=cf_pair,
        diagnostics_dir=diagnostics_dir,
        run_id=str(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
    )
    if surv_path:
        du.print_info(f"[ARTIFACT] Permission training survival audit: {surv_path}")
    try:
        fs_path = export_feature_column_survival_matrix(
            diagnostics_dir=diagnostics_dir,
            run_id=str(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
            feature_attrs=cohort_fused_attrs,
        )
        if fs_path:
            du.print_info(f"[ARTIFACT] Feature column survival matrix: {fs_path}")
    except Exception as exc:
        du.print_warning(f"[FEATURE_SURVIVAL] Export skipped: {exc}")
    leakage_audit_path = _export_leakage_pruning_audit(diagnostics_dir)
    if leakage_audit_path:
        du.print_info(f"[ARTIFACT] Leakage pruning audit exported: {leakage_audit_path}")

    if bool(getattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", True)):
        run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
        contract_path = export_feature_contract(
            feature_df=features_df,
            run_id=run_id,
            output_dir=str(diagnostics_dir),
        )
        if contract_path:
            du.print_info(f"[ARTIFACT] Training feature contract exported: {contract_path}")
    if bool(getattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", True)):
        run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
        leakage_path = export_leakage_assessment(
            feature_df=features_df,
            run_id=run_id,
            output_dir=str(diagnostics_dir),
        )
        if leakage_path:
            du.print_info(f"[ARTIFACT] Training leakage assessment exported: {leakage_path}")

    setattr(
        app_config,
        "RUNTIME_TRAINING_FINAL_FEATURE_COLUMNS",
        int(features_df.shape[1]) if isinstance(features_df, pd.DataFrame) else 0,
    )

    results, skipped = train_models(features_df, labels_df, models=models)
    promoted_model_key = summarize_models(results)
    promote_default_model(results, model_key=promoted_model_key or DEFAULT_MODEL_KEY)

    if skipped:
        du.print_warning(f"[SUMMARY] Skipped models: {', '.join(skipped)}")

    log_event(
        PIPELINE_LOGGER,
        "classifier_pipeline_complete",
        event_id="ML_PIPELINE_200",
        trained_models=sorted(results.keys()),
        skipped_models=skipped,
    )
    return results


def train_all_models(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    models: Optional[List[str]] = None,
) -> Optional[Dict[str, dict]]:
    """Public entrypoint for training configured models.

    Args:
        features: Fused feature matrix (indexed by sample id).
        labels: **Samples dataframe** with ``sample_id`` and label columns — passed through to
            ``run_classifier_pipeline`` as ``samples_df`` (name matches legacy callers).
        models: Optional model subset.
    """
    du.print_section("Train Malware Classification Models")
    log_event(
        PIPELINE_LOGGER,
        "train_all_models_start",
        event_id="ML_ENTRY_001",
        requested_models=models or [],
    )

    if features is None or features.empty:
        du.print_error("[ABORT] Feature matrix is empty or invalid.")
        log_event(
            PIPELINE_LOGGER,
            "train_all_models_failed",
            event_id="ML_ENTRY_400",
            reason="empty_features",
        )
        return None

    if labels is None or labels.empty:
        du.print_error("[ABORT] Label set is empty or invalid.")
        log_event(
            PIPELINE_LOGGER,
            "train_all_models_failed",
            event_id="ML_ENTRY_401",
            reason="empty_labels",
        )
        return None

    try:
        results = run_classifier_pipeline(
            features_df=features,
            samples_df=labels,
            save_model=True,
            models=models,
        )

        if not results:
            du.print_error("[FAILURE] Pipeline returned no valid model results.")
            log_event(
                PIPELINE_LOGGER,
                "train_all_models_failed",
                event_id="ML_ENTRY_500",
                reason="no_results",
            )
            return None

        trained = [m for m in results if m in ALL_SUPPORTED_MODELS]
        du.print_info(f"[SUMMARY] Trained models: {', '.join(trained)}")
        log_event(
            PIPELINE_LOGGER,
            "train_all_models_complete",
            event_id="ML_ENTRY_200",
            trained_models=trained,
        )
        return results

    except Exception as exc:
        du.print_error(f"[EXCEPTION] Pipeline failure: {exc}")
        du.print_debug(traceback.format_exc())
        log_event(
            PIPELINE_LOGGER,
            "train_all_models_exception",
            event_id="ML_ENTRY_501",
            error=str(exc),
        )
        if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)) and bool(
            getattr(app_config, "FAIL_FAST_TRAINING_EXCEPTIONS_IN_PAPER_MODE", True)
        ):
            raise
        return None
