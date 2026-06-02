"""Interactive profile selection helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from obsidiandroid.cli.ui import display as du
from obsidiandroid.cli.ui import menu as mu

_FINAL_PROFILE_IDS = {
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
}


def _print_profile_selection(message: str) -> None:
    """Emit compact profile-selection lines without generic severity wrappers."""
    print(f"[PROFILE] {str(message).strip()}")


def build_profile_catalog(profiles: list[Path]) -> list[tuple[str, str]]:
    """Build ordered profile summaries for interactive menu presentation."""
    entries: list[tuple[str, str]] = []
    for profile_path in profiles:
        profile_id = profile_path.stem
        summary = summarize_profile(profile_path)
        entries.append((profile_id, summary))

    entries.sort(key=lambda item: profile_sort_key(item[0]))
    return entries


def profile_sort_key(profile_id: str) -> tuple[int, int, str]:
    """Return deterministic profile ordering for a cleaner selection menu."""
    pid = str(profile_id).strip().lower()
    if pid == "android_malware_all_current":
        return (0, 0, pid)
    if pid == "android_malware_major_families":
        return (0, 1, pid)
    if pid == "android_malware_expanded_families":
        return (1, 0, pid)
    if pid == "android_malware_type_taxonomy":
        return (1, 1, pid)
    if pid == "malicious_temporal_stability_locked":
        return (2, 0, pid)
    if pid == "banker_locked":
        return (2, 1, pid)
    if pid == "malicious_temporal_stability":
        return (3, 0, pid)
    if pid == "malicious_temporal_stability_long_tail":
        return (3, 1, pid)
    if pid == "malicious_temporal_stability_expanded":
        return (3, 2, pid)
    if pid in {"malicious_temporal_consensus10", "malicious_temporal_family300"}:
        return (4, 0, pid)
    if pid == "banker":
        return (5, 0, pid)
    if pid in {"mixed", "benign_heavy"}:
        diagnostic_order = {"mixed": 0, "benign_heavy": 1}
        return (6, diagnostic_order[pid], pid)
    if pid == "dev_fast":
        return (7, 0, pid)
    if pid == "dev_smoke":
        return (7, 1, pid)

    return (3, 0, pid)


def summarize_profile(profile_path: Path) -> str:
    """Generate concise profile summary for menu display."""
    try:
        with open(profile_path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except Exception:
        return "summary unavailable"

    profile_id = str(raw.get("profile_id", profile_path.stem) or profile_path.stem)
    desc = str(raw.get("description", "")).strip()
    type_slug = raw.get("type_slug_filter")
    gates = raw.get("cohort_gates", {}) if isinstance(raw.get("cohort_gates"), dict) else {}
    models = raw.get("model_list", []) if isinstance(raw.get("model_list"), list) else []
    paper_lock = raw.get("paper_lock", {}) if isinstance(raw.get("paper_lock"), dict) else {}
    paper_locked = bool(raw.get("paper_locked", False))
    status_label = _profile_status_label(raw, profile_id)
    parts: list[str] = []

    if type_slug:
        parts.append(f"type={type_slug}")
    else:
        parts.append("type=all")

    if paper_locked:
        lock_mode = "membership-locked" if str(paper_lock.get("sample_id_lock_file", "")).strip() else "count-only"
        parts.append(f"lock={lock_mode}")
    elif profile_id.startswith("paper") or bool(raw.get("evidence_mode", False)):
        parts.append("publication=unlocked")

    min_detect = gates.get("min_malicious_detections", None)
    if min_detect is not None:
        parts.append(f"min_detect={min_detect}")

    family_cap = gates.get("family_cap", None)
    if family_cap:
        parts.append(f"family_cap={family_cap}")
    type_cap = gates.get("type_cap", None)
    if type_cap:
        parts.append(f"type_cap={type_cap}")

    exclude_unknown = gates.get("exclude_unknown_type_slug", None)
    if exclude_unknown is not None:
        parts.append(f"exclude_unknown={bool(exclude_unknown)}")

    if models:
        parts.append(f"models={len(models)}")

    summary = ", ".join(parts)
    headline = ""
    if desc:
        desc_short = desc if len(desc) <= 72 else f"{desc[:69]}..."
        headline = f"{status_label}: {desc_short}" if status_label else desc_short
    elif status_label:
        headline = status_label

    if headline:
        return f"{headline} | {summary}"
    return summary


def quick_profile_label(profile_id: str) -> str:
    """Return operator-facing quick-menu labels without exposing raw profile IDs as the main cue."""
    pid = str(profile_id).strip()
    labels = {
        "android_malware_all_current": "Research: all current Android malware",
        "android_malware_major_families": "Research: major-family classification",
        "android_malware_expanded_families": "Research: expanded family classification",
        "android_malware_type_taxonomy": "Research: type-level taxonomy",
        "malicious_temporal_consensus10": "Sensitivity: consensus threshold",
        "malicious_temporal_family300": "Sensitivity: family dominance cap",
        "malicious_temporal_stability_locked": "Reproducibility: locked 2026 paper benchmark",
        "banker_locked": "Reproducibility: banker count-locked benchmark",
        "malicious_temporal_stability": "Research: governed major-family baseline",
        "malicious_temporal_stability_expanded": "Research: governed expanded baseline",
        "malicious_temporal_stability_long_tail": "Research: governed long-tail baseline",
        "banker": "Research: banker-focused baseline",
        "mixed": "Diagnostic: balanced benign-malicious",
        "benign_heavy": "Diagnostic: benign-heavy robustness",
        "dev_fast": "Development: fast iteration",
        "dev_smoke": "Smoke: sanity check",
    }
    return labels.get(pid, pid)


def _profile_status_label(raw: dict[str, object], profile_id: str) -> str:
    """Return a short lifecycle label for full-catalog displays."""
    status = raw.get("profile_status") if isinstance(raw.get("profile_status"), dict) else {}
    status_label = str(status.get("status_label", "") or "").strip()
    if status_label:
        return status_label

    pid = str(profile_id).strip().lower()
    if pid in _FINAL_PROFILE_IDS and pid.startswith("dev_"):
        return "Dev-only supported"
    if pid in _FINAL_PROFILE_IDS:
        return "Final canonical"
    return ""


def _quick_intent_options() -> list[tuple[str, str]]:
    """Return the fixed operator-facing intent menu."""
    return [
        ("Current Android malware — all samples", "android_malware_all_current"),
        ("Major-family Android malware classification", "android_malware_major_families"),
        ("Expanded Android malware — major + minor families", "android_malware_expanded_families"),
        ("Type-level / coarse taxonomy classification", "android_malware_type_taxonomy"),
        ("Robustness and perturbation suite", "__submenu_robustness__"),
        ("Development / smoke checks", "__submenu_development__"),
    ]


def _robustness_submenu_options() -> list[tuple[str, str]]:
    """Return the fixed robustness submenu."""
    return [
        ("Sensitivity: consensus threshold", "malicious_temporal_consensus10"),
        ("Sensitivity: family dominance cap", "malicious_temporal_family300"),
    ]


def _development_submenu_options() -> list[tuple[str, str]]:
    """Return the fixed development submenu."""
    return [
        ("Development: fast iteration", "dev_fast"),
        ("Smoke: sanity check", "dev_smoke"),
    ]


def _select_fixed_profile_menu(
    *,
    options: list[tuple[str, str]],
    load_profile_fn: Callable[[str], dict],
    title: str,
    breadcrumb: str | None,
    exit_label: str,
) -> str | None:
    """Render a fixed menu and return the selected canonical profile id."""
    labels = [label for label, _ in options]
    while True:
        choice = mu.display_menu(
            labels,
            title=title,
            breadcrumb=breadcrumb,
            exit_label=exit_label,
            default_choice=1,
        )
        if choice == 0:
            return None

        selected_profile_id = options[choice - 1][1]
        try:
            load_profile_fn(selected_profile_id)
        except Exception as exc:
            du.print_error(f"[PROFILE] Selected profile is invalid: {exc}")
            continue

        _print_profile_selection(f"Selected: {selected_profile_id}")
        return selected_profile_id


def select_profile_interactive(
    *,
    list_profiles_fn: Callable[[], list[Path]],
    load_profile_fn: Callable[[str], dict],
    breadcrumb: str | None = None,
    subtitle: str | None = None,
    title: str = "Execution profile",
    exit_label: str = "Back",
) -> str | None:
    """Prompt user to select a profile id with richer context."""
    profiles = list_profiles_fn()
    if not profiles:
        du.print_error("[PROFILE] No profiles found in ./profiles.")
        return None
    catalog = build_profile_catalog(profiles)
    if not catalog:
        du.print_error("[PROFILE] No valid profiles found in ./profiles.")
        return None

    labels = [
        f"{profile_id} | {summary}" if summary else profile_id
        for profile_id, summary in catalog
    ]
    labels.append("Enter profile id manually")

    choice = mu.display_menu(
        labels,
        title=title,
        breadcrumb=breadcrumb,
        subtitle=subtitle,
        exit_label=exit_label,
    )
    if choice == 0:
        return None

    selected_label = labels[choice - 1]
    if selected_label == "Enter profile id manually":
        try:
            entered = input("Enter profile id (e.g., malicious_temporal_stability_locked): ").strip()
        except KeyboardInterrupt:
            du.print_warning("[PROFILE] Selection cancelled by user (Ctrl+C).")
            return None
        if not entered:
            return None
        try:
            load_profile_fn(entered)
            return entered
        except Exception as exc:
            du.print_error(f"[PROFILE] Invalid profile reference: {exc}")
            return None

    selected_index = choice - 1
    if selected_index < len(catalog):
        return catalog[selected_index][0]
    return selected_label


def select_profile_interactive_quick(
    *,
    list_profiles_fn: Callable[[], list[Path]],
    load_profile_fn: Callable[[str], dict],
    select_profile_interactive_fn: Callable[..., str | None],
    breadcrumb: str | None = None,
    subtitle: str | None = None,
    title: str = "Execution profile",
    exit_label: str = "Back",
) -> str | None:
    """Prompt an intent-first menu for common run paths."""
    del list_profiles_fn
    del select_profile_interactive_fn

    while True:
        options = _quick_intent_options()
        choice = mu.display_menu(
            [label for label, _ in options],
            title=title,
            breadcrumb=breadcrumb,
            subtitle=subtitle,
            exit_label=exit_label,
            default_choice=1,
        )
        if choice == 0:
            return None

        selected_label, selected_target = options[choice - 1]
        if selected_target == "__submenu_robustness__":
            resolved = _select_fixed_profile_menu(
                options=_robustness_submenu_options(),
                load_profile_fn=load_profile_fn,
                title="Robustness / perturbations",
                breadcrumb=f"{breadcrumb or title} › Robustness / perturbations",
                exit_label="Back",
            )
            if resolved is not None:
                return resolved
            continue
        if selected_target == "__submenu_development__":
            resolved = _select_fixed_profile_menu(
                options=_development_submenu_options(),
                load_profile_fn=load_profile_fn,
                title="Development / smoke checks",
                breadcrumb=f"{breadcrumb or title} › Development / smoke checks",
                exit_label="Back",
            )
            if resolved is not None:
                return resolved
            continue

        try:
            load_profile_fn(selected_target)
        except Exception as exc:
            du.print_error(f"[PROFILE] Selected profile is invalid: {exc}")
            continue

        _print_profile_selection(f"Selected: {selected_target}")
        return selected_target


__all__ = [
    "build_profile_catalog",
    "quick_profile_label",
    "profile_sort_key",
    "select_profile_interactive",
    "select_profile_interactive_quick",
    "summarize_profile",
]
