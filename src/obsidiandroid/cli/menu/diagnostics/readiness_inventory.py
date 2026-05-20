"""Profile-readiness inventory rendering for the Data Diagnostics menu."""

from __future__ import annotations

import obsidiandroid.cli.profile_manager as profile_manager
from obsidiandroid.cli.ui import display as du
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot

_READINESS_BUCKET_MEANINGS: tuple[tuple[str, str], ...] = (
    ("all_catalog", "All catalog samples"),
    ("android_platform", "Android platform samples"),
    ("android_with_permission_obs", "Android samples with PI observations"),
    (
        "android_high_or_strong_vt_with_permission_obs",
        "Android + PI observations + high/strong VT confidence",
    ),
    (
        "android_labeled_primary_with_permission_obs",
        "Android + PI observations + primary class label",
    ),
    (
        "android_banker_with_permission_obs",
        "Android banker-labeled samples with PI observations",
    ),
    (
        "android_family_ready_min3_permission_obs",
        "Android + PI observations, family support >= 3",
    ),
)

_PROFILE_INTENT_GUIDE: tuple[str, ...] = (
    "Supported banker profiles -> android_banker_with_permission_obs",
    "Supported all-malicious and sensitivity profiles -> android_high_or_strong_vt_with_permission_obs",
    "Supported dev profiles are included for local/operator checks, not scientific benchmark interpretation.",
    "Deprecated exploratory and compatibility-alias profiles are intentionally excluded from this supported inventory view.",
)


