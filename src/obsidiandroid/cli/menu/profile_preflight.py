"""Profile selection and preflight validation for startup menu."""

from __future__ import annotations

from obsidiandroid.orchestration.profile_filters import split_benign_malicious
from config import app_config
from obsidiandroid.database import db_sample_metadata_fetchers
from obsidiandroid.cli.ui import display as du
from obsidiandroid.observability.logging import get_logger, log_event
import obsidiandroid.cli.profile_manager as profile_manager

MENU_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.menu.profile_preflight",
    "menu",
)


def resolve_profile_for_run(
    *,
    prefer_quick: bool = False,
    menu_breadcrumb: str | None = None,
    menu_subtitle: str | None = None,
    menu_title: str | None = None,
) -> str | None:
    """Resolve execution profile interactively."""
    title = menu_title or "Execution profile"
    if prefer_quick:
        return profile_manager.select_profile_interactive_quick(
            breadcrumb=menu_breadcrumb,
            subtitle=menu_subtitle,
            title=title,
        )
    return profile_manager.select_profile_interactive(
        breadcrumb=menu_breadcrumb,
        subtitle=menu_subtitle,
        title=title,
    )


def validate_profile_runnable(profile_id: str) -> tuple[bool, str]:
    """Preflight profile viability to prevent avoidable runtime crashes."""
    try:
        profile = profile_manager.load_profile(profile_id)
    except Exception as exc:
        return False, f"[PROFILE] Failed to load profile '{profile_id}': {exc}"

    gates = profile.get("cohort_gates", {}) if isinstance(profile, dict) else {}
    dataset_filters = profile.get("dataset_filters", {}) if isinstance(profile, dict) else {}
    mode = str(dataset_filters.get("mode", "none") or "none").strip().lower()
    type_slug = profile.get("type_slug_filter")
    min_support = int(gates.get("min_samples_per_family", 3))
    # SQL cohort loader now supports min_samples_per_family even when type_slug_filter is unset.

    if mode in {"none", "", "malicious_only"}:
        # Fast/silent preflight for standard malicious-only profiles.
        # We only need to know whether at least one row survives profile gates.
        sample_probe_df = db_sample_metadata_fetchers.fetch_samples_by_type(
            type_slug=type_slug,
            min_samples_per_family=min_support,
            require_mapped_family=bool(gates.get("require_mapped_family", True)),
            require_sha256=bool(gates.get("require_sha256", True)),
            allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
            limit=1,
            as_dataframe=True,
        )
        if sample_probe_df is None or sample_probe_df.empty:
            return False, f"[PROFILE] Profile '{profile_id}' selected an empty cohort."
        return True, ""

    # Mixed-mode profiles need partition counts, so we still load the gated cohort.
    # Use the lower-level fetch path to avoid noisy preflight terminal banners.
    samples_df = db_sample_metadata_fetchers.fetch_samples_by_type(
        type_slug=type_slug,
        min_samples_per_family=min_support,
        require_mapped_family=bool(gates.get("require_mapped_family", True)),
        require_sha256=bool(gates.get("require_sha256", True)),
        allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
        limit=gates.get("limit", None),
        as_dataframe=True,
    )
    if samples_df is None or samples_df.empty:
        return False, f"[PROFILE] Profile '{profile_id}' selected an empty cohort."

    benign_df, malicious_df = split_benign_malicious(samples_df)
    benign_count = len(benign_df)
    malicious_count = len(malicious_df)
    min_partition_size = int(dataset_filters.get("min_partition_size", 1))

    if mode == "mixed_balanced":
        if benign_count == 0 or malicious_count == 0:
            return (
                False,
                f"[PROFILE] '{profile_id}' requires benign+malicious partitions "
                f"(benign={benign_count}, malicious={malicious_count}).",
            )
        if min(benign_count, malicious_count) < min_partition_size:
            return (
                False,
                f"[PROFILE] '{profile_id}' insufficient partition size "
                f"(benign={benign_count}, malicious={malicious_count}, min={min_partition_size}).",
            )
        return True, ""

    if mode == "benign_heavy":
        if benign_count == 0 or malicious_count == 0:
            return (
                False,
                f"[PROFILE] '{profile_id}' requires benign+malicious partitions "
                f"(benign={benign_count}, malicious={malicious_count}).",
            )
        if benign_count < min_partition_size:
            return (
                False,
                f"[PROFILE] '{profile_id}' benign partition below minimum "
                f"(benign={benign_count}, min={min_partition_size}).",
            )
        return True, ""

    return True, ""


def resolve_and_validate_profile(
    *,
    prefer_quick: bool = False,
    menu_breadcrumb: str | None = None,
    menu_subtitle: str | None = None,
    menu_title: str | None = None,
) -> str | None:
    """Interactive profile selection with preflight validation."""
    while True:
        profile_id = resolve_profile_for_run(
            prefer_quick=prefer_quick,
            menu_breadcrumb=menu_breadcrumb,
            menu_subtitle=menu_subtitle,
            menu_title=menu_title,
        )
        if not profile_id:
            return None

        du.print_info("[PROFILE] Preflight: verifying cohort against the database (quick check)...")
        ok, reason = validate_profile_runnable(profile_id)
        if ok:
            log_event(MENU_LOGGER, "profile_preflight_passed", profile_id=profile_id)
            return profile_id

        du.print_warning(reason)
        du.print_info("[MENU] Select a different profile or adjust profile dataset filters.")
        log_event(
            MENU_LOGGER,
            "profile_preflight_failed",
            profile_id=profile_id,
            reason=reason,
        )
