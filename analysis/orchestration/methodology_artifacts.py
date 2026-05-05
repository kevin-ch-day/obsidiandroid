"""Methodology artifacts for reproducibility and leakage disclosure."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common.hash_utils import hash_payload


def export_feature_contract(
    feature_df: pd.DataFrame,
    run_id: str,
    output_dir: str = "output/diagnostics",
) -> str:
    """Export feature contract artifact for exact training reproducibility.

    Args:
        feature_df: Training feature matrix.
        run_id: Runtime identifier.
        output_dir: Diagnostics directory.

    Returns:
        Path to run-scoped feature contract JSON.
    """
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return ""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    feature_columns = [str(col) for col in feature_df.columns.tolist()]
    encoder_mappings = feature_df.attrs.get("encoder_mappings", {})
    selected_vendors = feature_df.attrs.get("selected_vendors", [])

    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_vendors": [str(v) for v in selected_vendors],
        "selected_vendor_count": int(len(selected_vendors)),
        "feature_columns": feature_columns,
        "feature_column_hash": hash_payload(feature_columns),
        "encoder_mappings": encoder_mappings if isinstance(encoder_mappings, dict) else {},
        "top_k": int(feature_df.attrs.get("feature_top_k", getattr(app_config, "FEATURE_TOP_K", 8))),
        "feature_score_field": str(feature_df.attrs.get("feature_score_field", "")),
        "engine_included_count": int(feature_df.attrs.get("engine_included_count", 0)),
        "engine_excluded_count": int(feature_df.attrs.get("engine_excluded_count", 0)),
        "feature_shape": {
            "rows": int(feature_df.shape[0]),
            "columns": int(feature_df.shape[1]),
        },
    }

    run_path = output_root / "feature_contract.json"
    latest_path = output_root / "feature_contract.latest.json"
    with open(run_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    with open(latest_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return str(run_path)


def export_leakage_assessment(
    feature_df: pd.DataFrame,
    run_id: str,
    output_dir: str = "output/diagnostics",
) -> str:
    """Export plain-text leakage assessment artifact.

    Args:
        feature_df: Current feature matrix.
        run_id: Runtime identifier.
        output_dir: Diagnostics directory.

    Returns:
        Path to run-scoped leakage assessment text artifact.
    """
    columns = [str(col).lower() for col in feature_df.columns.tolist()] if isinstance(feature_df, pd.DataFrame) else []
    has_parsed_family = any(col.startswith("parsed_family_") for col in columns)
    has_threat_class = any(col.startswith("threat_class_") for col in columns)
    has_malware_type = any(col.startswith("malware_type_") for col in columns)

    if has_parsed_family or has_threat_class or has_malware_type:
        leakage_class = "AV-label-informed classification"
    else:
        leakage_class = "Lower AV-label coupling"

    lines = [
        f"Run ID: {run_id}",
        f"Timestamp UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Parsed Family used in features: {'Yes' if has_parsed_family else 'No'}",
        f"Threat Class used: {'Yes' if has_threat_class else 'No'}",
        f"Malware Type used: {'Yes' if has_malware_type else 'No'}",
        "Ground truth label source: family_id",
        f"Leakage risk classification: {leakage_class}",
    ]

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    run_path = output_root / "leakage_assessment.txt"
    latest_path = output_root / "leakage_assessment.latest.txt"
    run_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    latest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(run_path)


def export_modality_method_contract(
    *,
    permission_df: pd.DataFrame | None,
    fusion_feature_df: pd.DataFrame | None,
    run_id: str,
    output_dir: str = "output/diagnostics",
) -> str:
    """Export modality-method contract for paper-facing methods transparency.

    The artifact captures how permission/AV/fusion features are represented and
    dimensioned after preprocessing so manuscript text can be traceable.

    Args:
        permission_df: Permission modality dataframe (sample_id + permission features).
        fusion_feature_df: Final fused feature matrix used for modeling.
        run_id: Runtime identifier.
        output_dir: Diagnostics directory.

    Returns:
        Path to run-scoped modality contract JSON artifact.
    """
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    permission_cols: list[str] = []
    if isinstance(permission_df, pd.DataFrame) and not permission_df.empty:
        permission_cols = [str(col) for col in permission_df.columns if str(col) != "sample_id"]

    fusion_cols: list[str] = []
    if isinstance(fusion_feature_df, pd.DataFrame) and not fusion_feature_df.empty:
        fusion_cols = [str(col) for col in fusion_feature_df.columns]

    av_prefixes = ("parsed_family_", "threat_class_", "malware_type_")
    av_cols = [col for col in fusion_cols if col.startswith(av_prefixes)]
    perm_cols_in_fusion = [col for col in fusion_cols if col.startswith("perm__")]
    other_cols = [
        col for col in fusion_cols
        if col not in set(av_cols) and col not in set(perm_cols_in_fusion)
    ]

    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "permission_modality": {
            "representation": "binary_permission_indicators_plus_permission_counts",
            "encoding": "integer (0/1 for indicators; integer counts for aggregates)",
            "min_support": int(getattr(app_config, "PERMISSION_MIN_SUPPORT", 2)),
            "max_features": int(getattr(app_config, "PERMISSION_MAX_FEATURES", 0)),
            "semantic_weighting_applied": False,
            "grouping_applied": ["dangerous_count", "normal_count", "oem_count", "total_count"],
            "feature_count_raw": int(len(permission_cols)),
            "feature_columns_hash": hash_payload(permission_cols),
            "features_coupled_to_vendor_gating": False,
            "features_coupled_to_consensus_threshold": False,
        },
        "av_modality": {
            "representation": "categorical_vendor_parsed_labels_encoded_as_integers",
            "fields": ["Parsed Family", "Threat Class", "Malware Type"],
            "feature_count_in_fusion": int(len(av_cols)),
            "feature_columns_hash": hash_payload(av_cols),
            "coupled_to_vendor_gating": True,
            "coupled_to_consensus_threshold": True,
        },
        "fusion_modality": {
            "feature_count_total": int(len(fusion_cols)),
            "feature_count_permission": int(len(perm_cols_in_fusion)),
            "feature_count_av": int(len(av_cols)),
            "feature_count_other": int(len(other_cols)),
            "feature_columns_hash": hash_payload(fusion_cols),
            "matrix_shape": {
                "rows": int(fusion_feature_df.shape[0]) if isinstance(fusion_feature_df, pd.DataFrame) else 0,
                "columns": int(fusion_feature_df.shape[1]) if isinstance(fusion_feature_df, pd.DataFrame) else 0,
            },
        },
        "method_notes": {
            "paper_role": "permissions_are_structural_modality_not_headline_analysis",
            "run_scope": "values_reflect_this_run_only_and_must_be_cited_with_run_id",
        },
    }

    run_path = output_root / "modality_method_contract.json"
    latest_path = output_root / "modality_method_contract.latest.json"
    with open(run_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    with open(latest_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return str(run_path)
