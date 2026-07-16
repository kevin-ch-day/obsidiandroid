"""Profile loading and validation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.governance import family_tier_authority
from obsidiandroid.governance.paper_cohort_contract import validate_profile_paper_lock
from obsidiandroid.governance.support_floor_policy import (
    SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY,
    SUPPORT_FLOOR_MODE_DIAGNOSTIC_ONLY,
    SUPPORT_FLOOR_MODE_MEMBERSHIP_GATE,
)
from . import profile_selection

PROFILES_DIR = repo_root() / "profiles"
HIDDEN_PROFILE_IDS: set[str] = set()
FINAL_OPERATOR_PROFILE_IDS = (
    "android_malware_all_current",
    "android_malware_major_families",
    "android_malware_expanded_families",
    "android_malware_type_taxonomy",
    "malicious_temporal_consensus10",
    "malicious_temporal_family300",
    "dev_fast",
    "dev_smoke",
    "malicious_temporal_stability_locked",
    "banker_locked",
    "malicious_temporal_stability",
    "malicious_temporal_stability_expanded",
    "malicious_temporal_stability_long_tail",
    "banker",
)
REQUIRED_PROFILE_KEYS = {
    "profile_id",
    "type_slug_filter",
    "cohort_gates",
    "model_list",
}
ALLOWED_MODEL_KEYS = {
    "random_forest",
    "balanced_random_forest",
    "svm",
    "xgboost",
    "logistic_regression",
}
ALLOWED_AV_BINARY_FEATURE_ENGINE_SCOPES = {
    "all_observed",
    "lifecycle_included",
}
ALLOWED_COHORT_GATE_KEYS = {
    "support_floor_mode",
    "min_samples_per_family",
    "min_family_label_confidence_score",
    "min_support_guard_mode",
    "require_mapped_family",
    "require_sha256",
    "allow_missing_package_name",
    "max_missing_package_pct",
    "exclude_unknown_type_slug",
    "require_active_type_slug",
    "min_malicious_detections",
    "family_cap",
    "family_cap_seed",
    "type_cap",
    "type_cap_seed",
    "type_cap_by_slug",
    "exclude_weak_label_kinds",
    "exclude_family_label_conflicts",
    "limit",
    "include_families",
    "include_families_from_authority",
    "exclude_families",
    "time_window_start_utc",
    "time_window_end_utc",
}

_KNOWN_READINESS_BUCKETS = {
    "all_catalog",
    "android_platform",
    "android_with_permission_obs",
    "android_high_or_strong_vt_with_permission_obs",
    "android_labeled_primary_with_permission_obs",
    "android_banker_with_permission_obs",
    "android_family_ready_min3_permission_obs",
}


def list_profiles() -> List[Path]:
    """List available YAML profile files."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(
        path for path in PROFILES_DIR.glob("*.yaml") if path.stem not in HIDDEN_PROFILE_IDS
    )


def load_profile(profile_ref: str) -> Dict[str, Any]:
    """Load profile from file path or profile id."""
    if not profile_ref or not str(profile_ref).strip():
        raise ValueError("Profile reference is required.")

    requested_ref = str(profile_ref).strip()

    profile_path = _resolve_profile_path(profile_ref)
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as handle:
        profile = yaml.safe_load(handle) or {}
    profile = _apply_policy_defaults(profile)

    _validate_profile(profile, profile_path)
    profile["__profile_path"] = str(profile_path.as_posix())
    profile["__requested_profile_ref"] = requested_ref
    return profile


def _resolve_profile_path(profile_ref: str) -> Path:
    normalized_ref = str(profile_ref).strip()
    candidate = Path(normalized_ref)
    if candidate.exists():
        return candidate
    suffix = ".yaml" if not str(normalized_ref).endswith(".yaml") else ""
    return PROFILES_DIR / f"{normalized_ref}{suffix}"


