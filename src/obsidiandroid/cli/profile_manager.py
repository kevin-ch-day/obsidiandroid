"""Profile loading and validation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.governance.paper_cohort_contract import validate_profile_paper_lock
from . import profile_selection

PROFILES_DIR = repo_root() / "profiles"
PROFILE_ALIASES = {
    "paper1_banker_locked": "banker_locked",
    "paper2_primary": "malicious_temporal_stability",
    "paper2_primary_locked": "malicious_temporal_stability_locked",
    "paper2_sensitivity_consensus10": "malicious_temporal_consensus10",
    "paper2_sensitivity_family300": "malicious_temporal_family300",
}
HIDDEN_PROFILE_IDS = set(PROFILE_ALIASES.keys())
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
ALLOWED_COHORT_GATE_KEYS = {
    "min_samples_per_family",
    "require_mapped_family",
    "require_sha256",
    "allow_missing_package_name",
    "max_missing_package_pct",
    "exclude_unknown_type_slug",
    "min_malicious_detections",
    "family_cap",
    "family_cap_seed",
    "limit",
    "include_families",
    "exclude_families",
    "time_window_start_utc",
    "time_window_end_utc",
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

    profile_path = _resolve_profile_path(profile_ref)
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as handle:
        profile = yaml.safe_load(handle) or {}
    profile = _apply_policy_defaults(profile)

    _validate_profile(profile, profile_path)
    profile["__profile_path"] = str(profile_path.as_posix())
    return profile


def _resolve_profile_path(profile_ref: str) -> Path:
    normalized_ref = str(profile_ref).strip()
    candidate = Path(normalized_ref)
    if candidate.exists():
        return candidate
    normalized_ref = PROFILE_ALIASES.get(normalized_ref, normalized_ref)
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
    if bool(profile.get("evidence_mode")):
        start_utc = str(cohort_gates.get("time_window_start_utc", "") or "").strip()
        end_utc = str(cohort_gates.get("time_window_end_utc", "") or "").strip()
        if not start_utc or not end_utc:
            raise ValueError(
                "Evidence-mode profile requires explicit time_window_start_utc and time_window_end_utc."
            )
    validate_profile_paper_lock(profile, profile_path)


def _apply_policy_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Apply policy defaults for backward-compatible profile loading."""
    out = dict(profile)
    out.setdefault("evidence_mode", False)
    out.setdefault("allow_vendor_fallback_for_width", True)
    out.setdefault("allow_adaptive_top_k", True)
    out.setdefault("top_k_requested", 8)
    out.setdefault("exclude_unknown_from_main_results", False)
    out.setdefault("paper_locked", False)
    return out


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
                profile = {"profile_id": PROFILE_ALIASES.get(token, token)}

    profile_id = str(profile.get("profile_id", "") or "").strip()
    profile_id_lc = profile_id.lower()
    type_slug_filter = str(profile.get("type_slug_filter", "") or "").strip().lower()
    evidence_mode = bool(profile.get("evidence_mode", False))
    cohort_gates = profile.get("cohort_gates") if isinstance(profile.get("cohort_gates"), dict) else {}
    dataset_filters = profile.get("dataset_filters") if isinstance(profile.get("dataset_filters"), dict) else {}
    paper_lock = profile.get("paper_lock") if isinstance(profile.get("paper_lock"), dict) else {}
    expected_type_scope = str(paper_lock.get("expected_type_scope", "") or "").strip().lower()
    min_samples_per_family = cohort_gates.get("min_samples_per_family")
    dataset_mode = str(dataset_filters.get("mode", "") or "").strip().lower()

    def _mapped(bucket: str, reason: str) -> Dict[str, str | None]:
        return {
            "status": "mapped",
            "bucket": bucket,
            "summary": f"Best matching readiness bucket: {bucket}",
            "detail": f"{reason} Advisory only; this does not enforce sample selection.",
            "ambiguity_reason": None,
        }

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
        "research_all_malicious",
        "all_malicious",
        "malicious_temporal_stability",
        "malicious_temporal_stability_locked",
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


def inventory_cohort_readiness_mappings(*, include_hidden: bool = True) -> List[Dict[str, Any]]:
    """Return advisory cohort-readiness mapping inventory for bundled profiles."""
    paths = sorted(PROFILES_DIR.glob("*.yaml"))
    if not include_hidden:
        paths = [path for path in paths if path.stem not in HIDDEN_PROFILE_IDS]

    inventory: list[dict[str, Any]] = []
    for profile_path in paths:
        profile = load_profile(str(profile_path))
        signal = infer_cohort_readiness_signal(profile)
        inventory.append(
            {
                "profile_id": str(profile.get("profile_id", profile_path.stem) or profile_path.stem),
                "profile_path": str(profile_path.as_posix()),
                "description": str(profile.get("description", "") or "").strip(),
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
    """Prompt a concise profile menu for common run paths.

    This keeps the primary UX focused on day-to-day profiles and allows
    explicit opt-in to the full advanced profile catalog when needed.
    """
    return profile_selection.select_profile_interactive_quick(
        list_profiles_fn=list_profiles,
        load_profile_fn=load_profile,
        select_profile_interactive_fn=select_profile_interactive,
        breadcrumb=breadcrumb,
        subtitle=subtitle,
        title=title,
        exit_label=exit_label,
    )
