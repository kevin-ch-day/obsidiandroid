"""Deterministic permission protection / governance lane classification.

Offline contract for live-corpus type-permission reporting. Classification uses
only fields present on run-scoped ``permission_feature_audit.csv`` (and matching
prevalence ``permission`` tokens). It does **not** query Permission Intel, Core,
or Erebus, and it does **not** invent Android ``protectionLevel`` multi-flag
strings when those fields are absent from the completed-run artifacts.

Observed offline fields (all-current diagnostic run):

- ``permission_string`` / prevalence ``permission`` — canonical token
- ``pi_bucket_source`` — AOSP | OEM | GOOGLE | APP_DEFINED | UNKNOWN
- ``dangerous_bucket`` — normal | dangerous | google | oem_vendor | app_defined | unknown
- ``feature_column``, ``global_support``, retention flags

Absent from the completed-run audit CSV (do not invent):

- raw Android ``protectionLevel`` / ``base_protection_level``
- protection flag bitsets (privileged, development, …) as structured fields
- dictionary review/governance state beyond ``pi_bucket_source``
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

PROTECTION_LANE_CONTRACT_VERSION = "1.1.0"

# Exactly one headline reporting lane per token.
LANE_AOSP_NORMAL = "aosp_normal"
LANE_AOSP_DANGEROUS = "aosp_dangerous"
LANE_AOSP_PROTECTION_UNRESOLVED = "aosp_protection_unresolved"
LANE_OEM_OR_GOOGLE = "oem_or_google"
LANE_APP_DEFINED = "app_defined"
LANE_UNKNOWN_UNRESOLVED = "unknown_unresolved"

CANONICAL_PROTECTION_LANES: tuple[str, ...] = (
    LANE_AOSP_NORMAL,
    LANE_AOSP_DANGEROUS,
    LANE_AOSP_PROTECTION_UNRESOLVED,
    LANE_OEM_OR_GOOGLE,
    LANE_APP_DEFINED,
    LANE_UNKNOWN_UNRESOLVED,
)

# Conceptual mapping requested by research brief → offline lane actually used.
CONCEPTUAL_LANE_NOTES: dict[str, str] = {
    "AOSP normal": LANE_AOSP_NORMAL,
    "AOSP dangerous": LANE_AOSP_DANGEROUS,
    "AOSP signature / privileged": (
        f"{LANE_AOSP_PROTECTION_UNRESOLVED} "
        "(offline audit lacks structured signature/privileged flags; "
        "AOSP tokens with dangerous_bucket=unknown land here)"
    ),
    "OEM or Google platform permission": LANE_OEM_OR_GOOGLE,
    "App-defined permission": LANE_APP_DEFINED,
    "Unknown or unresolved": LANE_UNKNOWN_UNRESOLVED,
}

REPORTABILITY_STATUSES: tuple[str, ...] = (
    "descriptive_common",
    "descriptive_type_enriched",
    "family_balanced_supported",
    "single_family_dominated",
    "insufficient_family_support",
    "insufficient_sample_support",
    "protection_level_unresolved",
    "app_defined_high_cardinality",
    "not_significant_after_fdr",
    "effect_too_small",
    "exploratory_only",
)

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "min_sample_support": 30,
    "min_family_support": 3,
    "min_family_size": 3,
    "min_family_balanced_prevalence": 0.05,
    "min_effect_odds": 1.5,
    "dominance_threshold": 0.85,
    "fdr_alpha": 0.05,
    "app_defined_max_global_support_for_identity": 5,
    # Headline strength tiers (applied after family_balanced_supported).
    "headline_strength_strong_fb": 0.20,
    "headline_strength_moderate_fb": 0.10,
}


def classify_headline_strength(
    *,
    reportability_status: str,
    family_balanced_prevalence: float | None,
    thresholds: Mapping[str, Any] | None = None,
) -> str:
    """Tier already-supported headlines by family-balanced prevalence.

    Returns one of: ``strong``, ``moderate``, ``marginal``, ``not_headline``.
    Does not hide marginal rows; interpretation should prefer strong/moderate.
    """
    thr = {**DEFAULT_THRESHOLDS, **(dict(thresholds) if thresholds else {})}
    if str(reportability_status) != "family_balanced_supported":
        return "not_headline"
    if family_balanced_prevalence is None or pd.isna(family_balanced_prevalence):
        return "marginal"
    fb = float(family_balanced_prevalence)
    if fb >= float(thr["headline_strength_strong_fb"]):
        return "strong"
    if fb >= float(thr["headline_strength_moderate_fb"]):
        return "moderate"
    return "marginal"


def _norm_source(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_bucket(value: Any) -> str:
    return str(value or "").strip().lower()


def classify_protection_lane(
    *,
    pi_bucket_source: Any = "",
    dangerous_bucket: Any = "",
    permission_string: Any = "",
) -> str:
    """Map one permission token to exactly one canonical reporting lane.

    Precedence (deterministic):

    1. ``pi_bucket_source == UNKNOWN`` → ``unknown_unresolved``
    2. App-defined source or ``dangerous_bucket == app_defined`` → ``app_defined``
    3. OEM/GOOGLE source or oem_vendor/google bucket → ``oem_or_google``
    4. AOSP + ``normal`` → ``aosp_normal``
    5. AOSP + ``dangerous`` → ``aosp_dangerous``
    6. AOSP + any other/empty bucket → ``aosp_protection_unresolved``
       (includes tokens that *may* be signature/privileged, but that claim is
       not confirmable from offline audit fields)
    7. Anything else → ``unknown_unresolved``

    ``permission_string`` is accepted for provenance/call-site symmetry but is
    **not** used to invent signature/privileged lanes from name heuristics.
    """
    _ = permission_string  # retained for API stability / future governed fields
    src = _norm_source(pi_bucket_source)
    dang = _norm_bucket(dangerous_bucket)

    if src == "UNKNOWN":
        return LANE_UNKNOWN_UNRESOLVED
    if src == "APP_DEFINED" or dang == "app_defined":
        return LANE_APP_DEFINED
    if src in {"OEM", "GOOGLE"} or dang in {"oem_vendor", "google"}:
        return LANE_OEM_OR_GOOGLE
    if src == "AOSP":
        if dang == "normal":
            return LANE_AOSP_NORMAL
        if dang == "dangerous":
            return LANE_AOSP_DANGEROUS
        return LANE_AOSP_PROTECTION_UNRESOLVED
    return LANE_UNKNOWN_UNRESOLVED


def lane_pair_class(lane_a: str, lane_b: str) -> str:
    """Return ``within_lane`` or ``cross_lane`` with deterministic lane order."""
    a = str(lane_a)
    b = str(lane_b)
    return "within_lane" if a == b else "cross_lane"


def ordered_lane_pair(lane_a: str, lane_b: str) -> tuple[str, str]:
    """Canonical (lane_lo, lane_hi) ordering by CANONICAL_PROTECTION_LANES index."""
    order = {name: idx for idx, name in enumerate(CANONICAL_PROTECTION_LANES)}
    a = str(lane_a)
    b = str(lane_b)
    ia = order.get(a, 10_000)
    ib = order.get(b, 10_000)
    if (ia, a) <= (ib, b):
        return a, b
    return b, a


def attach_protection_lanes(audit: pd.DataFrame) -> pd.DataFrame:
    """Copy audit frame and add ``protection_governance_lane`` for every row."""
    frame = audit.copy()
    src_col = "pi_bucket_source" if "pi_bucket_source" in frame.columns else None
    dang_col = "dangerous_bucket" if "dangerous_bucket" in frame.columns else None
    perm_col = "permission_string" if "permission_string" in frame.columns else None
    if src_col is None and dang_col is None:
        frame["protection_governance_lane"] = LANE_UNKNOWN_UNRESOLVED
        return frame
    frame["protection_governance_lane"] = [
        classify_protection_lane(
            pi_bucket_source=row[src_col] if src_col else "",
            dangerous_bucket=row[dang_col] if dang_col else "",
            permission_string=row[perm_col] if perm_col else "",
        )
        for row in frame.to_dict(orient="records")
    ]
    return frame


def permission_lane_lookup(audit: pd.DataFrame) -> dict[str, str]:
    """Map lowercased permission_string → lane (last write wins; audit is unique)."""
    framed = attach_protection_lanes(audit)
    if "permission_string" not in framed.columns:
        return {}
    out: dict[str, str] = {}
    for row in framed.itertuples(index=False):
        key = str(getattr(row, "permission_string")).strip().lower()
        out[key] = str(getattr(row, "protection_governance_lane"))
    return out


def reconcile_lane_token_counts(lanes: Iterable[str]) -> dict[str, Any]:
    """Reconcile token counts: total == sum(lane counts)."""
    series = pd.Series(list(lanes), dtype="object")
    counts = {lane: int((series == lane).sum()) for lane in CANONICAL_PROTECTION_LANES}
    other = int((~series.isin(CANONICAL_PROTECTION_LANES)).sum())
    total = int(len(series))
    lane_sum = int(sum(counts.values()) + other)
    return {
        "total_tokens": total,
        "lane_counts": counts,
        "noncanonical_token_count": other,
        "lane_sum": lane_sum,
        "reconciles": total == lane_sum and other == 0,
    }


def governance_field_contract_table() -> list[dict[str, str]]:
    """Small durable contract describing offline fields and ambiguity handling."""
    return [
        {
            "source_field": "permission_string",
            "meaning": "Canonical permission token (lowercased in prevalence tables)",
            "allowed_values_observed": "Android / OEM / app-defined strings",
            "null_rate": "0 in audit rows",
            "mapping_authority": "permission_feature_audit.csv",
            "report_lane": "join key for all lanes",
            "ambiguity_handling": "Unmatched prevalence tokens → unknown_unresolved",
        },
        {
            "source_field": "pi_bucket_source",
            "meaning": "Governance / namespace bucket from Permission Intel export",
            "allowed_values_observed": "AOSP, OEM, GOOGLE, APP_DEFINED, UNKNOWN",
            "null_rate": "0 in completed-run audit",
            "mapping_authority": "permission_feature_audit.csv",
            "report_lane": "primary namespace gate before AOSP protection split",
            "ambiguity_handling": "UNKNOWN → unknown_unresolved; OEM/GOOGLE → oem_or_google",
        },
        {
            "source_field": "dangerous_bucket",
            "meaning": "Coarse protection/governance class in the audit export",
            "allowed_values_observed": "normal, dangerous, google, oem_vendor, app_defined, unknown",
            "null_rate": "0 in completed-run audit",
            "mapping_authority": "permission_feature_audit.csv",
            "report_lane": "AOSP normal/dangerous vs aosp_protection_unresolved",
            "ambiguity_handling": (
                "AOSP+unknown is NOT treated as confirmed signature/privileged; "
                "lands in aosp_protection_unresolved"
            ),
        },
        {
            "source_field": "base_protection_level / protection_flags",
            "meaning": "Structured Android protectionLevel decomposition",
            "allowed_values_observed": "absent from completed-run audit CSV",
            "null_rate": "100% (field missing)",
            "mapping_authority": "n/a offline",
            "report_lane": "not used",
            "ambiguity_handling": "Do not invent; keep unresolved lane instead",
        },
        {
            "source_field": "feature_column / retained_after_pruning / global_support",
            "meaning": "ML feature linkage and support filters for pairwise mining",
            "allowed_values_observed": "perm__* columns; yes/no retention; integer support",
            "null_rate": "low",
            "mapping_authority": "permission_feature_audit.csv + aligned_features",
            "report_lane": "filters which tokens enter pairwise tables",
            "ambiguity_handling": "App-defined / unknown excluded from default headline vocab",
        },
    ]


def classify_permission_row_reportability(
    *,
    lane: str,
    type_slug: str,
    positive_samples: int,
    families_with_permission: int,
    largest_family_share: float,
    sample_weighted_prevalence: float | None,
    family_balanced_prevalence: float | None,
    odds_ratio: float | None,
    thresholds: Mapping[str, Any] | None = None,
    no_headline_types: Iterable[str] | None = None,
) -> str:
    """Reportability for type×permission (lane-aware) rows."""
    thr = {**DEFAULT_THRESHOLDS, **(dict(thresholds) if thresholds else {})}
    slug = str(type_slug).strip().lower()
    exploratory = {
        str(x).strip().lower()
        for x in (
            no_headline_types
            or (
                "backdoor",
                "dropper",
                "sms-trojan",
                "pua",
                "riskware",
                "worm",
                "ransomware",
                "rootkit",
                "subscription-fraud",
                "unknown",
            )
        )
    }
    if lane in {LANE_UNKNOWN_UNRESOLVED, LANE_AOSP_PROTECTION_UNRESOLVED}:
        # Unresolved protection is never a capability headline by itself.
        return "protection_level_unresolved"
    if lane == LANE_APP_DEFINED:
        return "app_defined_high_cardinality"
    if int(positive_samples) < int(thr["min_sample_support"]):
        return "insufficient_sample_support"
    if int(families_with_permission) < int(thr["min_family_support"]):
        return "insufficient_family_support"
    if float(largest_family_share) >= float(thr["dominance_threshold"]):
        return "single_family_dominated"
    fb = family_balanced_prevalence
    if fb is not None and not pd.isna(fb) and float(fb) < float(thr["min_family_balanced_prevalence"]):
        return "effect_too_small"
    if slug in exploratory:
        return "exploratory_only"
    or_val = float(odds_ratio) if odds_ratio is not None and not pd.isna(odds_ratio) else None
    if or_val is not None and or_val >= float(thr["min_effect_odds"]):
        return "family_balanced_supported"
    if or_val is not None and or_val >= 1.0:
        return "descriptive_type_enriched"
    sw = sample_weighted_prevalence
    if sw is not None and not pd.isna(sw) and float(sw) >= 0.70:
        return "descriptive_common"
    return "descriptive_common"


def contract_metadata() -> dict[str, Any]:
    """Manifest block for composers."""
    return {
        "protection_lane_contract_version": PROTECTION_LANE_CONTRACT_VERSION,
        "canonical_lanes": list(CANONICAL_PROTECTION_LANES),
        "conceptual_lane_notes": CONCEPTUAL_LANE_NOTES,
        "reportability_statuses": list(REPORTABILITY_STATUSES),
        "default_thresholds": dict(DEFAULT_THRESHOLDS),
        "classification_precedence": [
            "UNKNOWN source → unknown_unresolved",
            "APP_DEFINED source or app_defined bucket → app_defined",
            "OEM/GOOGLE source or oem_vendor/google bucket → oem_or_google",
            "AOSP + normal → aosp_normal",
            "AOSP + dangerous → aosp_dangerous",
            "AOSP + other/unknown bucket → aosp_protection_unresolved",
            "else → unknown_unresolved",
        ],
        "signature_privileged_note": (
            "Structured signature/privileged protection flags are absent from the "
            "completed-run permission_feature_audit.csv; do not claim confirmed "
            "signature/privileged lanes from offline evidence alone."
        ),
        "governance_field_contract": governance_field_contract_table(),
    }


__all__ = [
    "PROTECTION_LANE_CONTRACT_VERSION",
    "CANONICAL_PROTECTION_LANES",
    "CONCEPTUAL_LANE_NOTES",
    "REPORTABILITY_STATUSES",
    "DEFAULT_THRESHOLDS",
    "LANE_AOSP_NORMAL",
    "LANE_AOSP_DANGEROUS",
    "LANE_AOSP_PROTECTION_UNRESOLVED",
    "LANE_OEM_OR_GOOGLE",
    "LANE_APP_DEFINED",
    "LANE_UNKNOWN_UNRESOLVED",
    "classify_protection_lane",
    "lane_pair_class",
    "ordered_lane_pair",
    "attach_protection_lanes",
    "permission_lane_lookup",
    "reconcile_lane_token_counts",
    "governance_field_contract_table",
    "classify_permission_row_reportability",
    "classify_headline_strength",
    "contract_metadata",
]