def _validate_profile(profile: Dict[str, Any], profile_path: Path) -> None:
    missing = sorted(REQUIRED_PROFILE_KEYS - set(profile.keys()))
    if missing:
        raise ValueError(
            f"Profile '{profile_path}' missing required keys: {missing}"
        )
    if not isinstance(profile.get("cohort_gates"), dict):
        raise ValueError("Profile key 'cohort_gates' must be a dictionary.")
    if not isinstance(profile.get("model_list"), list) or not profile.get("model_list"):
        raise ValueError("Profile key 'model_list' must be a non-empty list.")
    if not isinstance(profile.get("evidence_mode"), bool):
        raise ValueError("Profile key 'evidence_mode' must be a boolean.")
    if not isinstance(profile.get("allow_vendor_fallback_for_width"), bool):
        raise ValueError("Profile key 'allow_vendor_fallback_for_width' must be a boolean.")
    if not isinstance(profile.get("allow_adaptive_top_k"), bool):
        raise ValueError("Profile key 'allow_adaptive_top_k' must be a boolean.")
    if not isinstance(profile.get("exclude_unknown_from_main_results"), bool):
        raise ValueError("Profile key 'exclude_unknown_from_main_results' must be a boolean.")
    top_k_requested = profile.get("top_k_requested")
    if not isinstance(top_k_requested, int) or top_k_requested <= 0:
        raise ValueError("Profile key 'top_k_requested' must be a positive integer.")

    model_list = profile.get("model_list", [])
    invalid_models = sorted(
        str(model).strip()
        for model in model_list
        if str(model).strip() not in ALLOWED_MODEL_KEYS
    )
    if invalid_models:
        allowed = ", ".join(sorted(ALLOWED_MODEL_KEYS))
        invalid = ", ".join(invalid_models)
        raise ValueError(
            f"Profile '{profile_path}' has unsupported model_list entries: [{invalid}]. "
            f"Allowed models: [{allowed}]."
        )

    if "ablation_model_list" in profile:
        ablation_models = profile.get("ablation_model_list")
        if ablation_models is None:
            pass
        elif not isinstance(ablation_models, list):
            raise ValueError(
                f"Profile '{profile_path}' requires ablation_model_list to be a list (or null), "
                f"not {type(ablation_models).__name__}."
            )
        else:
            invalid_ablation = sorted(
                str(model).strip()
                for model in ablation_models
                if str(model).strip() not in ALLOWED_MODEL_KEYS
            )
            if invalid_ablation:
                allowed = ", ".join(sorted(ALLOWED_MODEL_KEYS))
                bad = ", ".join(invalid_ablation)
                raise ValueError(
                    f"Profile '{profile_path}' has unsupported ablation_model_list entries: [{bad}]. "
                    f"Allowed models: [{allowed}]."
                )

    cohort_gates = profile.get("cohort_gates", {})
    invalid_gate_keys = sorted(
        str(key).strip()
        for key in cohort_gates.keys()
        if str(key).strip() not in ALLOWED_COHORT_GATE_KEYS
    )
    if invalid_gate_keys:
        allowed_keys = ", ".join(sorted(ALLOWED_COHORT_GATE_KEYS))
        bad_keys = ", ".join(invalid_gate_keys)
        raise ValueError(
            f"Profile '{profile_path}' has unsupported cohort_gates keys: [{bad_keys}]. "
            f"Allowed keys: [{allowed_keys}]."
        )
    require_active_type_slug = cohort_gates.get("require_active_type_slug")
    if require_active_type_slug is not None and not isinstance(require_active_type_slug, bool):
        raise ValueError(
            f"Profile '{profile_path}' requires require_active_type_slug to be a boolean."
        )
    include_families_from_authority = str(
        cohort_gates.get("include_families_from_authority", "") or ""
    ).strip()
    if include_families_from_authority and include_families_from_authority not in {"major_families"}:
        raise ValueError(
            f"Profile '{profile_path}' has unsupported include_families_from_authority="
            f"{include_families_from_authority!r}. Allowed values: ['major_families']."
        )
    support_floor_mode = str(cohort_gates.get("support_floor_mode", "") or "").strip().lower()
    if support_floor_mode and support_floor_mode not in {
        SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY,
        SUPPORT_FLOOR_MODE_MEMBERSHIP_GATE,
        SUPPORT_FLOOR_MODE_DIAGNOSTIC_ONLY,
    }:
        raise ValueError(
            f"Profile '{profile_path}' has unsupported support_floor_mode={support_floor_mode!r}. "
            f"Allowed values: ['{SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY}', "
            f"'{SUPPORT_FLOOR_MODE_MEMBERSHIP_GATE}', "
            f"'{SUPPORT_FLOOR_MODE_DIAGNOSTIC_ONLY}']."
        )
    type_cap_by_slug = cohort_gates.get("type_cap_by_slug")
    if type_cap_by_slug is not None:
        if not isinstance(type_cap_by_slug, dict):
            raise ValueError(
                f"Profile '{profile_path}' requires type_cap_by_slug to be a mapping."
            )
        for key, value in type_cap_by_slug.items():
            if not str(key).strip():
                raise ValueError(
                    f"Profile '{profile_path}' has blank type_cap_by_slug key."
                )
            if not isinstance(value, int) or value <= 0:
                raise ValueError(
                    f"Profile '{profile_path}' type_cap_by_slug[{key!r}] must be a positive integer."
                )
    if bool(profile.get("evidence_mode")):
        start_utc = str(cohort_gates.get("time_window_start_utc", "") or "").strip()
        end_utc = str(cohort_gates.get("time_window_end_utc", "") or "").strip()
        if not start_utc or not end_utc:
            raise ValueError(
                "Evidence-mode profile requires explicit time_window_start_utc and time_window_end_utc."
            )
    training_label_field = str(profile.get("training_label_field", "") or "").strip()
    if training_label_field and training_label_field not in {"family_id", "type_slug", "family_within_type"}:
        raise ValueError(
            f"Profile '{profile_path}' has unsupported training_label_field={training_label_field!r}. "
            "Allowed values: ['family_id', 'type_slug', 'family_within_type']."
        )
    av_binary_scope = str(profile.get("av_binary_feature_engine_scope", "all_observed") or "").strip().lower()
    if av_binary_scope not in ALLOWED_AV_BINARY_FEATURE_ENGINE_SCOPES:
        allowed = ", ".join(sorted(ALLOWED_AV_BINARY_FEATURE_ENGINE_SCOPES))
        raise ValueError(
            f"Profile '{profile_path}' has unsupported "
            f"av_binary_feature_engine_scope={av_binary_scope!r}. Allowed values: [{allowed}]."
        )
    validate_profile_paper_lock(profile, profile_path)


