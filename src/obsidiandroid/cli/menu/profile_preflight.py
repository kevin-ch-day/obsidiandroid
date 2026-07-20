"""Profile selection and preflight validation for startup menu."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from mysql.connector import Error as MySQLError

from obsidiandroid.orchestration.profile_filters import split_benign_malicious
from config import app_config
from obsidiandroid.common.authority_taxonomy_terms import (
    live_taxonomy_backlog_detail,
    policy_held_only_note,
)
from obsidiandroid.common.backlog_semantics import build_taxonomy_curation_posture
from obsidiandroid.database import db_sample_metadata_fetchers
from obsidiandroid.database.db_engine import SourceDatabaseConfigurationError
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot
from obsidiandroid.governance.cohort_lock_manifest import (
    load_lock_manifest,
    read_member_list,
    validate_lock_manifest,
)
from obsidiandroid.governance.support_floor_policy import resolve_membership_min_samples_per_family
from obsidiandroid.pipeline.sample_exports import resolve_dataset_time_contract
from obsidiandroid.cli.menu.readiness_notes import (
    build_observed_readiness_note,
    build_permission_obs_gap_note,
)
from obsidiandroid.cli.ui import display as du
from obsidiandroid.observability.logging import get_logger, log_event
import obsidiandroid.cli.profile_manager as profile_manager
from obsidiandroid.cli.profile_selection import quick_profile_label

MENU_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.menu.profile_preflight",
    "menu",
)


def _source_preflight_failure(exc: BaseException) -> tuple[bool, str]:
    """Return an operator-safe, actionable message for expected source DB failures."""
    if isinstance(exc, SourceDatabaseConfigurationError):
        detail = str(exc).lower()
        if "administrator" in detail:
            cause = "The administrator credential is blocked for normal pipeline use."
        elif "option file" in detail:
            cause = "The configured private source option file is unavailable or not mode 0600."
        else:
            cause = "Normal Erebus or Permission Intel source configuration is missing."
    elif isinstance(exc, MySQLError):
        errno = int(getattr(exc, "errno", 0) or 0)
        if errno in {1045, 1698}:
            cause = "Source authentication failed."
        elif errno in {1044, 1142, 1227}:
            cause = "The configured source account lacks required SELECT access."
        elif errno == 1146:
            cause = "A required normal-analysis source table or view is missing."
        else:
            cause = "The normal source connection or query failed."
    else:
        cause = "The normal source configuration or connection failed."
    return (
        False,
        "[PROFILE] "
        + cause
        + " Configure OBSIDIAN_DB_* or OBSIDIAN_DB_OPTION_FILE, then retry. "
        + "The restricted Phase 2C Erebus reader is not a normal pipeline credential. "
        + "Historical menu counts can still describe the latest local run while live source connectivity is unavailable.",
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


_READINESS_SCOPE_LABELS = {
    "android_banker_with_permission_obs": "Android banker malware · permission observations",
    "android_high_or_strong_vt_with_permission_obs": (
        "Android malware · high/strong AV · permission observations"
    ),
    "android_with_permission_obs": "Android malware · permission observations",
    "android_family_ready_min3_permission_obs": (
        "Android family classification · permission observations"
    ),
    "android_platform": "All Android catalog records",
    "all_catalog": "All catalog records",
}


def _readiness_scope_block(
    readiness_signal: dict[str, object],
    *,
    paper_locked: bool,
) -> tuple[str, list[str]]:
    """Render a brief operator-facing explanation without internal bucket jargon."""
    bucket = str(readiness_signal.get("bucket", "") or "").strip()
    label = _READINESS_SCOPE_LABELS.get(bucket)
    if not label:
        summary = str(readiness_signal.get("summary", "") or "").strip()
        detail = str(readiness_signal.get("detail", "") or "").strip()
        return summary, _profile_detail_lines(detail)

    lines = ["Cohort gates determine membership."]
    if "permission_obs" in bucket:
        lines.append("Checked during the run, not by this menu.")
    if paper_locked:
        lines.append("Refresh the lock to change membership.")
    return f"Readiness scope: {label}", lines


def _print_profile_readiness_summary(
    *,
    profile_id: str,
    readiness_headline: str,
    readiness_lines: list[str],
) -> None:
    """Render selection context as aligned operator fields, not log fragments."""
    scope = readiness_headline.removeprefix("Readiness scope:").strip() or readiness_headline
    labels = {
        "Cohort gates determine membership.": "Cohort membership",
        "Checked during the run, not by this menu.": "Permission coverage",
        "Refresh the lock to change membership.": "Locked cohort",
    }
    du.print_subheader("Selected profile")
    du.print_stat("Name", quick_profile_label(profile_id), width=20)
    du.print_stat("Profile ID", profile_id, width=20)
    du.print_stat("Readiness scope", scope, width=20)
    for line in readiness_lines:
        du.print_stat(labels.get(line, "Note"), line, width=20)
    print("")


def _print_current_source_coverage(note: str) -> None:
    """Render the current readiness snapshot as a compact aligned block."""
    headline, lines = _observed_note_lines(note)
    if not headline.startswith("Observed readiness for `"):
        _print_profile_block(headline, *lines)
        return
    du.print_subheader("Current Android Catalog Coverage")
    for line in lines:
        key, separator, value = line.partition("=")
        if separator:
            du.print_stat(key.replace("_", " ").title(), value, width=20)
        else:
            du.print_stat("Detail", line, width=20)
    print("")


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


def _profile_menu_latest_run_context(output_root: Path | None = None) -> list[tuple[str, str]]:
    """Build concise context from one canonical latest-run artifact.

    Profile selection must remain responsive, so this avoids a live-database
    query.  It also must not combine a latest-run pointer with a summary from
    another slot merely because that file was written more recently.
    """
    root = output_root or Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    pointer_path = root / "diagnostics" / "latest_run_pointer.json"
    pointer_run_id = ""
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if isinstance(pointer, dict):
            pointer_run_id = str(pointer.get("run_id", "")).strip()
    except (OSError, json.JSONDecodeError):
        pass

    candidates = list(root.glob("runs/*/diagnostics/run_observability_summary.json"))
    if pointer_run_id:
        candidates = [
            path
            for path in candidates
            if _summary_run_id(path) == pointer_run_id
        ]
        if not candidates:
            return [
                ("LAST RUN STATUS", "Summary unavailable"),
                ("INFO", f"Canonical run: {pointer_run_id}"),
            ]
    if not candidates:
        return []
    summary_path = max(candidates, key=lambda path: path.stat().st_mtime)
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []

    status = str(payload.get("run_status") or payload.get("pipeline_status") or "unknown").title()
    prepared = payload.get("cohort_prepared_row_count")
    trainable = payload.get("post_low_support_training_rows")
    visible_families = payload.get("visible_family_count")
    modeled_families = payload.get("modeled_family_class_count")
    support_floor_families = payload.get("benchmark_trainable_family_count")

    claim_surface = str(payload.get("claim_surface") or "").replace("_", " ").strip()
    status_text = status if not claim_surface else f"{status} · {claim_surface}"
    context: list[tuple[str, str]] = [("LAST RUN STATUS", status_text)]
    if isinstance(prepared, int):
        prepared_text = f"Latest cohort: {prepared:,} prepared samples"
        if isinstance(trainable, int):
            context.append(("INFO", prepared_text))
            context.append(("INFO", f"Training-eligible samples: {trainable:,}"))
        else:
            context.append(("INFO", prepared_text))
    if isinstance(visible_families, int):
        family_text = f"Family coverage: {visible_families:,} visible"
        if isinstance(modeled_families, int):
            family_text += f" · {modeled_families:,} modeled"
        context.append(("INFO", family_text))

    support_preview_path = summary_path.parent / "support_threshold_preview.csv"
    preview_floor_families = _support_preview_family_count(support_preview_path, threshold=3)
    conservative_families = _support_preview_family_count(support_preview_path, threshold=20)
    if not isinstance(support_floor_families, int):
        support_floor_families = preview_floor_families
    if isinstance(support_floor_families, int) or conservative_families is not None:
        support_text = "Support thresholds (preview):"
        preview_parts: list[str] = []
        if isinstance(support_floor_families, int):
            preview_parts.append(f"n>=3: {support_floor_families:,} families")
        if conservative_families is not None:
            preview_parts.append(f"n>=20: {conservative_families:,} families")
        context.append(("INFO", support_text + " " + " · ".join(preview_parts)))
    return context


def _summary_run_id(path: Path) -> str:
    """Return a summary run ID without raising during interactive rendering."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("run_id", "")).strip() if isinstance(payload, dict) else ""


