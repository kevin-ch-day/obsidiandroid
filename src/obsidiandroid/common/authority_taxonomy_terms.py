"""Shared operator-facing terminology for authority/taxonomy debt surfaces."""

from __future__ import annotations


TRUE_UNRESOLVED_FAMILY_DEBT_LABEL = "True unresolved family debt"
TRUE_UNRESOLVED_FAMILY_SLUGS_LABEL = "True unresolved family slugs"
TOP_TRUE_UNRESOLVED_FAMILY_BACKLOG_TITLE = "Top true unresolved family backlog"
POLICY_HELD_FAMILY_NOISE_LABEL = "Policy-held family noise"
POLICY_HELD_FAMILY_TOKENS_LABEL = "Policy-held family tokens"
TOP_POLICY_HELD_TOKEN_BACKLOG_TITLE = "Top policy-held token backlog"
FAMILY_TYPE_CONFLICT_BACKLOG_LABEL = "Family/type conflict backlog"
ACTIVE_FAMILY_RETIRED_TYPE_LIFECYCLE_LABEL = "Active-family retired-type lifecycle gaps"
TRUE_FAMILY_TYPE_CONFLICT_CANDIDATES_LABEL = "True family/type conflict candidates"
HIGH_PRIORITY_TAXONOMY_CONFLICTS_LABEL = "High-priority taxonomy conflicts"
TAXONOMY_CURATION_DISCIPLINE_TITLE = "Taxonomy curation discipline"
ANDROID_MISSING_RESOLUTION_BACKLOG_LABEL = "Android missing-resolution backlog"
VT_FALSE_POSITIVE_REVIEW_RESIDUE_LABEL = "False-positive review residue"
AUTHORITY_TAXONOMY_SPLIT_PROBLEM_LABEL = "Live readiness / authority-taxonomy split"
PROFILE_FAMILY_MAPPING_DEBT_LABEL = "Profile family-mapping debt"


def live_taxonomy_backlog_detail(
    *,
    repair_candidate_count: int,
    known_unresolved_count: int,
    policy_held_count: int,
) -> str:
    """Return compact operator wording for live authority/taxonomy debt."""
    return (
        "Live authority/taxonomy backlog: "
        f"repair candidates={repair_candidate_count}, "
        f"known unresolved families={known_unresolved_count}, "
        f"policy-held tokens={policy_held_count}."
    )


def policy_held_only_note() -> str:
    """Return the canonical note for slices with no true unresolved family debt."""
    return (
        "Live readiness shows no true unresolved family slugs in this slice; "
        "the remaining taxonomy residue is policy-held token noise."
    )


def taxonomy_curation_discipline_note(
    *,
    conflict_count: int,
    high_priority_count: int,
    action_counts: dict[str, int] | None,
    issue_counts: dict[str, int] | None,
) -> str | None:
    """Return compact wording for the current taxonomy repair posture."""
    if conflict_count <= 0:
        return None
    action_counts = dict(action_counts or {})
    issue_counts = dict(issue_counts or {})
    top_action = ""
    top_action_count = 0
    if action_counts:
        top_action, top_action_count = max(
            action_counts.items(),
            key=lambda item: (int(item[1]), str(item[0])),
        )
    top_issue = ""
    top_issue_count = 0
    if issue_counts:
        top_issue, top_issue_count = max(
            issue_counts.items(),
            key=lambda item: (int(item[1]), str(item[0])),
        )
    detail = (
        "Taxonomy curation discipline: "
        f"high-priority conflicts={high_priority_count}/{conflict_count}"
    )
    if top_action:
        detail += f"; dominant action={top_action} ({top_action_count})"
    if top_issue:
        detail += f"; dominant issue={top_issue} ({top_issue_count})"
    detail += "."
    return detail


def taxonomy_count_drift_semantics(
    *,
    expected_family_count: int,
    observed_family_count: int,
    expected_type_count: int,
    observed_type_count: int,
) -> dict[str, object]:
    """Classify locked-cohort family/type count drift in operator-safe language."""
    family_delta = int(observed_family_count) - int(expected_family_count)
    type_delta = int(observed_type_count) - int(expected_type_count)
    family_direction = _drift_direction(family_delta)
    type_direction = _drift_direction(type_delta)
    if family_delta == 0 and type_delta == 0:
        drift_class = "stable"
        action = "No taxonomy count drift detected."
    elif family_delta >= 0 and type_delta >= 0:
        drift_class = "taxonomy_expansion"
        action = (
            "Review newly split families/types inside the locked sample set; "
            "refresh the lock only after curation intent is accepted."
        )
    elif family_delta <= 0 and type_delta <= 0:
        drift_class = "taxonomy_consolidation"
        action = (
            "Review merged or collapsed family/type labels inside the locked sample set; "
            "confirm aliases before comparing to historical counts."
        )
    else:
        drift_class = "mixed_taxonomy_drift"
        action = (
            "Review both family and type mappings before treating this as a simple lock refresh."
        )
    return {
        "family_delta": family_delta,
        "type_delta": type_delta,
        "family_direction": family_direction,
        "type_direction": type_direction,
        "drift_class": drift_class,
        "recommended_action": action,
    }


def taxonomy_count_drift_note(drift: dict[str, object]) -> str:
    """Render a compact note for taxonomy count-drift payloads."""
    drift_class = str(drift.get("drift_class", "taxonomy_drift") or "taxonomy_drift")
    family_delta = int(drift.get("family_delta", 0) or 0)
    type_delta = int(drift.get("type_delta", 0) or 0)
    action = str(drift.get("recommended_action", "") or "").strip()
    note = f"Taxonomy drift class={drift_class}; family_delta={family_delta:+d}; type_delta={type_delta:+d}."
    if action:
        note += f" {action}"
    return note


def _drift_direction(delta: int) -> str:
    if delta > 0:
        return "expanded"
    if delta < 0:
        return "contracted"
    return "unchanged"
