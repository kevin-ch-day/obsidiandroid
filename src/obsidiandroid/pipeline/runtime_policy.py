"""Runtime profile policy helpers for pipeline orchestration.

Includes :data:`CROSS_RUN_ARTIFACT_POINTERS` / :func:`clear_cross_run_artifact_path_pointers`
for resetting path-like ``RUNTIME_*`` keys between pipeline runs (pytest isolation and
strict artifact governance). See ``obsidiandroid.pipeline`` package docs.
"""

from __future__ import annotations

from typing import Any

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console

RUNTIME_OVERRIDE_KEYS = (
    "ENABLE_CROSS_VALIDATION",
    "ENABLE_CV_REBALANCING",
    "ENABLE_SMOTE_OVERSAMPLING",
    "ENABLE_ABLATION_EXPERIMENTS",
    "ENABLE_PERMISSION_TRENDS_REPORT",
    "ENABLE_LABEL_RESOLUTION_STAGE",
    "ENABLE_ENGINE_WEIGHT_DB_SUMMARY",
    "ENABLE_FAMILY_DISTRIBUTION_REPORT",
    "ENABLE_AV_PIPELINE_EXCEL_EXPORT",
    "ENABLE_MODEL_COMPARISON_CSV_EXPORT",
    "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT",
    "ENABLE_PERMISSION_FEATURES",
    "ENABLE_SAMPLE_METADATA_FEATURES",
    "SKIP_ABLATIONS_FOR_SINGLE_MODEL",
    "ENABLE_ABLATION_MULTI_LABEL_TARGETS",
    "EXPORT_ANALYSIS_SNAPSHOT",
    "EXPORT_ALIGNED_TRAINING_CACHE",
    "ENABLE_FEATURE_CONTRACT_EXPORT",
    "ENABLE_LEAKAGE_ASSESSMENT_EXPORT",
    "WRITE_RUN_SCOPED_PERMISSION_TREND_ARTIFACTS",
)

PARSER_OVERRIDE_KEYS = (
    "PARSER_UNKNOWN_EXCLUDE_THRESHOLD",
    "PARSER_MAPPED_MIN_THRESHOLD",
    "PARSER_GENERIC_DOWNWEIGHT_THRESHOLD",
    "PARSER_GENERIC_DOWNWEIGHT_FACTOR",
    "PARSER_MIN_INCLUDED_VENDORS",
    "PARSER_ALLOW_RELAXED_MAPPED_GATE",
)

# Paths / split handles that must not leak across pytest modules or sequential CLI
# runs; :mod:`analysis.pipeline.runner` appends these to a strict artifact list.
CROSS_RUN_ARTIFACT_POINTERS: dict[str, Any] = {
    "RUNTIME_ENGINE_METADATA_OVERLAY_CSV": "",
    "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV": "",
    "RUNTIME_FEATURE_COLUMN_SURVIVAL_CSV": "",
    "RUNTIME_SPLIT_METADATA": None,
    "RUNTIME_SPLIT_HASH": "",
    "RUNTIME_SPLIT_AUDIT_PATH": "",
    "RUNTIME_HEADLINE_SPLIT_METADATA": None,
    "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH": "",
    "RUNTIME_HEADLINE_FIT_COLUMN_NAMES": None,
    "RUNTIME_HEADLINE_FEATURE_CONTRACT_PATH": "",
    "RUNTIME_LAST_FIT_FEATURE_COLUMN_HASH": "",
    "RUNTIME_COHORT_ENCODER_MAPPINGS": None,
    "RUNTIME_COHORT_FAMILY_COUNT": 0,
    "RUNTIME_ABLATION_LABEL_TARGET_SLUG": "",
    "RUNTIME_ABLATION_FEATURE_SET_NAME": "",
    "RUNTIME_SPLIT_LEDGER_INDEX": None,
}


def clear_cross_run_artifact_path_pointers() -> None:
    """Clear artifact path pointers from prior runs (see ``CROSS_RUN_ARTIFACT_POINTERS``)."""
    for key, value in CROSS_RUN_ARTIFACT_POINTERS.items():
        setattr(app_config, key, value)


