"""Profile-readiness inventory rendering for the Data Diagnostics menu."""

from __future__ import annotations

import inspect

import obsidiandroid.cli.profile_manager as profile_manager
from obsidiandroid.common import ml_console
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.authority_taxonomy_terms import (
    POLICY_HELD_FAMILY_TOKENS_LABEL,
    HIGH_PRIORITY_TAXONOMY_CONFLICTS_LABEL,
    TAXONOMY_CURATION_DISCIPLINE_TITLE,
    TOP_POLICY_HELD_TOKEN_BACKLOG_TITLE,
    TOP_TRUE_UNRESOLVED_FAMILY_BACKLOG_TITLE,
    TRUE_FAMILY_TYPE_CONFLICT_CANDIDATES_LABEL,
    TRUE_UNRESOLVED_FAMILY_SLUGS_LABEL,
    policy_held_only_note,
)
from obsidiandroid.common.backlog_semantics import build_taxonomy_curation_posture
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
    "Only supported profiles are shown in this readiness inventory view.",
)

_PRIMARY_BUCKET_ORDER: tuple[str, ...] = (
    "all_catalog",
    "android_platform",
    "android_with_permission_obs",
    "android_high_or_strong_vt_with_permission_obs",
    "android_family_ready_min3_permission_obs",
    "android_banker_with_permission_obs",
)


def _profile_group_label(profile_id: str) -> str:
    token = str(profile_id or "").strip().lower()
    if not token:
        return "other profiles"
    if "banker" in token:
        return "banker profiles"
    if "dev" in token or "smoke" in token or "type" in token:
        return "all-current / type-taxonomy / dev profiles"
    if any(part in token for part in ("major", "expanded", "temporal", "malicious", "sensitivity")):
        return "major / expanded / temporal profiles"
    return "other profiles"


def _overall_status(*, ambiguous_count: int, unresolved_count: int, repair_count: int, high_priority_conflicts: int) -> str:
    if ambiguous_count <= 0 and unresolved_count <= 0 and repair_count <= 0 and high_priority_conflicts <= 0:
        return "GREEN"
    return "YELLOW"


