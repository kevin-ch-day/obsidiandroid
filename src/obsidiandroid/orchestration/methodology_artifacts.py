"""Methodology artifacts for reproducibility and leakage disclosure."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.common.hash_utils import hash_payload


def export_feature_contract(
    feature_df: pd.DataFrame,
    run_id: str,
    output_dir: str = "output/diagnostics",
    selection_contract: dict[str, Any] | None = None,
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

    # Encoder/source prefixes are not stable.  Match target-adjacent semantic
    # tokens anywhere in the final feature name so aliases cannot bypass the
    # publication gate.
    prohibited_tokens = (
        "parsed_family", "suggested_family", "family_token", "threat_class",
        "malware_type", "type_slug", "suggested_threat_label",
    )
    prohibited_exact = {
        "meta__has_vt_suggested_threat_label", "suggested_threat_label",
        "vt_suggested_threat_label",
    }
    prohibited = [
        col for col in feature_columns
        if col.lower() in prohibited_exact
        or any(token in col.lower() for token in prohibited_tokens)
    ]
    av_assisted = bool(getattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False))
    if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)) and prohibited:
        raise ValueError(
            "publication feature gate failed: label-derived AV semantics remain in final feature list: "
            + ", ".join(prohibited[:12])
        )
    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_vendors": [str(v) for v in selected_vendors],
        "selected_vendor_count": int(len(selected_vendors)),
        "feature_columns": feature_columns,
        "feature_column_hash": hash_payload(feature_columns),
        "ordered_feature_columns_artifact": f"feature_columns_{run_id}.csv",
        "feature_contract_id": str(getattr(
            app_config,
            "AV_ASSISTED_FEATURE_CONTRACT_ID" if av_assisted else "PRIMARY_FEATURE_CONTRACT_ID",
            "av_assisted_family_attribution_v1" if av_assisted else "family_classification_label_independent_v1",
        )),
        "classification_surface": "av_assisted" if av_assisted else "label_independent",
        "direct_target_proxies": int(len(prohibited)),
        "target_adjacent_semantic_fields": int(len(prohibited)),
        "prohibited_semantic_columns": prohibited,
        "publication_gate": "PASS" if not prohibited else "NOT_APPLICABLE_AV_ASSISTED",
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
    if isinstance(selection_contract, dict):
        payload["feature_selection"] = dict(selection_contract)

    stamped = f"feature_contract_{run_id}.json"
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=output_root,
        run_filename=stamped,
        payload=payload,
        global_latest_name="feature_contract.latest.json",
    )
    ordered_columns_csv = pd.DataFrame(
        {
            "run_id": str(run_id),
            "column_order": range(len(feature_columns)),
            "feature_column": feature_columns,
        }
    ).to_csv(index=False)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=output_root,
        run_filename=f"feature_columns_{run_id}.csv",
        csv_text=ordered_columns_csv,
        global_latest_name="feature_columns.latest.csv",
    )
    # Core methodology evidence is always stamped and run-bound.  Do not
    # replace it with an unversioned compatibility copy: reused run slots and
    # global ``latest`` mirrors can otherwise point reports at another run.
    return str(output_root / stamped)


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
    has_parsed_family = any("parsed_family" in col or "suggested_family" in col or "family_token" in col for col in columns)
    has_threat_class = any("threat_class" in col for col in columns)
    has_malware_type = any("malware_type" in col or "type_slug" in col for col in columns)
    has_suggested_threat = any("suggested_threat_label" in col for col in columns)
    semantic_column_count = sum(
        int(
            "parsed_family" in col
            or "suggested_family" in col
            or "family_token" in col
            or "threat_class" in col
            or "malware_type" in col
            or "type_slug" in col
            or "suggested_threat_label" in col
        )
        for col in columns
    )
    if semantic_column_count:
        leakage_class = "AV-label-informed classification"
    else:
        leakage_class = "label_independent"

    lines = [
        f"Run ID: {run_id}",
        f"Timestamp UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Parsed Family used in features (weak vendor support only): {'Yes' if has_parsed_family else 'No'}",
        f"Threat Class used (weak vendor support only): {'Yes' if has_threat_class else 'No'}",
        f"Malware Type used (weak vendor support only): {'Yes' if has_malware_type else 'No'}",
        f"Suggested Threat Label indicator used: {'Yes' if has_suggested_threat else 'No'}",
        "Ground truth label source: family_id",
        f"Leakage risk classification: {leakage_class}",
        f"classification_surface={'av_assisted' if leakage_class != 'label_independent' else 'label_independent'}",
        f"direct_target_proxies={semantic_column_count}",
        f"target_adjacent_semantic_fields={semantic_column_count}",
        f"publication_gate={'PASS' if leakage_class == 'label_independent' else 'FAIL'}",
    ]

    body = "\n".join(lines) + "\n"
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=output_root,
        run_filename=f"leakage_assessment_{run_id}.txt",
        text=body,
        global_latest_name="leakage_assessment.latest.txt",
    )
    return str(output_root / f"leakage_assessment_{run_id}.txt")


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
    label_derived_fields = [
        field
        for field, prefix in (
            ("Parsed Family", "parsed_family_"),
            ("Threat Class", "threat_class_"),
            ("Malware Type", "malware_type_"),
        )
        if any(col.startswith(prefix) for col in av_cols)
    ]
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
            "min_support": safe_int_config_value(getattr(app_config, "PERMISSION_MIN_SUPPORT", 2), default=2),
            "max_features": safe_int_config_value(getattr(app_config, "PERMISSION_MAX_FEATURES", 0), default=0),
            "semantic_weighting_applied": False,
            "grouping_applied": ["dangerous_count", "normal_count", "oem_count", "total_count"],
            "feature_count_raw": int(len(permission_cols)),
            "feature_columns_hash": hash_payload(permission_cols),
            "features_coupled_to_vendor_gating": False,
            "features_coupled_to_consensus_threshold": False,
        },
        "av_modality": {
            "representation": (
                "categorical_vendor_parsed_labels_encoded_as_integers"
                if av_cols
                else "no_label_derived_vendor_fields_in_fusion"
            ),
            "fields": label_derived_fields,
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

    oh.mirror_json_text_run_then_global(
        diagnostics_dir=output_root,
        run_filename=f"modality_method_contract_{run_id}.json",
        payload=payload,
        global_latest_name="modality_method_contract.latest.json",
    )
    return str(output_root / f"modality_method_contract_{run_id}.json")