def _apply_policy_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Apply policy defaults for backward-compatible profile loading."""
    out = dict(profile)
    out.setdefault("evidence_mode", False)
    out.setdefault("allow_vendor_fallback_for_width", True)
    out.setdefault("allow_adaptive_top_k", True)
    out.setdefault("top_k_requested", 8)
    # Keep predictive AV-engine membership explicit and deterministic.  A
    # lifecycle-filtered scope is an experimental comparison, never an
    # inherited side effect of a prior process-local run.
    out.setdefault("av_binary_feature_engine_scope", "all_observed")
    out.setdefault("exclude_unknown_from_main_results", False)
    out.setdefault("paper_locked", False)
    out["cohort_gates"] = _resolve_authority_backed_cohort_gates(
        out.get("cohort_gates") if isinstance(out.get("cohort_gates"), dict) else {}
    )
    out["profile_status"] = _normalize_profile_status(out)
    return out


def _resolve_authority_backed_cohort_gates(cohort_gates: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve symbolic authority references into concrete cohort gate lists."""
    resolved = dict(cohort_gates)
    authority_ref = str(resolved.get("include_families_from_authority", "") or "").strip()
    if authority_ref == "major_families":
        resolved["include_families"] = list(family_tier_authority.major_family_name_list())
    return resolved


