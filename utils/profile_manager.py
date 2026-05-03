"""Profile loading and validation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from utils import display_utils as du
from utils.ui import menu as mu

PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
REQUIRED_PROFILE_KEYS = {
    "profile_id",
    "type_slug_filter",
    "cohort_gates",
    "model_list",
}
REQUIRED_POLICY_KEYS = {
    "evidence_mode",
    "allow_vendor_fallback_for_width",
    "allow_adaptive_top_k",
    "top_k_requested",
    "exclude_unknown_from_main_results",
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
    return sorted(PROFILES_DIR.glob("*.yaml"))


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


def _apply_policy_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Apply policy defaults for backward-compatible profile loading."""
    out = dict(profile)
    out.setdefault("evidence_mode", False)
    out.setdefault("allow_vendor_fallback_for_width", True)
    out.setdefault("allow_adaptive_top_k", True)
    out.setdefault("top_k_requested", 8)
    out.setdefault("exclude_unknown_from_main_results", False)
    return out


def select_profile_interactive() -> str | None:
    """Prompt user to select a profile id with richer context."""
    profiles = list_profiles()
    if not profiles:
        du.print_error("[PROFILE] No profiles found in ./profiles.")
        return None
    catalog = _build_profile_catalog(profiles)
    if not catalog:
        du.print_error("[PROFILE] No valid profiles found in ./profiles.")
        return None

    menu_options: Dict[str, str] = {
        profile_id: profile_summary for profile_id, profile_summary in catalog
    }
    menu_options["Enter profile id manually"] = "Use typed profile id/path for direct selection."

    choice = mu.display_rich_menu(menu_options, title="Select Execution Profile")
    if choice == 0:
        return None

    selected_label = list(menu_options.keys())[choice - 1]
    if selected_label == "Enter profile id manually":
        try:
            entered = input("Enter profile id (e.g., paper2_primary): ").strip()
        except KeyboardInterrupt:
            du.print_warning("[PROFILE] Selection cancelled by user (Ctrl+C).")
            return None
        if not entered:
            return None
        try:
            # Validate manual entry early for better UX.
            load_profile(entered)
            return entered
        except Exception as exc:
            du.print_error(f"[PROFILE] Invalid profile reference: {exc}")
            return None

    return selected_label


def select_profile_interactive_quick() -> str | None:
    """Prompt a concise profile menu for common run paths.

    This keeps the primary UX focused on day-to-day profiles and allows
    explicit opt-in to the full advanced profile catalog when needed.
    """
    quick_order = [
        "research_all_malicious",
        "all_malicious",
        "banker",
        "mixed",
        "benign_heavy",
        "dev_fast",
        "dev_smoke",
    ]
    profiles = list_profiles()
    available = {p.stem: p for p in profiles}
    quick_entries: list[str] = []
    for profile_id in quick_order:
        profile_path = available.get(profile_id)
        if profile_path is None:
            continue
        quick_entries.append(profile_id)

    if not quick_entries:
        return select_profile_interactive()

    indexed_profiles: list[str] = []
    for profile_id in quick_entries:
        if profile_id.startswith("dev_"):
            continue
        indexed_profiles.append(profile_id)

    for profile_id in quick_entries:
        if not profile_id.startswith("dev_"):
            continue
        indexed_profiles.append(profile_id)

    advanced_idx = len(indexed_profiles) + 1

    du.print_subheader("Execution Profile")
    print("Press Enter for research_all_malicious.")
    for idx, profile_id in enumerate(indexed_profiles, 1):
        print(f"  [{idx}] {profile_id}")
    print(f"  [{advanced_idx}] advanced")
    print("  [0] Back\n")

    prompt = f"Enter selection [default=1, 0-{advanced_idx}]: "
    while True:
        try:
            raw = input(prompt).strip()
        except KeyboardInterrupt:
            du.print_warning("[PROFILE] Selection cancelled by user (Ctrl+C).")
            return None

        if raw == "":
            choice = 1
        else:
            try:
                choice = int(raw)
            except ValueError:
                du.print_warning("[PROFILE] Invalid input. Please enter a numeric selection.")
                continue

        if choice == 0:
            return None
        if choice == advanced_idx:
            return select_profile_interactive()
        if 1 <= choice <= len(indexed_profiles):
            selected = indexed_profiles[choice - 1]
            try:
                # Validate selected profile before returning so launch failures are
                # caught at selection time with a clear message.
                load_profile(selected)
            except Exception as exc:
                du.print_error(f"[PROFILE] Selected profile is invalid: {exc}")
                continue
            du.print_info(f"[PROFILE] Selected: {selected}")
            return selected
        du.print_warning("[PROFILE] Selection out of range. Try again.")


def _build_profile_catalog(profiles: List[Path]) -> List[tuple[str, str]]:
    """Build ordered profile summaries for interactive menu presentation."""
    entries: List[tuple[str, str]] = []
    for profile_path in profiles:
        profile_id = profile_path.stem
        summary = _summarize_profile(profile_path)
        entries.append((profile_id, summary))

    entries.sort(key=lambda item: _profile_sort_key(item[0]))
    return entries


def _profile_sort_key(profile_id: str) -> tuple[int, int, str]:
    """Return deterministic profile ordering for a cleaner selection menu."""
    pid = str(profile_id).strip().lower()
    if pid == "paper2_primary":
        return (0, 0, pid)
    if pid.startswith("paper2_sensitivity_"):
        return (1, 0, pid)

    core_order = {
        "research_all_malicious": 0,
        "all_malicious": 1,
        "banker": 2,
        "mixed": 3,
        "benign_heavy": 4,
    }
    if pid in core_order:
        return (2, core_order[pid], pid)

    if pid == "dev_fast":
        return (4, 0, pid)
    if pid == "dev_smoke":
        return (4, 1, pid)

    return (3, 0, pid)


def _summarize_profile(profile_path: Path) -> str:
    """Generate concise profile summary for menu display."""
    try:
        with open(profile_path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except Exception:
        return "summary unavailable"

    desc = str(raw.get("description", "")).strip()
    type_slug = raw.get("type_slug_filter")
    gates = raw.get("cohort_gates", {}) if isinstance(raw.get("cohort_gates"), dict) else {}
    models = raw.get("model_list", []) if isinstance(raw.get("model_list"), list) else []
    parts: List[str] = []

    if type_slug:
        parts.append(f"type={type_slug}")
    else:
        parts.append("type=all")

    min_detect = gates.get("min_malicious_detections", None)
    if min_detect is not None:
        parts.append(f"min_detect={min_detect}")

    family_cap = gates.get("family_cap", None)
    if family_cap:
        parts.append(f"family_cap={family_cap}")

    exclude_unknown = gates.get("exclude_unknown_type_slug", None)
    if exclude_unknown is not None:
        parts.append(f"exclude_unknown={bool(exclude_unknown)}")

    if models:
        parts.append(f"models={len(models)}")

    summary = ", ".join(parts)
    if desc:
        desc_short = desc if len(desc) <= 72 else f"{desc[:69]}..."
        return f"{desc_short} | {summary}"
    return summary
