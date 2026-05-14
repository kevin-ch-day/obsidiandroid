"""Ablation experiment matrix registry helpers.

This module isolates experiment matrix-construction concerns so
``stage_ablation`` can remain orchestration-focused.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from pandas.api.types import is_numeric_dtype

from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.features import feature_vector_builder
from obsidiandroid.matrix.av_binary_matrix_builder import METADATA_COLS as AV_METADATA_COLS


def build_vendor_matrix(
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    include_fields: list[str],
    extra_features_df: pd.DataFrame | None = None,
    cohort_sample_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Build a vendor feature matrix honoring configured score preferences."""
    score_field = str(getattr(app_config, "FEATURE_SCORE_FIELD", "Final ML Score"))
    if bool(getattr(app_config, "ENABLE_LEAKAGE_SAFE_VENDOR_SCORING", True)):
        leakage_field = str(getattr(app_config, "LEAKAGE_SAFE_SCORE_FIELD", "Leakage Safe Score"))
        if leakage_field in weights_df.columns:
            score_field = leakage_field

    return feature_vector_builder.build_feature_vector(
        weights_df=weights_df,
        parsed_vendor_data=parsed_data,
        top_k=safe_int_config_value(getattr(app_config, "FEATURE_TOP_K", 8), default=8),
        score_preference=score_field,
        exclude_categories=list(getattr(app_config, "FEATURE_EXCLUDE_VENDOR_CATEGORIES", [])),
        min_score=getattr(app_config, "FEATURE_MIN_VENDOR_SCORE", 0.0),
        include_fields=include_fields,
        encoding="category",
        verbose=False,
        extra_features_df=extra_features_df,
        cohort_sample_ids=cohort_sample_ids,
    )


def vendor_semantic_subset(encoded_df: pd.DataFrame, variant: str) -> pd.DataFrame:
    """Drop selected semantic vendor fields from encoded vendor matrices."""
    if not isinstance(encoded_df, pd.DataFrame) or encoded_df.empty:
        return encoded_df if isinstance(encoded_df, pd.DataFrame) else pd.DataFrame()
    if variant == "no_parsed_family":
        drop_parsed, drop_threat, drop_malware_type = True, False, False
    elif variant == "no_family_no_type":
        drop_parsed, drop_threat, drop_malware_type = True, True, True
    else:
        return encoded_df.copy()
    keep: list[str | int] = []
    for col in encoded_df.columns:
        low = str(col).lower()
        if drop_parsed and "parsed_family" in low:
            continue
        if drop_threat and "threat_class" in low:
            continue
        if drop_malware_type and "malware_type" in low:
            continue
        keep.append(col)
    if not keep:
        return pd.DataFrame()
    out = encoded_df[keep].copy()
    for key, val in getattr(encoded_df, "attrs", {}).items():
        out.attrs[key] = val
    return out


def build_binary_detection_only_matrix(binary_matrix: pd.DataFrame | None) -> pd.DataFrame:
    """Build a sample_id-indexed matrix of per-engine binary detections."""
    if not isinstance(binary_matrix, pd.DataFrame) or binary_matrix.empty:
        return pd.DataFrame()
    if "sample_id" not in binary_matrix.columns:
        return pd.DataFrame()
    eng_cols = [c for c in binary_matrix.columns if c not in AV_METADATA_COLS and c != "sample_id"]
    if not eng_cols:
        return pd.DataFrame()
    out = binary_matrix[["sample_id"] + eng_cols].copy()
    for col in eng_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out.set_index("sample_id")


def build_consensus_scores_only_matrix(enriched_matrix: pd.DataFrame | None) -> pd.DataFrame:
    """Extract non-binary numeric consensus columns from enriched AV matrix."""
    if not isinstance(enriched_matrix, pd.DataFrame) or enriched_matrix.empty:
        return pd.DataFrame()
    if "sample_id" not in enriched_matrix.columns:
        return pd.DataFrame()
    skip = set(AV_METADATA_COLS) | {"sample_id"}
    numeric_cols: list[str] = []
    for col in enriched_matrix.columns:
        if col in skip:
            continue
        series = enriched_matrix[col]
        if not is_numeric_dtype(series):
            continue
        nu = pd.to_numeric(series, errors="coerce").dropna()
        if nu.empty:
            continue
        uniq = sorted({float(x) for x in nu.unique().tolist()})
        if len(uniq) <= 3 and uniq and max(uniq) <= 1.0 and min(uniq) >= 0.0:
            continue
        numeric_cols.append(col)
    if not numeric_cols:
        return pd.DataFrame()
    work = enriched_matrix[["sample_id"] + numeric_cols].copy()
    return work.drop_duplicates("sample_id").set_index("sample_id")


def build_experiment_matrix_dict(
    *,
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    permission_features_df: pd.DataFrame | None,
    pipeline_results: dict[str, Any] | None,
    cohort_sample_ids: list[int] | None,
    permissions_band_builder: Callable[[pd.DataFrame | None, str], pd.DataFrame],
) -> dict[str, Any]:
    """Return mapping of experiment names to lazy matrix builders (pre-reindex)."""
    full_vendor_fields = ["Parsed Family", "Threat Class", "Malware Type"]
    pipelines = pipeline_results if isinstance(pipeline_results, dict) else {}
    cids = cohort_sample_ids

    builders: dict[str, Any] = {}

    builders["vendor_full"] = lambda: build_vendor_matrix(
        weights_df, parsed_data, full_vendor_fields, extra_features_df=None, cohort_sample_ids=cids
    )
    builders["vendor_no_parsed_family"] = lambda: build_vendor_matrix(
        weights_df,
        parsed_data,
        ["Threat Class", "Malware Type"],
        extra_features_df=None,
        cohort_sample_ids=cids,
    )

    def _vendor_no_ft() -> pd.DataFrame:
        raw_mat = builders["vendor_full"]()
        if not isinstance(raw_mat, pd.DataFrame) or raw_mat.empty:
            return pd.DataFrame()
        return vendor_semantic_subset(raw_mat, variant="no_family_no_type")

    builders["vendor_no_family_no_type"] = _vendor_no_ft
    builders["vendor_detection_binary_only"] = lambda: build_binary_detection_only_matrix(
        pipelines.get("binary_matrix")
    )
    builders["vendor_consensus_scores_only"] = lambda: build_consensus_scores_only_matrix(
        pipelines.get("enriched_matrix")
    )

    builders["permissions_raw"] = lambda: permissions_band_builder(permission_features_df, "raw")
    builders["permissions_grouped"] = lambda: permissions_band_builder(permission_features_df, "grouped")

    def _grp_plus_vnf() -> pd.DataFrame:
        gmat = permissions_band_builder(permission_features_df, "grouped")
        if not isinstance(gmat, pd.DataFrame) or gmat.empty:
            return build_vendor_matrix(
                weights_df,
                parsed_data,
                ["Threat Class", "Malware Type"],
                cohort_sample_ids=cids,
            )
        g_df = gmat.reset_index()
        if "sample_id" not in g_df.columns and gmat.index.name == "sample_id":
            g_df = gmat.rename_axis("sample_id").reset_index()
        return build_vendor_matrix(
            weights_df,
            parsed_data,
            ["Threat Class", "Malware Type"],
            extra_features_df=g_df,
            cohort_sample_ids=cids,
        )

    builders["permissions_grouped_plus_vendor_no_family"] = _grp_plus_vnf

    builders["full_fused"] = lambda: build_vendor_matrix(
        weights_df,
        parsed_data,
        full_vendor_fields,
        extra_features_df=permission_features_df,
        cohort_sample_ids=cids,
    )

    return builders