def _normalize_profile_status(profile: Dict[str, Any]) -> Dict[str, str]:
    """Return normalized profile lifecycle metadata for display/inventory surfaces."""
    profile_id = str(profile.get("profile_id", "") or "").strip()
    declared = profile.get("profile_status") if isinstance(profile.get("profile_status"), dict) else {}

    if profile_id in FINAL_OPERATOR_PROFILE_IDS and profile_id.startswith("dev_"):
        defaults = {
            "lifecycle": "dev_only",
            "operator_surface": "supported_dev",
            "support_tier": "development",
            "status_label": "Dev-only supported",
            "canonical_profile_id": profile_id,
            "replacement_profile_id": profile_id,
        }
    elif profile_id in FINAL_OPERATOR_PROFILE_IDS:
        defaults = {
            "lifecycle": "final_canonical",
            "operator_surface": "supported",
            "support_tier": "final",
            "status_label": "Final canonical",
            "canonical_profile_id": profile_id,
            "replacement_profile_id": profile_id,
        }
    else:
        defaults = {
            "lifecycle": "catalog_non_primary",
            "operator_surface": "debug_or_catalog",
            "support_tier": "non_primary",
            "status_label": "Non-primary catalog",
            "canonical_profile_id": profile_id,
            "replacement_profile_id": profile_id,
        }

    normalized = dict(defaults)
    for key, value in declared.items():
        token = str(key).strip()
        if token:
            normalized[token] = str(value).strip()
    return normalized


