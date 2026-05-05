"""Modeling-stage helpers for feature construction, training, and label resolution."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from obsidiandroid.evaluation import engine_scoring_summary
from analysis.feature_engineering import compute_vendor_scores
from config import app_config
from obsidiandroid.labeling import classification_label_resolver
from obsidiandroid.modeling import pipeline_core
from obsidiandroid.features import feature_vector_builder
from obsidiandroid.cli.ui import display as du
from obsidiandroid.observability.logging import get_logger, log_event


PIPELINE_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.pipeline.modeling",
    "pipeline",
)


def compute_engine_weights_from_pipeline(
    pipeline_results: dict,
) -> Optional[pd.DataFrame]:
    """Compute AV engine weights from vendor evaluation output.

    Args:
        pipeline_results: Pipeline dictionary with ``vendor_eval_df`` key.

    Returns:
        A weights dataframe if successful, otherwise ``None``.
    """
    du.print_subheader("Compute AV Engine Weights")
    log_event(
        PIPELINE_LOGGER,
        "engine_weights_start",
        has_vendor_eval=bool(isinstance(pipeline_results.get("vendor_eval_df"), pd.DataFrame)),
    )
    try:
        if bool(getattr(app_config, "ENABLE_ENGINE_WEIGHT_DB_SUMMARY", True)):
            summary_df = engine_scoring_summary.build_av_engine_scoring_summary_from_db()
            if summary_df.empty:
                raise ValueError("Engine scoring summary is empty.")
            pipeline_results["engine_summary"] = summary_df
        else:
            du.print_info("[ENGINE WEIGHTS] DB engine summary stage disabled by config.")

        vendor_eval_df = pipeline_results.get("vendor_eval_df")
        if not isinstance(vendor_eval_df, pd.DataFrame) or vendor_eval_df.empty:
            raise ValueError("Vendor evaluation summary is missing or invalid.")

        weights_df = compute_vendor_scores.run_score_analysis(vendor_eval_df, verbose=True)
        weights_df = _enrich_vendor_trust_flags(
            weights_df=weights_df,
            engine_scores_df=pipeline_results.get("engine_scores"),
        )
        du.print_success(f"Engine weights computed: {weights_df.shape}")
        log_event(
            PIPELINE_LOGGER,
            "engine_weights_complete",
            rows=int(weights_df.shape[0]),
            columns=int(weights_df.shape[1]),
        )
        return weights_df

    except Exception as exc:
        du.print_error(f"[ERROR] Engine weight computation failed: {exc}")
        log_event(PIPELINE_LOGGER, "engine_weights_failed", error=str(exc))
        return None


def _normalize_vendor_name(value: object) -> str:
    """Normalize vendor names for reliable join behavior across dataframes."""
    return str(value or "").strip().lower().replace("-", "").replace("_", "")


def _enrich_vendor_trust_flags(
    *,
    weights_df: pd.DataFrame,
    engine_scores_df: object,
) -> pd.DataFrame:
    """Attach trusted/active engine governance flags to vendor weights."""
    if not isinstance(weights_df, pd.DataFrame) or weights_df.empty:
        return weights_df
    if not isinstance(engine_scores_df, pd.DataFrame) or engine_scores_df.empty:
        out = weights_df.copy()
        out["trusted_vendor_flag"] = 0
        out["active_vendor_flag"] = 0
        return out

    name_col = next(
        (
            col
            for col in ("Engine Name", "engine_name", "vendor", "Vendor")
            if col in engine_scores_df.columns
        ),
        None,
    )
    if not name_col:
        out = weights_df.copy()
        out["trusted_vendor_flag"] = 0
        out["active_vendor_flag"] = 0
        return out

    score_frame = engine_scores_df.copy()
    score_frame["vendor_norm"] = score_frame[name_col].map(_normalize_vendor_name)
    score_frame["trusted_vendor_flag"] = pd.to_numeric(
        score_frame.get("Trusted", 0), errors="coerce"
    ).fillna(0).astype(int)
    score_frame["active_vendor_flag"] = pd.to_numeric(
        score_frame.get("Active", 0), errors="coerce"
    ).fillna(0).astype(int)
    score_frame = (
        score_frame[["vendor_norm", "trusted_vendor_flag", "active_vendor_flag"]]
        .drop_duplicates(subset=["vendor_norm"], keep="last")
    )

    out = weights_df.copy()
    vendor_col = "Vendor" if "Vendor" in out.columns else None
    if vendor_col is None:
        out["trusted_vendor_flag"] = 0
        out["active_vendor_flag"] = 0
        return out

    out["vendor_norm"] = out[vendor_col].map(_normalize_vendor_name)
    out = out.merge(score_frame, on="vendor_norm", how="left")
    out["trusted_vendor_flag"] = pd.to_numeric(
        out.get("trusted_vendor_flag", 0), errors="coerce"
    ).fillna(0).astype(int)
    out["active_vendor_flag"] = pd.to_numeric(
        out.get("active_vendor_flag", 0), errors="coerce"
    ).fillna(0).astype(int)
    out = out.drop(columns=["vendor_norm"])

    trusted_count = int(out["trusted_vendor_flag"].sum())
    active_count = int(out["active_vendor_flag"].sum())
    du.print_info(
        "[ENGINE WEIGHTS] Trusted/active vendor flags merged: "
        f"trusted={trusted_count}, active={active_count}"
    )
    return out


def build_feature_matrix_stage(
    weights_df: pd.DataFrame,
    vendor_data: dict,
    extra_features: pd.DataFrame | None = None,
    cohort_sample_ids: pd.Series | list | None = None,
) -> Optional[pd.DataFrame]:
    """Build the model feature matrix from weighted vendor metadata.

    Args:
        weights_df: Engine scoring/weights dataframe.
        vendor_data: Parsed vendor metadata map.
        extra_features: Optional enrichment dataframe.

    Returns:
        Feature dataframe if successful, otherwise ``None``.
    """
    du.print_subheader("Build ML Feature Vectors")
    top_k = int(getattr(app_config, "FEATURE_TOP_K", 8))
    score_field = str(getattr(app_config, "FEATURE_SCORE_FIELD", "Final ML Score"))
    if bool(getattr(app_config, "ENABLE_LEAKAGE_SAFE_VENDOR_SCORING", True)):
        leakage_safe_field = str(
            getattr(app_config, "LEAKAGE_SAFE_SCORE_FIELD", "Leakage Safe Score")
        )
        if leakage_safe_field in weights_df.columns:
            score_field = leakage_safe_field
    exclude_categories = list(
        getattr(app_config, "FEATURE_EXCLUDE_VENDOR_CATEGORIES", [])
    )
    min_score = getattr(app_config, "FEATURE_MIN_VENDOR_SCORE", 0.0)
    du.print_info(
        f"[PARAM] top_k={top_k}, score='{score_field}', "
        f"exclude_categories={exclude_categories}, min_score={min_score}"
    )
    baseline_final_ml = str(getattr(app_config, "FEATURE_SCORE_FIELD", "Final ML Score"))
    leak_field = str(getattr(app_config, "LEAKAGE_SAFE_SCORE_FIELD", "Leakage Safe Score"))
    du.print_info(
        f"[PARAM] Vendor top_k / get_top_engines_by_score sorts on '{score_field}' "
        f"(FEATURE_SCORE_FIELD default is '{baseline_final_ml}')."
    )
    if (
        bool(getattr(app_config, "ENABLE_LEAKAGE_SAFE_VENDOR_SCORING", True))
        and score_field == leak_field
    ):
        du.print_info(
            "[PARAM] Leakage Safe Score is the active selector for top_k vendors. "
            "Vendor summary tables that emphasize 'Final ML Score', precision, or generic labels "
            "describe different diagnostics and are not the same ranking key unless configured."
        )
    log_event(
        PIPELINE_LOGGER,
        "feature_matrix_start",
        top_k=top_k,
        score_field=score_field,
        exclude_categories=exclude_categories,
        min_score=min_score,
    )

    try:
        feature_df = feature_vector_builder.build_feature_vector(
            weights_df=weights_df,
            parsed_vendor_data=vendor_data,
            top_k=top_k,
            score_preference=score_field,
            exclude_categories=exclude_categories,
            min_score=min_score,
            include_fields=["Parsed Family", "Threat Class", "Malware Type"],
            encoding="category",
            verbose=True,
            extra_features_df=extra_features,
            cohort_sample_ids=cohort_sample_ids,
        )
        if feature_df.empty:
            raise ValueError("Feature matrix is empty.")
        fallback_used = bool(feature_df.attrs.get("vendor_fallback_used", False))
        fallback_added = int(feature_df.attrs.get("vendor_fallback_added_count", 0) or 0)
        selected_vendor_count = int(len(feature_df.attrs.get("selected_vendors", [])))
        selection_policy = str(
            feature_df.attrs.get("vendor_selection_policy", "parser_gated_only")
        )
        log_event(
            PIPELINE_LOGGER,
            "feature_matrix_vendor_selection",
            fallback_used=fallback_used,
            fallback_added_count=fallback_added,
            selected_vendor_count=selected_vendor_count,
            selection_policy=selection_policy,
            requested_top_k=int(getattr(app_config, "FEATURE_TOP_K", top_k)),
            strict_evidence_mode=bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False)),
        )
        if fallback_used:
            du.print_warning(
                "[FEATURE BUILD] Vendor fallback engaged: "
                f"added={fallback_added}, selected={selected_vendor_count}."
            )
        du.print_success(f"[FEATURES] Matrix shape: {feature_df.shape}")
        log_event(
            PIPELINE_LOGGER,
            "feature_matrix_complete",
            rows=int(feature_df.shape[0]),
            columns=int(feature_df.shape[1]),
        )
        return feature_df
    except Exception as exc:
        du.print_error(f"[ERROR] Feature matrix generation failed: {exc}")
        log_event(PIPELINE_LOGGER, "feature_matrix_failed", error=str(exc))
        return None


def run_training_stage(
    aligned_feature_df: pd.DataFrame,
    aligned_labels_df: pd.DataFrame,
    model_list: list[str] | None,
) -> dict | None:
    """Run classifier training stage and return model result dictionary."""
    if model_list:
        du.print_info(f"[TRAINING] Requested model subset: {', '.join(model_list)}")
    log_event(
        PIPELINE_LOGGER,
        "training_stage_start",
        requested_models=list(model_list or []),
    )
    model_results = pipeline_core.train_all_models(
        aligned_feature_df,
        aligned_labels_df,
        models=model_list,
    )
    if not model_results:
        du.print_error("[PIPELINE] Model training failed.")
        log_event(PIPELINE_LOGGER, "training_stage_failed", reason="no_model_results")
        return None
    log_event(
        PIPELINE_LOGGER,
        "training_stage_complete",
        result_keys=sorted(list(model_results.keys())),
    )
    return model_results


def resolve_final_labels_stage(
    vendor_records: dict,
    model_output: dict,
) -> Optional[pd.DataFrame]:
    """Resolve final structured labels from trained model output."""
    has_predictions = bool(model_output.get("predictions")) if isinstance(model_output, dict) else False
    log_event(PIPELINE_LOGGER, "label_resolution_start", has_predictions=has_predictions)
    try:
        if not isinstance(model_output, dict):
            raise ValueError("Model output is not a dictionary.")
        if not model_output.get("predictions"):
            raise ValueError("No predictions found in model output.")
        result_df = classification_label_resolver.resolve_structured_classification_labels(
            vendor_records=vendor_records,
            model_output=model_output,
        )
        if isinstance(result_df, pd.DataFrame):
            log_event(
                PIPELINE_LOGGER,
                "label_resolution_complete",
                rows=int(result_df.shape[0]),
                columns=int(result_df.shape[1]),
            )
        return result_df
    except Exception as exc:
        du.print_error(f"[LABEL RESOLUTION] Failed to finalize structured labels: {exc}")
        log_event(PIPELINE_LOGGER, "label_resolution_failed", error=str(exc))
        return None