def show_profile_readiness_mapping_inventory(
    *,
    profile_manager_module=profile_manager,
    get_cohort_readiness_snapshot_fn=get_cohort_readiness_snapshot,
    display_module=du,
) -> int:
    """Print bundled profile-to-readiness mapping inventory (advisory only)."""
    inventory = profile_manager_module.inventory_cohort_readiness_mappings(
        include_hidden=False,
        profile_ids=list(getattr(profile_manager_module, "FINAL_OPERATOR_PROFILE_IDS", ())),
    )
    if not inventory:
        display_module.print_warning("[MENU] No bundled profiles found for readiness mapping inventory.")
        return 1
    try:
        readiness = get_cohort_readiness_snapshot_fn()
    except Exception as exc:
        readiness = {
            "status": "degraded",
            "warnings": [f"Cohort readiness counts unavailable: {exc}"],
            "buckets": {},
        }

    bucket_rows: list[dict[str, object]] = []
    bucket_counts = readiness.get("buckets", {}) if isinstance(readiness, dict) else {}
    for bucket, meaning in _READINESS_BUCKET_MEANINGS:
        bucket_payload = bucket_counts.get(bucket, {}) if isinstance(bucket_counts, dict) else {}
        sample_count = bucket_payload.get("sample_count") if isinstance(bucket_payload, dict) else None
        family_count = bucket_payload.get("family_count") if isinstance(bucket_payload, dict) else None
        bucket_rows.append(
            {
                "bucket": bucket,
                "samples": sample_count if sample_count is not None else "unavailable",
                "families": family_count if family_count is not None else "unavailable",
                "meaning": meaning,
            }
        )

    display_module.print_table(
        bucket_rows,
        title="Readiness bucket summary",
        columns=["bucket", "samples", "families", "meaning"],
        show_index=False,
    )
    authority_source_mode = str(readiness.get("authority_source_mode", "") or "").strip() if isinstance(readiness, dict) else ""
    if authority_source_mode:
        display_module.print_stat("Authority source", authority_source_mode)

    rows: list[dict[str, object]] = []
    ambiguous_count = 0
    for entry in inventory:
        status = str(entry.get("status", "") or "ambiguous")
        if status != "mapped":
            ambiguous_count += 1
        bucket = str(entry.get("bucket", "") or "")
        bucket_payload = bucket_counts.get(bucket, {}) if isinstance(bucket_counts, dict) else {}
        sample_count = bucket_payload.get("sample_count") if isinstance(bucket_payload, dict) else None
        family_count = bucket_payload.get("family_count") if isinstance(bucket_payload, dict) else None
        rows.append(
            {
                "profile_id": str(entry.get("profile_id", "") or ""),
                "bucket": bucket or "—",
                "samples": sample_count if sample_count is not None else "unavailable",
                "families": family_count if family_count is not None else "unavailable",
                "status": status,
                "reason": str(entry.get("summary", "") or "").strip(),
            }
        )

    display_module.print_table(
        rows,
        title="Supported profile readiness inventory",
        columns=["profile_id", "bucket", "samples", "families", "status", "reason"],
        show_index=False,
    )
    taxonomy_signals = readiness.get("taxonomy_signals", {}) if isinstance(readiness, dict) else {}
    if isinstance(taxonomy_signals, dict):
        taxonomy_rows = [
            {
                "signal": "banker_label_bucket",
                "samples": taxonomy_signals.get("banker_label_bucket_samples", "unavailable")
                if taxonomy_signals.get("banker_label_bucket_samples") is not None
                else "unavailable",
                "meaning": "Legacy label bucket (Trojan / Banker)",
            },
            {
                "signal": "banker_type_bucket",
                "samples": taxonomy_signals.get("banker_type_bucket_samples", "unavailable")
                if taxonomy_signals.get("banker_type_bucket_samples") is not None
                else "unavailable",
                "meaning": "Resolved family mapped to type_slug=banker",
            },
            {
                "signal": "missing_primary_labels",
                "samples": taxonomy_signals.get("missing_primary_label_samples", "unavailable")
                if taxonomy_signals.get("missing_primary_label_samples") is not None
                else "unavailable",
                "meaning": "Android + PI samples missing classification_primary",
            },
            {
                "signal": "unresolved_family_samples",
                "samples": taxonomy_signals.get("unresolved_family_samples", "unavailable")
                if taxonomy_signals.get("unresolved_family_samples") is not None
                else "unavailable",
                "meaning": "Android + PI samples whose resolved family is not in android_malware_family",
            },
            {
                "signal": "known_unresolved_family_samples",
                "samples": taxonomy_signals.get("known_unresolved_family_samples", "unavailable")
                if taxonomy_signals.get("known_unresolved_family_samples") is not None
                else "unavailable",
                "meaning": "Unresolved samples whose family is already known locally",
            },
        ]
        display_module.print_table(
            taxonomy_rows,
            title="Taxonomy drift summary",
            columns=["signal", "samples", "meaning"],
            show_index=False,
        )
        top_unresolved = taxonomy_signals.get("top_unresolved_families", [])
        unresolved_rows: list[dict[str, object]] = []
        if isinstance(top_unresolved, list):
            for entry in top_unresolved[:5]:
                if not isinstance(entry, dict):
                    continue
                unresolved_rows.append(
                    {
                        "family": str(entry.get("family", "") or ""),
                        "samples": entry.get("sample_count", "unavailable"),
                        "high_strong": entry.get("high_strong_sample_count", "unavailable"),
                        "known_locally": "yes" if entry.get("known_locally") else "no",
                    }
                )
        if unresolved_rows:
            display_module.print_table(
                unresolved_rows,
                title="Top unresolved family backlog",
                columns=["family", "samples", "high_strong", "known_locally"],
                show_index=False,
            )
        top_conflicts = taxonomy_signals.get("top_family_type_conflicts", [])
        conflict_rows: list[dict[str, object]] = []
        if isinstance(top_conflicts, list):
            for entry in top_conflicts[:8]:
                if not isinstance(entry, dict):
                    continue
                conflict_rows.append(
                    {
                        "family": str(entry.get("family", "") or ""),
                        "priority": str(entry.get("priority", "") or "low"),
                        "action": str(entry.get("suggested_action", "") or "review_manually"),
                        "db_type": str(entry.get("db_type_slug", "") or "unavailable"),
                        "issue": str(entry.get("issue", "") or "unknown"),
                        "operator_model": str(entry.get("operator_model_candidate", "") or "unclear"),
                        "fraud_posture": str(entry.get("fraud_posture_candidate", "") or "unclear"),
                        "perm_signal": str(entry.get("permission_signal_summary", "") or "none"),
                        "samples": entry.get("sample_count", "unavailable"),
                        "high_strong": entry.get("high_strong_sample_count", "unavailable"),
                        "label_signal": (
                            f"{entry.get('dominant_label_semantic', '<none>')} "
                            f"({entry.get('dominant_label_samples', 0)})"
                        ).strip(),
                    }
                )
        if conflict_rows:
            display_module.print_table(
                conflict_rows,
                title="Family/type conflict backlog",
                columns=["family", "priority", "action", "db_type", "issue", "operator_model", "fraud_posture", "perm_signal", "samples", "high_strong", "label_signal"],
                show_index=False,
            )
        repair_candidates = taxonomy_signals.get("top_repair_candidates", [])
        repair_rows: list[dict[str, object]] = []
        if isinstance(repair_candidates, list):
            for entry in repair_candidates[:6]:
                if not isinstance(entry, dict):
                    continue
                repair_rows.append(
                    {
                        "family": str(entry.get("family", "") or ""),
                        "priority": str(entry.get("priority", "") or "low"),
                        "action": str(entry.get("suggested_action", "") or "review_manually"),
                        "issue": str(entry.get("issue", "") or "unknown"),
                        "db_type": str(entry.get("db_type_slug", "") or "unavailable"),
                        "samples": entry.get("sample_count", "unavailable"),
                        "high_strong": entry.get("high_strong_sample_count", "unavailable"),
                        "perm_signal": str(entry.get("permission_signal_summary", "") or "none"),
                    }
                )
        if repair_rows:
            display_module.print_table(
                repair_rows,
                title="Taxonomy repair candidates",
                columns=["family", "priority", "action", "issue", "db_type", "samples", "high_strong", "perm_signal"],
                show_index=False,
            )
    display_module.print_stat("Supported operator profiles", len(rows))
    display_module.print_stat("Ambiguous / unmapped", ambiguous_count)
    unresolved_family_count = taxonomy_signals.get("unresolved_family_count") if isinstance(taxonomy_signals, dict) else None
    if unresolved_family_count is not None:
        display_module.print_stat("Unresolved family slugs", unresolved_family_count)
    known_unresolved_family_count = taxonomy_signals.get("known_unresolved_family_count") if isinstance(taxonomy_signals, dict) else None
    if known_unresolved_family_count is not None:
        display_module.print_stat("Known unresolved families", known_unresolved_family_count)
    family_type_conflict_count = taxonomy_signals.get("family_type_conflict_count") if isinstance(taxonomy_signals, dict) else None
    if family_type_conflict_count is not None:
        display_module.print_stat("Family/type conflict candidates", family_type_conflict_count)
    repair_candidate_count = taxonomy_signals.get("repair_candidate_count") if isinstance(taxonomy_signals, dict) else None
    if repair_candidate_count is not None:
        display_module.print_stat("Taxonomy repair candidates", repair_candidate_count)
    display_module.print_subheader("Supported profile intent guide")
    for line in _PROFILE_INTENT_GUIDE:
        display_module.print_note(line)
    display_module.print_note(
        "Use the full catalog or direct profile loading only for debug/audit work; "
        "the supported operator architecture is the canonical final profile set."
    )
    if isinstance(taxonomy_signals, dict):
        banker_gap = taxonomy_signals.get("banker_type_minus_label_samples")
        if banker_gap:
            display_module.print_note(
                "Banker type scope currently exceeds the banker label bucket by "
                f"{banker_gap} sample(s)."
            )
        top_unresolved = taxonomy_signals.get("top_unresolved_families", [])
        if isinstance(top_unresolved, list) and top_unresolved:
            families = ", ".join(
                f"{entry.get('family')} ({entry.get('sample_count')})"
                for entry in top_unresolved[:5]
                if isinstance(entry, dict) and entry.get("family")
            )
            if families:
                display_module.print_note(f"Top unresolved resolved-family slugs: {families}")
        known_unresolved_samples = taxonomy_signals.get("known_unresolved_family_samples")
        if known_unresolved_samples:
            display_module.print_note(
                "Some unresolved family samples already map to known local taxonomy names; "
                "prioritize DB catalog alignment before adding more advisory layers."
            )
        top_conflicts = taxonomy_signals.get("top_family_type_conflicts", [])
        if isinstance(top_conflicts, list) and top_conflicts:
            families = ", ".join(
                f"{entry.get('family')} [{entry.get('issue')}]"
                for entry in top_conflicts[:4]
                if isinstance(entry, dict) and entry.get("family")
            )
            if families:
                display_module.print_note(f"Top family/type conflict candidates: {families}")
            posture_pairs = ", ".join(
                f"{entry.get('family')} → {entry.get('operator_model_candidate')}"
                for entry in top_conflicts[:3]
                if isinstance(entry, dict) and entry.get("family")
            )
            if posture_pairs:
                display_module.print_note(f"Operator-model hypotheses: {posture_pairs}")
            actions = ", ".join(
                f"{entry.get('family')} → {entry.get('suggested_action')}"
                for entry in top_conflicts[:3]
                if isinstance(entry, dict) and entry.get("family")
            )
            if actions:
                display_module.print_note(f"Suggested next actions: {actions}")
        repair_candidates = taxonomy_signals.get("top_repair_candidates", [])
        if isinstance(repair_candidates, list) and repair_candidates:
            families = ", ".join(
                f"{entry.get('family')} ({entry.get('high_strong_sample_count')})"
                for entry in repair_candidates[:5]
                if isinstance(entry, dict) and entry.get("family")
            )
            if families:
                display_module.print_note(f"Top taxonomy repair queue: {families}")
    display_module.print_note("Advisory only; does not enforce sample selection.")
    for warning in (readiness.get("warnings", []) if isinstance(readiness, dict) else [])[:3]:
        display_module.print_note(str(warning))
    if ambiguous_count > 0:
        display_module.print_note("Unmapped profile; review cohort filters manually.")
        display_module.print_note("Ambiguous profile intent; no readiness bucket selected.")
    return 0


__all__ = ["show_profile_readiness_mapping_inventory"]