def infer_cohort_readiness_signal(profile_ref: str | Dict[str, Any] | None) -> Dict[str, str | None]:
    """Return advisory cohort-readiness mapping for operator review surfaces.

    This is intentionally non-enforcing. It helps operators interpret which
    live split-catalog readiness bucket best matches the selected profile.
    """
    profile: Dict[str, Any] = {}
    if isinstance(profile_ref, dict):
        profile = dict(profile_ref)
    else:
        token = str(profile_ref or "").strip()
        if token:
            try:
                profile = load_profile(token)
            except Exception:
                profile = {"profile_id": token}

    profile_id = str(profile.get("profile_id", "") or "").strip()
    profile_id_lc = profile_id.lower()
    type_slug_filter = str(profile.get("type_slug_filter", "") or "").strip().lower()
    evidence_mode = bool(profile.get("evidence_mode", False))
    cohort_gates = profile.get("cohort_gates") if isinstance(profile.get("cohort_gates"), dict) else {}
    dataset_filters = profile.get("dataset_filters") if isinstance(profile.get("dataset_filters"), dict) else {}
    paper_lock = profile.get("paper_lock") if isinstance(profile.get("paper_lock"), dict) else {}
    paper_locked = bool(profile.get("paper_locked", False))
    expected_type_scope = str(paper_lock.get("expected_type_scope", "") or "").strip().lower()
    min_samples_per_family = cohort_gates.get("min_samples_per_family")
    dataset_mode = str(dataset_filters.get("mode", "") or "").strip().lower()
    declared_bucket = _declared_readiness_bucket(profile)

    def _mapped(bucket: str, reason: str) -> Dict[str, str | None]:
        prefix = (
            f"Declared readiness bucket in profile contract: {declared_bucket}. "
            if declared_bucket and declared_bucket == bucket
            else ""
        )
        caveats: list[str] = []
        if "permission_obs" in bucket:
            caveats.append(
                "Permission-observation wording is advisory here; bucket mapping does not verify or enforce PI observation materialization for the selected run."
            )
        if paper_locked:
            caveats.append(
                "This profile uses a locked benchmark cohort; snapshot membership can prevent new DB curation or authority expansions from changing the cohort until the lock is refreshed."
            )
        caveat_text = f" {' '.join(caveats)}" if caveats else ""
        return {
            "status": "mapped",
            "bucket": bucket,
            "summary": f"Best matching readiness bucket: {bucket}",
            "detail": f"{prefix}{reason} Advisory only; this does not enforce sample selection.{caveat_text}",
            "ambiguity_reason": None,
        }

    if declared_bucket:
        return _mapped(
            declared_bucket,
            _readiness_bucket_reason(declared_bucket),
        )

    if (
        type_slug_filter == "banker"
        or expected_type_scope == "banker"
        or "banker" in profile_id_lc
    ):
        return _mapped(
            "android_banker_with_permission_obs",
            "Banker-focused profile intent is best compared against the Android banker cohort with permission observations.",
        )

    if profile_id_lc in {
        "malicious_temporal_stability",
        "malicious_temporal_stability_locked",
        "malicious_temporal_stability_expanded",
        "malicious_temporal_stability_long_tail",
        "malicious_temporal_consensus10",
        "malicious_temporal_family300",
    } or expected_type_scope == "all_malicious" or (
        evidence_mode and dataset_mode == "malicious_only" and type_slug_filter in {"", "all"}
    ):
        bucket = (
            "android_high_or_strong_vt_with_permission_obs"
            if evidence_mode
            else "android_with_permission_obs"
        )
        reason = (
            "Android malicious evidence-style profile intent is best compared against the Android cohort with permission observations and high/strong VT confidence."
            if evidence_mode
            else "Android malicious permission-feature profile intent is best compared against the Android cohort with permission observations."
        )
        return _mapped(
            bucket,
            reason,
        )

    if type_slug_filter in {"dropper", "rat", "sms-trojan", "spyware", "stealer", "adware"} or (
        dataset_mode == "malicious_only"
        and type_slug_filter not in {"", "all"}
        and min_samples_per_family not in (None, "")
    ):
        return _mapped(
            "android_family_ready_min3_permission_obs",
            "Family classification and min-support profile intent is best compared against the Android family-ready cohort with permission observations.",
        )

    if profile_id_lc.startswith("dev_") or profile_id_lc in {"mixed", "benign_heavy"} or dataset_mode in {
        "mixed_balanced",
        "benign_heavy",
    }:
        return _mapped(
            "android_platform",
            "Broad Android or mixed-scope exploratory profile intent is best compared against the Android platform readiness signal.",
        )

    if dataset_mode and dataset_mode != "malicious_only":
        return _mapped(
            "all_catalog",
            "Broad catalog profile intent is best compared against the full catalog readiness signal.",
        )

    return {
        "status": "ambiguous",
        "bucket": None,
        "summary": "No readiness bucket mapped for this profile; review cohort filters manually.",
        "detail": "This guidance is advisory only and does not enforce sample selection.",
        "ambiguity_reason": "Ambiguous profile intent; no readiness bucket selected.",
    }


def _readiness_bucket_reason(bucket: str) -> str:
    """Return a human-readable reason for a declared or inferred readiness bucket."""
    token = str(bucket or "").strip()
    if token == "android_banker_with_permission_obs":
        return (
            "Banker-focused profile intent is best compared against the Android banker cohort with permission observations."
        )
    if token == "android_high_or_strong_vt_with_permission_obs":
        return (
            "Android malicious evidence-style profile intent is best compared against the Android cohort with permission observations and high/strong VT confidence."
        )
    if token == "android_with_permission_obs":
        return (
            "Android malicious permission-feature profile intent is best compared against the Android cohort with permission observations."
        )
    if token == "android_family_ready_min3_permission_obs":
        return (
            "Family classification and min-support profile intent is best compared against the Android family-ready cohort with permission observations."
        )
    if token == "android_platform":
        return "Broad Android or mixed-scope exploratory profile intent is best compared against the Android platform readiness signal."
    if token == "all_catalog":
        return "Broad catalog profile intent is best compared against the full catalog readiness signal."
    return "Declared readiness bucket aligns with the selected profile intent."