def build_mutable_config_keys() -> set[str]:
    """Build runtime config keys that must be restored after a run."""
    return {
        "DEFAULT_OUTPUT_DIR",
        "RUNTIME_RUN_ROOT",
        "RUNTIME_RUN_ID",
        "EVIDENCE_MODE_ENABLED",
        "EVIDENCE_MODE_LOCKED_VALUE",
        "PAPER_MODE_ENABLED",
        "PAPER_MODE_LOCKED_VALUE",
        "RUNTIME_DIAGNOSTICS_DIR",
        "RUNTIME_TRAINING_STATE",
        "RUNTIME_PROFILE_ID",
        "RUNTIME_IS_DEV_PROFILE",
        "RUNTIME_EVIDENCE_MODE",
        "RUNTIME_EVIDENCE_STRICT_MODE",
        "RUNTIME_VENDOR_GATE_DEBUG_PATH",
        "RUNTIME_VENDOR_FALLBACK_USED",
        "RUNTIME_VENDOR_FALLBACK_ADDED_COUNT",
        "RUNTIME_MIN_FAMILY_SUPPORT",
        "RUNTIME_K_REQUESTED",
        "RUNTIME_EFFECTIVE_TOP_K",
        "RUNTIME_INCLUDED_ENGINE_COUNT",
        "RUNTIME_EVIDENCE_OVERRIDE_USED",
        "RUNTIME_NON_STANDARD_FEATURES",
        "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED",
        "RUNTIME_EXCLUDE_UNKNOWN_FROM_MAIN_RESULTS",
        "RUNTIME_ALLOW_GLOBAL_ARTIFACTS",
        "RUNTIME_OUTPUT_ROOT_BASE",
        "OUTPUT_HYGIENE_MODE",
        "ABLATION_MODEL_LIST",
        "ENABLE_ABLATION_MULTI_LABEL_TARGETS",
        "SKIP_ABLATIONS_FOR_SINGLE_MODEL",
        "ANALYSIS_SNAPSHOT_FILE",
        "ANALYSIS_SNAPSHOT_META_FILE",
        "ANALYSIS_SNAPSHOT_CONFLICT_FILE",
        "PAPER_COHORT_SAMPLE_IDS_FILE",
        "DATASET_TIME_CONTRACT_FILE",
        "ALIGNED_FEATURE_CACHE_FILE",
        "ALIGNED_LABEL_CACHE_FILE",
        "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS",
        "ALLOW_ADAPTIVE_TOP_K",
        "ENABLE_SAMPLE_METADATA_FEATURES",
        "ENABLE_PERMISSION_FEATURES",
        *PARSER_OVERRIDE_KEYS,
        *RUNTIME_OVERRIDE_KEYS,
    } | set(CROSS_RUN_ARTIFACT_POINTERS)


def reset_runtime_markers() -> None:
    """Reset run-scoped runtime markers to avoid cross-run state leakage."""
    clear_cross_run_artifact_path_pointers()
    setattr(app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "")
    setattr(app_config, "RUNTIME_VENDOR_FALLBACK_USED", False)
    setattr(app_config, "RUNTIME_VENDOR_FALLBACK_ADDED_COUNT", 0)
    setattr(app_config, "RUNTIME_K_REQUESTED", 0)
    setattr(app_config, "RUNTIME_EFFECTIVE_TOP_K", 0)
    setattr(app_config, "RUNTIME_INCLUDED_ENGINE_COUNT", 0)
    setattr(app_config, "RUNTIME_EVIDENCE_OVERRIDE_USED", False)
    setattr(app_config, "RUNTIME_NON_STANDARD_FEATURES", False)
    setattr(app_config, "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED", False)
    setattr(app_config, "RUNTIME_EXCLUDE_UNKNOWN_FROM_MAIN_RESULTS", False)
    setattr(app_config, "RUNTIME_ALLOW_GLOBAL_ARTIFACTS", False)
    setattr(app_config, "RUNTIME_EVIDENCE_MODE", False)
    setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", int(getattr(app_config, "MIN_FAMILY_SUPPORT", 3)))