def show_profile_readiness_mapping_inventory(
    *,
    profile_manager_module=profile_manager,
    get_cohort_readiness_snapshot_fn=get_cohort_readiness_snapshot,
    display_module=du,
) -> int:
    """Print bundled profile-to-readiness mapping inventory (advisory only)."""
    inventory_fn = profile_manager_module.inventory_cohort_readiness_mappings
    inventory_kwargs = {
        "include_hidden": False,
        "profile_ids": list(getattr(profile_manager_module, "FINAL_OPERATOR_PROFILE_IDS", ())),
    }
    try:
        params = inspect.signature(inventory_fn).parameters
    except (TypeError, ValueError):
        params = {}
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()) or inventory_kwargs.keys() <= params.keys():
        inventory = inventory_fn(**inventory_kwargs)
    else:
        inventory = inventory_fn()
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
    authority_source_mode = str(readiness.get("authority_source_mode", "") or "").strip() if isinstance(readiness, dict) else ""

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
    taxonomy_signals = readiness.get("taxonomy_signals", {}) if isinstance(readiness, dict) else {}
    taxonomy_rows: list[dict[str, object]] = []
    unresolved_rows: list[dict[str, object]] = []
    policy_rows: list[dict[str, object]] = []
    policy_kind_rows: list[dict[str, object]] = []
    conflict_rows: list[dict[str, object]] = []
    discipline_rows: list[dict[str, object]] = []
    repair_rows: list[dict[str, object]] = []
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
                "signal": "typed_authority_pi_scope",
                "samples": taxonomy_signals.get("typed_authority_permission_obs_samples", "unavailable")
                if taxonomy_signals.get("typed_authority_permission_obs_samples") is not None
                else "unavailable",
                "meaning": "Family-typed authority rows in the Android + Permission Intel scope; may include retired taxonomy records",
            },
            {
                "signal": "strict_active_authority_pi_scope",
                "samples": taxonomy_signals.get("strict_active_authority_permission_obs_samples", "unavailable")
                if taxonomy_signals.get("strict_active_authority_permission_obs_samples") is not None
                else "unavailable",
                "meaning": "Family-typed authority rows whose linked family and type records are both active",
            },
            {
                "signal": "retired_type_authority_pi_scope",
                "samples": taxonomy_signals.get("retired_type_authority_permission_obs_samples", "unavailable")
                if taxonomy_signals.get("retired_type_authority_permission_obs_samples") is not None
                else "unavailable",
                "meaning": "Family-typed authority rows excluded from the strict surface because their active family points to a retired type",
            },
            {
                "signal": "missing_primary_labels",
                "samples": taxonomy_signals.get("missing_primary_label_samples", "unavailable")
                if taxonomy_signals.get("missing_primary_label_samples") is not None
                else "unavailable",
                "meaning": "Active/actionable Android + PI missing-primary debt after suppression-aware triage",
            },
            {
                "signal": "missing_primary_actionable",
                "samples": taxonomy_signals.get("missing_primary_label_actionable_samples", "unavailable")
                if taxonomy_signals.get("missing_primary_label_actionable_samples") is not None
                else "unavailable",
                "meaning": "Missing-primary rows with high/strong evidence still eligible for label review",
            },
            {
                "signal": "missing_primary_residual",
                "samples": taxonomy_signals.get("missing_primary_label_residual_samples", "unavailable")
                if taxonomy_signals.get("missing_primary_label_residual_samples") is not None
                else "unavailable",
                "meaning": "Missing-primary rows blocked by provenance, suppression, zero-signal, or low-consensus posture",
            },
            {
                "signal": "missing_primary_suppressed",
                "samples": taxonomy_signals.get("missing_primary_label_suppressed_samples", "unavailable")
                if taxonomy_signals.get("missing_primary_label_suppressed_samples") is not None
                else "unavailable",
                "meaning": "Missing-primary rows already closed by sample/package false-positive suppression",
            },
            {
                "signal": "missing_primary_active_residual",
                "samples": taxonomy_signals.get("missing_primary_label_active_residual_samples", "unavailable")
                if taxonomy_signals.get("missing_primary_label_active_residual_samples") is not None
                else "unavailable",
                "meaning": "Missing-primary rows still needing manual provenance or low-consensus review",
            },
            {
                "signal": "unresolved_family_samples",
                "samples": taxonomy_signals.get("unresolved_family_samples", "unavailable")
                if taxonomy_signals.get("unresolved_family_samples") is not None
                else "unavailable",
                "meaning": "Android + PI samples whose resolved family is not in android_malware_family and not already policy-held",
            },
            {
                "signal": "known_unresolved_family_samples",
                "samples": taxonomy_signals.get("known_unresolved_family_samples", "unavailable")
                if taxonomy_signals.get("known_unresolved_family_samples") is not None
                else "unavailable",
                "meaning": "Unresolved samples whose family is already known locally",
            },
            {
                "signal": "policy_held_family_samples",
                "samples": taxonomy_signals.get("policy_held_family_samples", "unavailable")
                if taxonomy_signals.get("policy_held_family_samples") is not None
                else "unavailable",
                "meaning": "Resolved-family samples held by generic/coarse token policy and excluded from true family-repair backlog",
            },
        ]
        top_unresolved = taxonomy_signals.get("top_unresolved_families", [])
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
        top_policy_held = taxonomy_signals.get("top_policy_held_families", [])
        if isinstance(top_policy_held, list):
            for entry in top_policy_held[:5]:
                if not isinstance(entry, dict):
                    continue
                policy_rows.append(
                    {
                        "family": str(entry.get("family", "") or ""),
                        "samples": entry.get("sample_count", "unavailable"),
                        "high_strong": entry.get("high_strong_sample_count", "unavailable"),
                        "token_kind": str(entry.get("token_kind", "") or "policy_held_token"),
                    }
                )
        policy_kind_counts = taxonomy_signals.get("policy_held_family_token_kind_counts", {})
        if isinstance(policy_kind_counts, dict):
            for token_kind, count in sorted(
                policy_kind_counts.items(),
                key=lambda item: (-int(item[1] or 0), str(item[0])),
            ):
                policy_kind_rows.append(
                    {
                        "token_kind": str(token_kind or "policy_held_token"),
                        "samples": int(count or 0),
                        "meaning": "Policy-held rows by generic/coarse token class",
                    }
                )
        top_conflicts = taxonomy_signals.get("top_family_type_conflicts", [])
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
        action_counts = taxonomy_signals.get("family_type_conflict_action_counts", {})
        if isinstance(action_counts, dict):
            for action, count in sorted(
                action_counts.items(),
                key=lambda item: (-int(item[1] or 0), str(item[0])),
            ):
                discipline_rows.append(
                    {
                        "focus": str(action or "review_manually"),
                        "families": int(count or 0),
                        "meaning": "Suggested curation action for family/type conflict cleanup",
                    }
                )
        repair_candidates = taxonomy_signals.get("top_repair_candidates", [])
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
    unresolved_family_count = taxonomy_signals.get("unresolved_family_count") if isinstance(taxonomy_signals, dict) else None
    known_unresolved_family_count = taxonomy_signals.get("known_unresolved_family_count") if isinstance(taxonomy_signals, dict) else None
    policy_held_family_count = taxonomy_signals.get("policy_held_family_count") if isinstance(taxonomy_signals, dict) else None
    family_type_conflict_count = taxonomy_signals.get("family_type_conflict_count") if isinstance(taxonomy_signals, dict) else None
    high_priority_conflict_count = taxonomy_signals.get("high_priority_conflict_count") if isinstance(taxonomy_signals, dict) else None
    repair_candidate_count = taxonomy_signals.get("repair_candidate_count") if isinstance(taxonomy_signals, dict) else None
    unresolved_family_count_int = int(unresolved_family_count or 0) if unresolved_family_count is not None else 0
    known_unresolved_family_count_int = (
        int(known_unresolved_family_count or 0) if known_unresolved_family_count is not None else 0
    )
    policy_held_family_count_int = int(policy_held_family_count or 0) if policy_held_family_count is not None else 0
    family_type_conflict_count_int = (
        int(family_type_conflict_count or 0) if family_type_conflict_count is not None else 0
    )
    high_priority_conflict_count_int = (
        int(high_priority_conflict_count or 0) if high_priority_conflict_count is not None else 0
    )
    repair_candidate_count_int = int(repair_candidate_count or 0) if repair_candidate_count is not None else 0

    display_module.print_section("Profile Readiness Summary")
    display_module.print_stat(
        "Overall status",
        _overall_status(
            ambiguous_count=ambiguous_count,
            unresolved_count=unresolved_family_count_int,
            repair_count=repair_candidate_count_int,
            high_priority_conflicts=high_priority_conflict_count_int,
        ),
    )
    display_module.print_stat("Supported operator profiles", len(rows))
    display_module.print_stat("Ambiguous / unmapped profiles", ambiguous_count)
    display_module.print_stat("Authority source", authority_source_mode or "unavailable")

    display_module.print_subheader("Key interpretation")
    if unresolved_family_count_int <= 0:
        print("No true unresolved Android family slugs are active in this slice.")
    else:
        print(f"True unresolved Android family slugs remain active: {unresolved_family_count_int}.")
    if repair_candidate_count_int <= 0 and high_priority_conflict_count_int <= 0:
        print("No high-priority taxonomy conflict candidates are currently queued.")
    else:
        print(
            "High-priority taxonomy conflict review remains open: "
            f"{high_priority_conflict_count_int} high-priority conflict(s), "
            f"{repair_candidate_count_int} repair candidate(s)."
        )
    if policy_held_family_count_int > 0:
        print(
            "Remaining taxonomy residue is policy-held generic/coarse token noise, "
            "not true family-repair debt."
        )

    display_module.print_subheader("Readiness buckets")
    bucket_lookup = {str(row.get("bucket", "")): row for row in bucket_rows}
    for bucket in _PRIMARY_BUCKET_ORDER:
        row = bucket_lookup.get(bucket)
        if not isinstance(row, dict):
            continue
        print(
            f"{bucket:<34} : {row.get('samples', 'unavailable')} samples | "
            f"{row.get('families', 'unavailable')} families"
        )

    display_module.print_subheader("Profile mapping")
    if ambiguous_count <= 0:
        print(f"All {len(rows)} supported operator profiles are mapped.")
    else:
        print(f"{ambiguous_count} supported profile(s) remain ambiguous or unmapped.")
    group_to_buckets: dict[str, set[str]] = {}
    for row in rows:
        group = _profile_group_label(str(row.get("profile_id", "") or ""))
        bucket = str(row.get("bucket", "") or "—")
        group_to_buckets.setdefault(group, set()).add(bucket)
    print("")
    print("Primary mappings:")
    for group in (
        "all-current / type-taxonomy / dev profiles",
        "major / expanded / temporal profiles",
        "banker profiles",
        "other profiles",
    ):
        buckets = sorted(group_to_buckets.get(group, set()))
        if not buckets:
            continue
        print(f"- {group} -> {', '.join(buckets)}")

    display_module.print_subheader("Taxonomy residue")
    display_module.print_stat(TRUE_UNRESOLVED_FAMILY_SLUGS_LABEL, unresolved_family_count_int)
    display_module.print_stat("Known unresolved families", known_unresolved_family_count_int)
    display_module.print_stat("Repair candidates", repair_candidate_count_int)
    display_module.print_stat(HIGH_PRIORITY_TAXONOMY_CONFLICTS_LABEL, high_priority_conflict_count_int)
    display_module.print_stat("Policy-held token samples", int(taxonomy_signals.get("policy_held_family_samples", 0) or 0))
    display_module.print_stat("Policy-held token classes", policy_held_family_count_int)

    display_module.print_subheader("Policy-held token review")
    print("Top tokens:")
    for row in policy_rows[:5]:
        print(
            f"- {str(row.get('family', '')):<22} : {row.get('samples', 'unavailable')} samples | "
            f"{row.get('token_kind', 'policy_held_token')}"
        )
    if not policy_rows:
        print("- None")
    print("")
    print("Token classes:")
    for row in policy_kind_rows:
        print(f"- {str(row.get('token_kind', 'policy_held_token')):<22} : {row.get('samples', 0)}")
    if not policy_kind_rows:
        print("- None")

    display_module.print_subheader("Missing primary labels")
    display_module.print_stat(
        "Raw missing primary labels",
        int(taxonomy_signals.get("missing_primary_label_samples", 0) or 0),
    )
    display_module.print_stat(
        "Actionable missing-primary debt",
        int(taxonomy_signals.get("missing_primary_label_actionable_samples", 0) or 0),
    )
    display_module.print_stat(
        "Suppressed / false-positive rows",
        int(taxonomy_signals.get("missing_primary_label_suppressed_samples", 0) or 0),
    )
    display_module.print_stat(
        "Active residual review rows",
        int(taxonomy_signals.get("missing_primary_label_active_residual_samples", 0) or 0),
    )
    display_module.print_stat(
        "High/strong label-review rows",
        int(taxonomy_signals.get("missing_primary_label_high_strong_samples", 0) or 0),
    )

    display_module.print_subheader("Notes")
    print("- Readiness inventory is advisory only; it does not enforce sample selection.")
    print("- Supported dev profiles are for local/operator checks, not scientific benchmark interpretation.")
    for warning in (readiness.get("warnings", []) if isinstance(readiness, dict) else [])[:3]:
        print(f"- {warning}")
    print("- Use full dataframe exports for audit/debug detail.")

    display_module.print_subheader("Diagnostics")
    print("- profile_readiness_inventory.csv")
    print("- taxonomy_drift_summary.csv")
    print("- policy_held_token_risk_export.csv")

    if ml_console.show_debug_tables(default=False):
        display_module.print_table(
            bucket_rows,
            title="Readiness bucket summary",
            columns=["bucket", "samples", "families", "meaning"],
            show_index=False,
        )
        display_module.print_table(
            rows,
            title="Supported profile readiness inventory",
            columns=["profile_id", "bucket", "samples", "families", "status", "reason"],
            show_index=False,
        )
        if taxonomy_rows:
            display_module.print_table(
                taxonomy_rows,
                title="Taxonomy drift summary",
                columns=["signal", "samples", "meaning"],
                show_index=False,
            )
        if unresolved_rows:
            display_module.print_table(
                unresolved_rows,
                title=TOP_TRUE_UNRESOLVED_FAMILY_BACKLOG_TITLE,
                columns=["family", "samples", "high_strong", "known_locally"],
                show_index=False,
            )
        if policy_rows:
            display_module.print_table(
                policy_rows,
                title=TOP_POLICY_HELD_TOKEN_BACKLOG_TITLE,
                columns=["family", "samples", "high_strong", "token_kind"],
                show_index=False,
            )
        if policy_kind_rows:
            display_module.print_table(
                policy_kind_rows,
                title="Policy-Held Token Classes",
                columns=["token_kind", "samples", "meaning"],
                show_index=False,
            )
        if conflict_rows:
            display_module.print_table(
                conflict_rows,
                title="Family/type conflict backlog",
                columns=["family", "priority", "action", "db_type", "issue", "operator_model", "fraud_posture", "perm_signal", "samples", "high_strong", "label_signal"],
                show_index=False,
            )
        if discipline_rows:
            display_module.print_table(
                discipline_rows,
                title=TAXONOMY_CURATION_DISCIPLINE_TITLE,
                columns=["focus", "families", "meaning"],
                show_index=False,
            )
        if repair_rows:
            display_module.print_table(
                repair_rows,
                title="Taxonomy repair candidates",
                columns=["family", "priority", "action", "issue", "db_type", "samples", "high_strong", "perm_signal"],
                show_index=False,
            )
    return 0


__all__ = ["show_profile_readiness_mapping_inventory"]