def _support_preview_family_count(path: Path, *, threshold: int) -> int | None:
    """Read one family-count value from a run-local support preview safely."""
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if int(str(row.get("min_support_threshold", "")).strip()) != threshold:
                    continue
                return int(str(row.get("retained_families", "")).strip())
    except (OSError, ValueError, TypeError, csv.Error):
        return None
    return None


def resolve_profile_for_run(
    *,
    prefer_quick: bool = False,
    menu_breadcrumb: str | None = None,
    menu_subtitle: str | None = None,
    menu_context_lines: list[tuple[str, str]] | None = None,
    menu_title: str | None = None,
) -> str | None:
    """Resolve execution profile interactively."""
    title = menu_title or "Execution profile"
    if prefer_quick:
        return profile_manager.select_profile_interactive_quick(
            breadcrumb=menu_breadcrumb,
            subtitle=menu_subtitle,
            context_lines=menu_context_lines,
            title=title,
        )
    return profile_manager.select_profile_interactive(
        breadcrumb=menu_breadcrumb,
        subtitle=menu_subtitle,
        context_lines=menu_context_lines,
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
    require_active_type_slug = bool(gates.get("require_active_type_slug", False))
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
    exclude_family_ids = tuple(
        int(family_id)
        for family_id in (gates.get("exclude_family_ids", []) or [])
        if str(family_id).strip()
    )
    # Keep readiness counts on exactly the same temporal contract as the
    # samples stage. Non-evidence profiles without explicit bounds still
    # inherit the global reproducibility window.
    time_contract = resolve_dataset_time_contract(
        gates=gates,
        run_id=f"profile_preflight_{profile_id}",
    )
    effective_time_start_utc = time_contract.get("start_utc")
    effective_time_end_utc = time_contract.get("end_utc")
    require_effective_first_seen = bool(time_contract.get("require_effective_first_seen", True))
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
        # Forward the same profile gate contract as the samples stage, but use
        # a bounded viability probe instead of an exact governed-cohort census.
        try:
            viability = db_sample_metadata_fetchers.probe_profile_cohort_viability(
                type_slug=type_slug,
                min_samples_per_family=min_support,
                require_mapped_family=bool(gates.get("require_mapped_family", True)),
                require_sha256=bool(gates.get("require_sha256", True)),
                allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
                exclude_unknown_type_slug=exclude_unknown_type_slug,
                require_active_type_slug=require_active_type_slug,
                exclude_weak_label_kinds=exclude_weak_label_kinds,
                exclude_family_label_conflicts=exclude_family_label_conflicts,
                effective_time_start_utc=effective_time_start_utc,
                effective_time_end_utc=effective_time_end_utc,
                require_effective_first_seen=require_effective_first_seen,
                include_family_canonical=include_families,
                exclude_family_ids=exclude_family_ids,
                exclude_family_canonical=exclude_families,
            )
        except (SourceDatabaseConfigurationError, MySQLError) as exc:
            return _source_preflight_failure(exc)
        if bool(viability.get("timed_out", False)):
            return (
                False,
                "[PROFILE] Bounded cohort viability check timed out; no pipeline was started. "
                "Run the explicit cohort diagnostics before retrying this profile.",
            )
        if not bool(viability.get("runnable", False)):
            if str(viability.get("reason_code", "")) in {
                "inconclusive_candidate_window",
                "inconclusive_quality_gate",
                "inconclusive_authority_surface",
            }:
                return (
                    False,
                    "[PROFILE] Bounded cohort viability check was inconclusive; no pipeline was started. "
                    "Run the explicit cohort diagnostics before retrying this profile.",
                )
            return False, f"[PROFILE] Profile '{profile_id}' selected an empty cohort."
        return True, ""

    # Mixed-mode profiles need partition counts, so we still load the gated cohort.
    # Use the lower-level fetch path to avoid noisy preflight terminal banners.
    try:
        samples_df = db_sample_metadata_fetchers.fetch_samples_by_type(
            type_slug=type_slug,
            min_samples_per_family=min_support,
            require_mapped_family=bool(gates.get("require_mapped_family", True)),
            require_sha256=bool(gates.get("require_sha256", True)),
            allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
            exclude_unknown_type_slug=exclude_unknown_type_slug,
            require_active_type_slug=require_active_type_slug,
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
            exclude_family_ids=exclude_family_ids,
            exclude_family_canonical=exclude_families,
            as_dataframe=True,
        )
    except (SourceDatabaseConfigurationError, MySQLError) as exc:
        return _source_preflight_failure(exc)
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
    effective_menu_subtitle = (
        menu_subtitle
        if menu_subtitle is not None
        else None
    )
    effective_menu_context_lines = (
        None
        if menu_subtitle is not None
        else _profile_menu_latest_run_context()
    )
    persistence_mode = str(getattr(app_config, "RESULTS_PERSISTENCE_MODE", "read_only")).strip()
    warehouse_enabled = bool(getattr(app_config, "ENABLE_RESULTS_WAREHOUSE_EXPORT", False))
    print(
        "[PROFILE] Persistence mode: "
        f"{persistence_mode} (legacy Erebus warehouse export {'enabled' if warehouse_enabled else 'disabled'}; "
        "Core persistence disabled unless separately enabled)."
    )
    while True:
        profile_id = resolve_profile_for_run(
            prefer_quick=prefer_quick,
            menu_breadcrumb=menu_breadcrumb,
            menu_subtitle=effective_menu_subtitle,
            menu_context_lines=effective_menu_context_lines,
            menu_title=menu_title,
        )
        if not profile_id:
            return None

        readiness_signal = profile_manager.infer_cohort_readiness_signal(profile_id)
        readiness_snapshot = None
        paper_locked = False
        try:
            profile_payload = profile_manager.load_profile(profile_id)
        except Exception:
            profile_payload = {}
        if isinstance(profile_payload, dict):
            paper_locked = bool(profile_payload.get("paper_locked", False))
        readiness_headline, readiness_lines = _readiness_scope_block(
            readiness_signal,
            paper_locked=paper_locked,
        )
        if readiness_headline:
            _print_profile_readiness_summary(
                profile_id=profile_id,
                readiness_headline=readiness_headline,
                readiness_lines=readiness_lines,
            )
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
            _print_current_source_coverage(observed_note)
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