def enforce_paper_perturbation_axes(profile: dict[str, Any], paper_mode: bool) -> None:
    """Hard-fail on non-approved perturbation axes when evidence mode is enabled."""
    if not paper_mode:
        return
    allowed_axes = {
        "min_malicious_detections",
        "family_cap",
        "exclude_unknown_type_slug",
        "exclude_families",
    }
    declared_axes = []
    if isinstance(profile, dict):
        declared_axes = profile.get("evidence_perturbation_axes", profile.get("paper_perturbation_axes", []))
    if not isinstance(declared_axes, list) or not declared_axes:
        raise ValueError(
            "[EVIDENCE] Profile must declare 'evidence_perturbation_axes' in evidence mode."
        )
    normalized = [str(axis).strip() for axis in declared_axes if str(axis).strip()]
    invalid = sorted(set(axis for axis in normalized if axis not in allowed_axes))
    if invalid:
        raise ValueError(
            "[EVIDENCE] Invalid perturbation axis(es) in profile: "
            f"{invalid}. Allowed: {sorted(allowed_axes)}"
        )


def apply_profile_runtime_policy(
    *,
    profile: dict[str, Any],
    feature_flags: dict[str, Any],
    allow_evidence_override: bool,
    allow_global_artifacts: bool,
    manifest_context: dict[str, Any],
) -> dict[str, Any]:
    """Apply profile runtime controls and return resolved policy values."""
    type_slug = profile.get("type_slug_filter")
    profile_id = str(profile.get("profile_id", "unknown"))
    is_dev_profile = profile_id.startswith("dev_")
    evidence_mode = bool(profile.get("evidence_mode", False))
    if is_dev_profile and evidence_mode:
        raise ValueError("[PROFILE] Development profiles cannot run in evidence mode.")

    override_requested = bool(allow_evidence_override)
    override_allowed = bool(evidence_mode and override_requested and ml_console.is_debug())
    global_artifacts_allowed = bool(allow_global_artifacts and ml_console.is_debug())
    setattr(app_config, "RUNTIME_ALLOW_GLOBAL_ARTIFACTS", global_artifacts_allowed)
    if allow_global_artifacts and not global_artifacts_allowed:
        du.print_warning(
            "[PROFILE] --allow-global-artifacts ignored. Requires ML_CONSOLE_MODE=debug."
        )
    if override_requested and not override_allowed:
        du.print_warning(
            "[PROFILE] --allow-evidence-override ignored. "
            "Requires evidence_mode=true and ML_CONSOLE_MODE=debug."
        )

    strict_evidence_mode = bool(evidence_mode and not override_allowed)
    requested_top_k = int(profile.get("top_k_requested", getattr(app_config, "FEATURE_TOP_K", 8)) or 8)
    setattr(app_config, "FEATURE_TOP_K", requested_top_k)
    setattr(
        app_config,
        "ALLOW_VENDOR_FALLBACK_FOR_WIDTH",
        bool(
            profile.get(
                "allow_vendor_fallback_for_width",
                getattr(app_config, "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", False),
            )
        ),
    )
    setattr(
        app_config,
        "ALLOW_ADAPTIVE_TOP_K",
        bool(profile.get("allow_adaptive_top_k", False)),
    )
    setattr(
        app_config,
        "RUNTIME_EXCLUDE_UNKNOWN_FROM_MAIN_RESULTS",
        bool(profile.get("exclude_unknown_from_main_results", False) or evidence_mode),
    )
    setattr(app_config, "RUNTIME_EVIDENCE_OVERRIDE_USED", bool(override_allowed))
    setattr(app_config, "RUNTIME_NON_STANDARD_FEATURES", bool(override_allowed))
    manifest_context["non_standard_features"] = bool(override_allowed)
    setattr(app_config, "RUNTIME_PROFILE_ID", profile_id)
    setattr(app_config, "RUNTIME_IS_DEV_PROFILE", bool(is_dev_profile))
    setattr(app_config, "RUNTIME_EVIDENCE_MODE", bool(evidence_mode))
    setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", bool(strict_evidence_mode))
    setattr(app_config, "RUNTIME_K_REQUESTED", int(requested_top_k))
    if is_dev_profile:
        du.print_warning(
            "[PROFILE] SANITY PROFILE ACTIVE: non-evidence mode; fallback/relaxed behavior may be active."
        )
    if evidence_mode:
        du.print_info(
            f"[EVIDENCE] mode=ON strict={int(strict_evidence_mode)} "
            f"override_used={int(override_allowed)}"
        )

    setattr(
        app_config,
        "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS",
        bool(
            feature_flags.get(
                "enable_dynamic_generic_vendor_parsers",
                getattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", True),
            )
        ),
    )
    setattr(
        app_config,
        "ENABLE_SAMPLE_METADATA_FEATURES",
        bool(
            feature_flags.get(
                "enable_sample_metadata_features",
                getattr(app_config, "ENABLE_SAMPLE_METADATA_FEATURES", True),
            )
        ),
    )
    setattr(
        app_config,
        "ENABLE_PERMISSION_FEATURES",
        bool(
            feature_flags.get(
                "enable_permission_features",
                getattr(app_config, "ENABLE_PERMISSION_FEATURES", True),
            )
        ),
    )
    setattr(
        app_config,
        "ENABLE_ABLATION_MULTI_LABEL_TARGETS",
        bool(
            feature_flags.get(
                "enable_ablation_multi_label_targets",
                getattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", True),
            )
        ),
    )

    runtime_overrides = profile.get("runtime_overrides", {}) if isinstance(profile, dict) else {}
    if isinstance(runtime_overrides, dict):
        applied_overrides: list[str] = []
        for key in RUNTIME_OVERRIDE_KEYS:
            if key not in runtime_overrides:
                continue
            value = bool(runtime_overrides.get(key))
            setattr(app_config, key, value)
            applied_overrides.append(f"{key}={value}")
            if ml_console.is_debug():
                du.print_info(f"[PROFILE] Runtime override applied: {key}={value}")
        if applied_overrides and not ml_console.is_debug():
            du.print_info(
                f"[PROFILE] Applied {len(applied_overrides)} runtime override(s). "
                "Set ML_CONSOLE_MODE=debug for per-key detail."
            )

    parser_overrides = profile.get("parser_overrides", {}) if isinstance(profile, dict) else {}
    if isinstance(parser_overrides, dict):
        applied_parser_overrides: list[str] = []
        for key in PARSER_OVERRIDE_KEYS:
            if key not in parser_overrides:
                continue
            raw_value = parser_overrides.get(key)
            if key in {"PARSER_MIN_INCLUDED_VENDORS"}:
                value = int(raw_value)
            elif key in {"PARSER_ALLOW_RELAXED_MAPPED_GATE"}:
                value = bool(raw_value)
            else:
                value = float(raw_value)
            setattr(app_config, key, value)
            applied_parser_overrides.append(f"{key}={value}")
            if ml_console.is_debug():
                du.print_info(f"[PROFILE] Parser override applied: {key}={value}")
        if applied_parser_overrides and not ml_console.is_debug():
            du.print_info(
                f"[PROFILE] Applied {len(applied_parser_overrides)} parser override(s). "
                "Set ML_CONSOLE_MODE=debug for per-key detail."
            )

    if isinstance(profile, dict) and "ablation_model_list" in profile:
        raw_abl = profile.get("ablation_model_list")
        if raw_abl is None:
            setattr(app_config, "ABLATION_MODEL_LIST", [])
        elif not isinstance(raw_abl, list):
            raise ValueError("[PROFILE] ablation_model_list must be a list or null when provided.")
        else:
            setattr(
                app_config,
                "ABLATION_MODEL_LIST",
                [str(x).strip() for x in raw_abl if str(x).strip()],
            )
    else:
        setattr(app_config, "ABLATION_MODEL_LIST", [])

    if ml_console.is_debug():
        hygiene_mode = "debug_audit"
    elif evidence_mode:
        hygiene_mode = "paper_evidence"
    elif is_dev_profile:
        hygiene_mode = "dev_fast"
    else:
        hygiene_mode = "standard"
    setattr(app_config, "OUTPUT_HYGIENE_MODE", hygiene_mode)

    return {
        "type_slug": type_slug,
        "profile_id": profile_id,
        "is_dev_profile": bool(is_dev_profile),
        "evidence_mode": bool(evidence_mode),
        "strict_evidence_mode": bool(strict_evidence_mode),
        "override_allowed": bool(override_allowed),
    }
