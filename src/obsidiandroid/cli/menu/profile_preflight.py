"""Profile selection and preflight validation for startup menu."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.orchestration.profile_filters import split_benign_malicious
from config import app_config
from obsidiandroid.common.authority_taxonomy_terms import (
    live_taxonomy_backlog_detail,
    policy_held_only_note,
)
from obsidiandroid.common.backlog_semantics import build_taxonomy_curation_posture
from obsidiandroid.database import db_sample_metadata_fetchers
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot
from obsidiandroid.governance.cohort_lock_manifest import (
    load_lock_manifest,
    read_member_list,
    validate_lock_manifest,
)
from obsidiandroid.governance.support_floor_policy import resolve_membership_min_samples_per_family
from obsidiandroid.cli.menu.readiness_notes import (
    build_observed_readiness_note,
    build_permission_obs_gap_note,
)
from obsidiandroid.cli.ui import display as du
from obsidiandroid.observability.logging import get_logger, log_event
import obsidiandroid.cli.profile_manager as profile_manager

MENU_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.menu.profile_preflight",
    "menu",
)


def _print_profile_block(headline: str, *detail_lines: str, blank_after: bool = False) -> None:
    """Print compact profile-selection lines without generic log-level wrappers."""
    print(f"[PROFILE] {str(headline).strip()}")
    for line in detail_lines:
        text = str(line or "").strip()
        if text:
            print(f"           {text}")
    if blank_after:
        print("")


def _split_sentences(text: str) -> list[str]:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in cleaned.split(". ") if part.strip()]
    out: list[str] = []
    for idx, part in enumerate(parts):
        if idx < len(parts) - 1 and not part.endswith("."):
            out.append(part + ".")
        else:
            out.append(part)
    return out


def _profile_detail_lines(detail: str) -> list[str]:
    return _split_sentences(detail)


def _observed_note_lines(note: str) -> tuple[str, list[str]]:
    text = " ".join(str(note or "").split()).strip()
    if not text:
        return "", []
    marker = ": samples="
    if marker in text and ", families=" in text:
        prefix, rest = text.split(marker, 1)
        sample_part, family_part = rest.split(", families=", 1)
        return f"{prefix}:", [f"samples={sample_part.strip()}", f"families={family_part.strip()}"]
    return text, []


def _gap_note_lines(note: str) -> tuple[str, list[str]]:
    parts = _split_sentences(note)
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _summarize_live_readiness_gaps(
    *,
    readiness: dict[str, object] | None,
    bucket: str | None,
    paper_locked: bool = False,
) -> list[str]:
    token = str(bucket or "").strip()
    snapshot = readiness if isinstance(readiness, dict) else {}
    buckets = snapshot.get("buckets", {}) if isinstance(snapshot, dict) else {}
    payload = buckets.get(token, {}) if isinstance(buckets, dict) else {}
    warnings = snapshot.get("warnings", []) if isinstance(snapshot, dict) else []
    taxonomy = snapshot.get("taxonomy_signals", {}) if isinstance(snapshot, dict) else {}

    out: list[str] = []
    permission_obs_note = build_permission_obs_gap_note(snapshot, token)
    if permission_obs_note:
        out.append(permission_obs_note)
    repair_candidate_count = int(taxonomy.get("repair_candidate_count") or 0)
    unresolved_family_count = int(taxonomy.get("unresolved_family_count") or 0)
    known_unresolved_count = int(taxonomy.get("known_unresolved_family_count") or 0)
    policy_held_count = int(taxonomy.get("policy_held_family_count") or 0)
    posture = build_taxonomy_curation_posture(readiness=snapshot)
    if repair_candidate_count > 0 or known_unresolved_count > 0 or policy_held_count > 0:
        detail = live_taxonomy_backlog_detail(
            repair_candidate_count=repair_candidate_count,
            known_unresolved_count=known_unresolved_count,
            policy_held_count=policy_held_count,
        )
        out.append(detail)
        if paper_locked:
            out.append(
                "This profile is locked, so new Erebus-side authority fixes may not change cohort membership until the lock is refreshed."
            )
        else:
            out.append(
                "New Erebus-side authority fixes may still sit outside this cohort unless the selected profile/snapshot absorbs them."
            )
    unresolved_family_count_value = taxonomy.get("unresolved_family_count")
    if unresolved_family_count_value is not None and unresolved_family_count == 0 and policy_held_count > 0:
        out.append(policy_held_only_note())
    curation_note = str(posture.get("note", "") or "").strip() or None
    if curation_note:
        out.append(curation_note)
    for warning in warnings[:2]:
        out.append(str(warning))
    return out


def _compact_profile_detail(detail: str, *, paper_locked: bool = False) -> str:
    text = " ".join(str(detail or "").split()).strip()
    if not text:
        return ""
    compact = text
    compact = compact.replace(
        "Android malicious evidence-style profile intent is best compared against the Android cohort with permission observations and high/strong VT confidence. ",
        "",
    )
    compact = compact.replace(
        "Advisory only; this does not enforce sample selection. ",
        "Advisory only; sample selection is not enforced. ",
    )
    compact = compact.replace(
        "Permission-observation wording is advisory here; bucket mapping does not verify or enforce PI observation materialization for the selected run. ",
        "Permission-observation wording is not verified/enforced for this run. ",
    )
    compact = compact.replace(
        "This profile is paper-locked; snapshot membership can prevent new DB curation or authority expansions from changing the cohort until the lock is refreshed.",
        "Locked benchmark cohort; new DB curation will not change membership until the lock is refreshed.",
    )
    if paper_locked and "Locked benchmark cohort" not in compact:
        compact = (
            f"{compact} Locked benchmark cohort; new DB curation will not change membership until the lock is refreshed."
        ).strip()
    return compact


def _paper_locked_follow_up_note(*, profile_id: str | None, paper_locked: bool = False) -> str | None:
    token = str(profile_id or "").strip()
    if not paper_locked or not token:
        return None
    return (
        "This run uses a locked benchmark cohort. Use the current-corpus profiles in "
        "`Run Analysis` when you want recent DB curation and authority repairs to affect membership immediately."
    )


def _merge_advisory_notes(*notes: str | None) -> str | None:
    """Combine short advisory notes into one operator-facing line."""
    parts = [str(note).strip() for note in notes if str(note or "").strip()]
    if not parts:
        return None
    return " ".join(parts)


def _compact_live_gap_lines(notes: list[str]) -> tuple[str, list[str]]:
    cleaned = [str(note).strip().rstrip(".") for note in notes if str(note).strip()]
    if not cleaned:
        return "", []
    preferred: list[str] = []
    for token in (
        "Live authority/taxonomy backlog",
        "This profile is locked",
        "Permission Intel observations include",
        "Taxonomy curation discipline",
        "Primary labels are raw-missing",
        "Live readiness mismatch",
        "Live readiness shows no true unresolved family slugs",
    ):
        for note in cleaned:
            if note.startswith(token) and note not in preferred:
                preferred.append(note)
    extras = [note for note in cleaned if note not in preferred]
    ordered = preferred + extras
    if len(ordered) > 3:
        ordered = ordered[:3]
    headline = ordered[0] + "."
    detail_lines = [note + "." for note in ordered[1:]]
    return headline, detail_lines


def _observed_readiness_note(
    bucket: str | None,
    *,
    readiness_snapshot: dict[str, object] | None = None,
) -> str | None:
    readiness = readiness_snapshot
    if not isinstance(readiness, dict):
        try:
            readiness = get_cohort_readiness_snapshot()
        except Exception as exc:
            return f"Observed readiness counts unavailable: {exc}"
    return build_observed_readiness_note(readiness, bucket)


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
    raw_lock = profile.get("paper_lock") if isinstance(profile.get("paper_lock"), dict) else {}
    paper_locked = bool(profile.get("paper_locked", False))
    mode = str(dataset_filters.get("mode", "none") or "none").strip().lower()
    type_slug = profile.get("type_slug_filter")
    min_support = resolve_membership_min_samples_per_family(gates)
    family_cap = gates.get("family_cap", None)
    family_cap_seed = gates.get("family_cap_seed", None)
    type_cap = gates.get("type_cap", None)
    type_cap_seed = gates.get("type_cap_seed", None)
    type_cap_by_slug = gates.get("type_cap_by_slug", None)
    evidence_mode = bool(profile.get("evidence_mode", False))
    exclude_unknown_type_slug = bool(gates.get("exclude_unknown_type_slug", False))
    exclude_weak_label_kinds = bool(gates.get("exclude_weak_label_kinds", False))
    exclude_family_label_conflicts = bool(gates.get("exclude_family_label_conflicts", False))
    if not exclude_unknown_type_slug:
        exclude_unknown_type_slug = evidence_mode
    exclude_families = tuple(
        str(family).strip().lower()
        for family in (gates.get("exclude_families", []) or [])
        if str(family).strip()
    )
    include_families = tuple(
        str(family).strip().lower()
        for family in (gates.get("include_families", []) or [])
        if str(family).strip()
    )
    effective_time_start_utc = str(gates.get("time_window_start_utc", "") or "").strip() or None
    effective_time_end_utc = str(gates.get("time_window_end_utc", "") or "").strip() or None
    require_effective_first_seen = bool(
        effective_time_start_utc or effective_time_end_utc or evidence_mode
    )
    if paper_locked:
        try:
            manifest = load_lock_manifest(raw_lock)
            if manifest is not None:
                validate_lock_manifest(manifest=manifest, manifest_path=Path(str(manifest.get("manifest_path", ""))))
                member_df = read_member_list(str(manifest.get("member_list_path", "") or ""))
                if member_df.empty:
                    return False, f"[PROFILE] Locked profile '{profile_id}' has an empty member-list lock."
                return True, ""
            lock_file = str(raw_lock.get("sample_id_lock_file", "") or "").strip()
            if lock_file:
                member_df = read_member_list(lock_file)
                if member_df.empty:
                    return False, f"[PROFILE] Locked profile '{profile_id}' has an empty sample-id lock."
                return True, ""
            return (
                False,
                f"[PROFILE] Locked profile '{profile_id}' is missing an immutable cohort lock manifest/member list.",
            )
        except Exception as exc:
            return False, f"[PROFILE] Locked profile '{profile_id}' lock validation failed: {exc}"
    # SQL cohort loader now supports min_samples_per_family even when type_slug_filter is unset.

    if mode in {"none", "", "malicious_only"}:
        # Fast/silent preflight for standard malicious-only profiles.
        # Use the same SQL gate summary path as the real samples stage so time-window,
        # unknown-type, and excluded-family gates do not get silently skipped here.
        gate_stats = db_sample_metadata_fetchers.get_type_cohort_gate_stats(
            type_slug=type_slug,
            min_samples_per_family=min_support,
            require_mapped_family=bool(gates.get("require_mapped_family", True)),
            require_sha256=bool(gates.get("require_sha256", True)),
            allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
            exclude_unknown_type_slug=exclude_unknown_type_slug,
            exclude_weak_label_kinds=exclude_weak_label_kinds,
            exclude_family_label_conflicts=exclude_family_label_conflicts,
            effective_time_start_utc=effective_time_start_utc,
            effective_time_end_utc=effective_time_end_utc,
            require_effective_first_seen=require_effective_first_seen,
            include_family_canonical=include_families,
            exclude_family_canonical=exclude_families,
        )
        governed_count = int(
            gate_stats.get("governed_cohort_count", gate_stats.get("final_count_estimate", 0)) or 0
        )
        if governed_count <= 0:
            return False, f"[PROFILE] Profile '{profile_id}' selected an empty cohort."

        # Lightweight materialization probe for the same governed SQL surface.
        sample_probe_df = db_sample_metadata_fetchers.fetch_samples_by_type(
            type_slug=type_slug,
            min_samples_per_family=min_support,
            require_mapped_family=bool(gates.get("require_mapped_family", True)),
            require_sha256=bool(gates.get("require_sha256", True)),
            allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
            exclude_unknown_type_slug=exclude_unknown_type_slug,
            exclude_weak_label_kinds=exclude_weak_label_kinds,
            exclude_family_label_conflicts=exclude_family_label_conflicts,
            effective_time_start_utc=effective_time_start_utc,
            effective_time_end_utc=effective_time_end_utc,
            require_effective_first_seen=require_effective_first_seen,
            include_family_canonical=include_families,
            exclude_family_canonical=exclude_families,
            limit=1,
            family_cap=family_cap,
            family_cap_seed=family_cap_seed,
            type_cap=type_cap,
            type_cap_seed=type_cap_seed,
            type_cap_by_slug=type_cap_by_slug,
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
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        limit=gates.get("limit", None),
        family_cap=family_cap,
        family_cap_seed=family_cap_seed,
        type_cap=type_cap,
        type_cap_seed=type_cap_seed,
        type_cap_by_slug=type_cap_by_slug,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_families,
        exclude_family_canonical=exclude_families,
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

        readiness_signal = profile_manager.infer_cohort_readiness_signal(profile_id)
        summary_text = str(readiness_signal.get("summary", "") or "").strip()
        if summary_text:
            _print_profile_block(summary_text)
        readiness_snapshot = None
        paper_locked = False
        try:
            profile_payload = profile_manager.load_profile(profile_id)
        except Exception:
            profile_payload = {}
        if isinstance(profile_payload, dict):
            paper_locked = bool(profile_payload.get("paper_locked", False))
        detail = _compact_profile_detail(
            str(readiness_signal.get("detail", "") or "").strip(),
            paper_locked=paper_locked,
        )
        locked_follow_up = _paper_locked_follow_up_note(
            profile_id=profile_id,
            paper_locked=paper_locked,
        )
        advisory_note = _merge_advisory_notes(detail, locked_follow_up)
        if advisory_note:
            detail_lines = _profile_detail_lines(advisory_note)
            if detail_lines:
                _print_profile_block(detail_lines[0], *detail_lines[1:], blank_after=True)
        try:
            readiness_snapshot = get_cohort_readiness_snapshot()
        except Exception:
            readiness_snapshot = None
        gap_headline, gap_lines = _compact_live_gap_lines(
            _summarize_live_readiness_gaps(
                readiness=readiness_snapshot,
                bucket=readiness_signal.get("bucket"),
                paper_locked=paper_locked,
            )
        )
        observed_note = _observed_readiness_note(
            readiness_signal.get("bucket"),
            readiness_snapshot=readiness_snapshot,
        )
        if observed_note and not (
            gap_headline
            and (
                "is unavailable in the live DB snapshot" in observed_note
                or "counts unavailable" in observed_note
            )
        ):
            observed_headline, observed_lines = _observed_note_lines(observed_note)
            _print_profile_block(observed_headline, *observed_lines)
        if gap_headline:
            _print_profile_block(gap_headline, *gap_lines, blank_after=True)
        try:
            inventory = profile_manager.inventory_cohort_readiness_mappings(
                include_hidden=False,
                profile_ids=list(getattr(profile_manager, "FINAL_OPERATOR_PROFILE_IDS", ())),
            )
        except Exception:
            inventory = []
        if inventory:
            mapped = sum(1 for row in inventory if str(row.get("status", "")).strip() == "mapped")
            unresolved = len(inventory) - mapped
            if unresolved > 0:
                _print_profile_block(
                    f"Readiness mapping inventory: {mapped} mapped, {unresolved} ambiguous.",
                    "Readiness mapping is advisory only; it does not enforce sample selection.",
                    blank_after=True,
                )

        _print_profile_block("Preflight: verifying cohort against the database (quick check)...")
        ok, reason = validate_profile_runnable(profile_id)
        if ok:
            log_event(
                MENU_LOGGER,
                "profile_preflight_passed",
                event_id="MENU_PREFLIGHT_200",
                profile_id=profile_id,
            )
            return profile_id

        du.print_warning(reason)
        print("[ACTION] Select a different profile or adjust profile dataset filters.")
        log_event(
            MENU_LOGGER,
            "profile_preflight_failed",
            event_id="MENU_PREFLIGHT_422",
            level="WARNING",
            profile_id=profile_id,
            reason=reason,
        )
