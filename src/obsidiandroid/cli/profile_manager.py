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


def _build_profile_catalog(profiles: List[Path]) -> List[tuple[str, str]]:
    """Build ordered profile summaries for interactive menu presentation."""
    return profile_selection.build_profile_catalog(profiles)


def _profile_sort_key(profile_id: str) -> tuple[int, int, str]:
    """Return deterministic profile ordering for a cleaner selection menu."""
    return profile_selection.profile_sort_key(profile_id)


def _summarize_profile(profile_path: Path) -> str:
    """Generate concise profile summary for menu display."""
    return profile_selection.summarize_profile(profile_path)