def _declared_readiness_bucket(profile: Dict[str, Any]) -> str | None:
    """Return an explicitly declared readiness bucket when the profile contract provides one."""
    candidate_sources = (
        profile.get("cohort_readiness_bucket"),
        profile.get("readiness_bucket"),
        profile.get("profile_status", {}).get("readiness_bucket")
        if isinstance(profile.get("profile_status"), dict)
        else None,
        profile.get("paper_lock", {}).get("readiness_bucket")
        if isinstance(profile.get("paper_lock"), dict)
        else None,
    )
    for candidate in candidate_sources:
        bucket = str(candidate or "").strip()
        if bucket in _KNOWN_READINESS_BUCKETS:
            return bucket
    return None


def inventory_cohort_readiness_mappings(
    *,
    include_hidden: bool = True,
    profile_ids: list[str] | tuple[str, ...] | None = None,
) -> List[Dict[str, Any]]:
    """Return advisory cohort-readiness mapping inventory for bundled profiles."""
    paths = sorted(PROFILES_DIR.glob("*.yaml"))
    if not include_hidden:
        paths = [path for path in paths if path.stem not in HIDDEN_PROFILE_IDS]
    if profile_ids is not None:
        wanted = {str(profile_id).strip() for profile_id in profile_ids if str(profile_id).strip()}
        paths = [path for path in paths if path.stem in wanted]

    inventory: list[dict[str, Any]] = []
    for profile_path in paths:
        profile = load_profile(str(profile_path))
        signal = infer_cohort_readiness_signal(profile)
        inventory.append(
            {
                "profile_id": str(profile.get("profile_id", profile_path.stem) or profile_path.stem),
                "profile_path": str(profile_path.as_posix()),
                "description": str(profile.get("description", "") or "").strip(),
                "profile_status": dict(profile.get("profile_status", {}))
                if isinstance(profile.get("profile_status"), dict)
                else {},
                "lifecycle": str(
                    (
                        profile.get("profile_status", {})
                        if isinstance(profile.get("profile_status"), dict)
                        else {}
                    ).get("lifecycle", "")
                    or ""
                ).strip(),
                "operator_surface": str(
                    (
                        profile.get("profile_status", {})
                        if isinstance(profile.get("profile_status"), dict)
                        else {}
                    ).get("operator_surface", "")
                    or ""
                ).strip(),
                "support_tier": str(
                    (
                        profile.get("profile_status", {})
                        if isinstance(profile.get("profile_status"), dict)
                        else {}
                    ).get("support_tier", "")
                    or ""
                ).strip(),
                "bucket": signal.get("bucket"),
                "summary": str(signal.get("summary", "") or "").strip(),
                "detail": str(signal.get("detail", "") or "").strip(),
                "status": str(signal.get("status", "ambiguous") or "ambiguous"),
                "ambiguity_reason": (
                    str(signal.get("ambiguity_reason", "") or "").strip() or None
                ),
            }
        )
    return inventory


def select_profile_interactive(
    *,
    breadcrumb: str | None = None,
    subtitle: str | None = None,
    title: str = "Execution profile",
    exit_label: str = "Back",
) -> str | None:
    """Prompt user to select a profile id with richer context."""
    return profile_selection.select_profile_interactive(
        list_profiles_fn=list_profiles,
        load_profile_fn=load_profile,
        breadcrumb=breadcrumb,
        subtitle=subtitle,
        title=title,
        exit_label=exit_label,
    )


def select_profile_interactive_quick(
    *,
    breadcrumb: str | None = None,
    subtitle: str | None = None,
    title: str = "Execution profile",
    exit_label: str = "Back",
) -> str | None:
    """Prompt the intent-first operator menu for common run paths."""
    return profile_selection.select_profile_interactive_quick(
        list_profiles_fn=list_profiles,
        load_profile_fn=load_profile,
        select_profile_interactive_fn=select_profile_interactive,
        breadcrumb=breadcrumb,
        subtitle=subtitle,
        title=title,
        exit_label=exit_label,
    )
