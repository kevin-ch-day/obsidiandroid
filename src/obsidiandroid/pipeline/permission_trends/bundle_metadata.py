"""Provenance and coverage metadata for the permission trends bundle."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.governance import run_manifest
from obsidiandroid.governance.mobile_attack_permission_mapping import mobile_attack_permission_mapping_payload
from obsidiandroid.orchestration.permission_features import PERMISSION_GROUP_DEFINITIONS

from .constants import (
    BUNDLE_CONTRACT_NAME,
    BUNDLE_CONTRACT_VERSION,
    PERMISSION_ALIAS_MAP_VERSION,
    PRIMARY_PERMISSION_VIEW,
)
from .reporting_support import read_snapshot_meta


def build_bundle_metadata(
    run_id: str,
    profile_id: str,
    sample_core_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    family_support_df: pd.DataFrame,
    selected_vendors: list[str],
    engine_included_count: int,
    engine_excluded_count: int,
    permission_support_floor: int,
    kept_permission_count: int,
    kept_permissions_by_view: dict[str, list[str]],
    analysis_scope: str,
    figure_mode: str,
    cohort_hash: str,
    permission_feature_hash: str,
    type_heatmap_identity: str,
    dataset_time_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble run provenance and report coverage for the bundle contract."""
    min_selected = safe_int_config_value(
        getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1),
        default=1,
    )
    vendor_constrained = len(selected_vendors) < min_selected
    snapshot_meta = {
        "selection_rule_version": str(
            getattr(app_config, "ANALYSIS_SELECTION_RULE_VERSION", "snapshot_v1")
        ),
        "min_support": safe_int_config_value(getattr(app_config, "GENERIC_MIN_SUPPORT", 30), default=30),
        "permission_global_support_floor_rule": "max(50,1%)",
    }
    snapshot_meta.update(read_snapshot_meta())
    excluded_low_vendor = int(
        pd.to_numeric(consensus_df.get("low_vendor_count_flag", 0), errors="coerce").fillna(0).sum()
    ) if isinstance(consensus_df, pd.DataFrame) and not consensus_df.empty else 0
    temporal_summary = _build_temporal_summary(sample_core_df)
    attack_mapping = mobile_attack_permission_mapping_payload()
    return {
        "run_id": run_id,
        "profile_id": profile_id,
        "bundle_contract_name": BUNDLE_CONTRACT_NAME,
        "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
        "code_commit_hash": run_manifest.get_git_commit(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_vendor_count": len(selected_vendors),
        "selected_vendors": selected_vendors,
        "vendor_constrained_run_flag": vendor_constrained,
        "engine_included_count": engine_included_count,
        "engine_excluded_count": engine_excluded_count,
        "feature_top_k": safe_int_config_value(getattr(app_config, "FEATURE_TOP_K", 8), default=8),
        "consensus_formula_version": "v1_top_vote_share_normalized_entropy",
        "consensus_min_vendor_count": safe_int_config_value(
            getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5),
            default=5,
        ),
        "consensus_bootstrap_resamples": safe_int_config_value(
            getattr(app_config, "CONSENSUS_BOOTSTRAP_RESAMPLES", 2000),
            default=2000,
        ),
        "banker_pattern_cluster_k": safe_int_config_value(
            getattr(app_config, "BANKER_PATTERN_CLUSTER_K", 3),
            default=3,
        ),
        "permission_support_floor": int(permission_support_floor),
        "kept_permission_count": int(kept_permission_count),
        "permission_pattern_policy": {
            "primary_view": PRIMARY_PERMISSION_VIEW,
            "views": ["inclusive", "aosp_only", "ecosystem"],
            "permission_alias_map_version": PERMISSION_ALIAS_MAP_VERSION,
            "capability_bundle_names": [
                str(name).replace("_count", "") for name, _pattern in PERMISSION_GROUP_DEFINITIONS
            ],
            "capability_bundle_rule_count": int(len(PERMISSION_GROUP_DEFINITIONS)),
            "attack_mobile_mapping_version": str(attack_mapping.get("version", "") or "").strip(),
            "attack_mobile_mapping_hash": str(attack_mapping.get("hash", "") or "").strip(),
        },
        "analysis_scope": str(analysis_scope),
        "figure_mode": str(figure_mode),
        "cohort_hash": str(cohort_hash),
        "permission_feature_hash": str(permission_feature_hash),
        "type_permission_heatmap_identity": str(type_heatmap_identity),
        "kept_permission_count_by_view": {
            key: int(len(value)) for key, value in kept_permissions_by_view.items()
        },
        "snapshot_contract": snapshot_meta,
        "dataset_time_contract": dataset_time_contract or {},
        "coverage": coverage_df.to_dict(orient="records")[0] if not coverage_df.empty else {},
        "consensus_rows": int(len(consensus_df)),
        "consensus_excluded_low_vendor_count": excluded_low_vendor,
        "temporal_coverage": temporal_summary,
        "families_ge_50_support": int((family_support_df["support_ge_50_flag"] == 1).sum())
        if not family_support_df.empty
        else 0,
        "families_ge_30_support": int((family_support_df["support_ge_30_flag"] == 1).sum())
        if not family_support_df.empty
        else 0,
    }


def _build_temporal_summary(sample_core_df: pd.DataFrame) -> dict[str, Any]:
    """Summarize temporal coverage for snapshot using VT first-seen/submission fields."""
    if not isinstance(sample_core_df, pd.DataFrame) or sample_core_df.empty:
        return {}
    anchor = pd.to_datetime(sample_core_df.get("vt_first_seen_itw_date"), errors="coerce", utc=True)
    fallback = pd.to_datetime(sample_core_df.get("vt_first_submission_at_utc"), errors="coerce", utc=True)
    anchor = anchor.where(anchor.notna(), fallback)
    valid = anchor.dropna()
    if valid.empty:
        return {
            "samples_with_temporal_anchor": 0,
            "temporal_anchor_coverage": 0.0,
            "min_year": None,
            "max_year": None,
        }
    return {
        "samples_with_temporal_anchor": int(len(valid)),
        "temporal_anchor_coverage": round(float(len(valid) / max(len(sample_core_df), 1)), 6),
        "min_year": int(valid.dt.year.min()),
        "max_year": int(valid.dt.year.max()),
    }
