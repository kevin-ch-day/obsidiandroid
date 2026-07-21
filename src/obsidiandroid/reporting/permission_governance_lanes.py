"""Deterministic permission protection / governance lane classification.

Offline contract for live-corpus type-permission reporting. Classification uses
only fields present on run-scoped ``permission_feature_audit.csv`` (and optional
structured protection columns when present). It does **not** query Permission
Intel, Core, or Erebus, and it does **not** invent Android ``protectionLevel``
multi-flag strings when those fields are absent.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

PROTECTION_LANE_CONTRACT_VERSION = "2.0.0"
GOVERNANCE_FIELD_CONTRACT_VERSION = "1.0.0"

# Exactly one headline reporting lane per token (v2).
LANE_AOSP_NORMAL = "aosp_normal"
LANE_AOSP_DANGEROUS = "aosp_dangerous"
LANE_AOSP_SIGNATURE = "aosp_signature"
LANE_AOSP_SIGNATURE_PRIVILEGED = "aosp_signature_privileged"
LANE_OEM_PLATFORM = "oem_platform"
LANE_GOOGLE_PLATFORM = "google_platform"
LANE_APP_DEFINED = "app_defined"
LANE_UNKNOWN_UNRESOLVED = "unknown_unresolved"

# Deprecated v1.1 aliases kept for migration / tests that still mention names.
LANE_AOSP_PROTECTION_UNRESOLVED = "aosp_protection_unresolved"  # folded → unknown_unresolved in v2
LANE_OEM_OR_GOOGLE = "oem_or_google"  # split → oem_platform | google_platform in v2

CANONICAL_PROTECTION_LANES: tuple[str, ...] = (
    LANE_AOSP_NORMAL,
    LANE_AOSP_DANGEROUS,
    LANE_AOSP_SIGNATURE,
    LANE_AOSP_SIGNATURE_PRIVILEGED,
    LANE_OEM_PLATFORM,
    LANE_GOOGLE_PLATFORM,
    LANE_APP_DEFINED,
    LANE_UNKNOWN_UNRESOLVED,
)

CONCEPTUAL_LANE_NOTES: dict[str, str] = {
    "AOSP normal": LANE_AOSP_NORMAL,
    "AOSP dangerous": LANE_AOSP_DANGEROUS,
    "AOSP signature": (
        f"{LANE_AOSP_SIGNATURE} when base_protection_level=signature is present; "
        f"otherwise tokens land in {LANE_UNKNOWN_UNRESOLVED}"
    ),
    "AOSP signature|privileged": (
        f"{LANE_AOSP_SIGNATURE_PRIVILEGED} when signature + privileged flag present; "
        f"otherwise unresolved"
    ),
    "OEM platform": LANE_OEM_PLATFORM,
    "Google platform": LANE_GOOGLE_PLATFORM,
    "App-defined permission": LANE_APP_DEFINED,
    "Unknown or unresolved": LANE_UNKNOWN_UNRESOLVED,
}

REPORTABILITY_STATUSES: tuple[str, ...] = (
    "descriptive_common",
    "descriptive_type_enriched",
    "family_balanced_supported",
    "dominant_family_sensitive",
    "single_family_dominated",
    "insufficient_family_support",
    "insufficient_sample_support",
    "effect_too_small",
    "not_significant_after_fdr",
    "protection_level_unresolved",
    "app_defined_high_cardinality",
    "identity_risk",
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
    "app_defined_min_families_for_headline": 3,
    "app_defined_max_family_concentration": 0.85,
    "headline_strength_strong_fb": 0.20,
    "headline_strength_moderate_fb": 0.10,
    "leave_dominant_spearman_sensitive": 0.85,
    "leave_dominant_jsd_sensitive": 0.10,
    "leave_dominant_max_shift_pp_sensitive": 10.0,
}


def classify_headline_strength(
    *,
    reportability_status: str,
    family_balanced_prevalence: float | None,
    thresholds: Mapping[str, Any] | None = None,
) -> str:
    """Tier already-supported headlines by family-balanced prevalence."""
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


def _norm_protection_level(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_privileged_flag(flags: Any) -> bool:
    text = str(flags or "").strip().lower()
    if not text:
        return False
    return "privileged" in text.replace("|", " ").replace(",", " ").split() or "privileged" in text


def classify_protection_lane(
    *,
    pi_bucket_source: Any = "",
    dangerous_bucket: Any = "",
    permission_string: Any = "",
    base_protection_level: Any = "",
    protection_flags: Any = "",
) -> str:
    """Map one permission token to exactly one canonical reporting lane.

    Precedence (deterministic, contract 2.0.0):

    1. ``pi_bucket_source == UNKNOWN`` → ``unknown_unresolved``
    2. App-defined source or ``dangerous_bucket == app_defined`` → ``app_defined``
    3. OEM source or ``oem_vendor`` bucket → ``oem_platform``
    4. GOOGLE source or ``google`` bucket → ``google_platform``
    5. When structured ``base_protection_level`` is present for AOSP:
       - signature + privileged flag → ``aosp_signature_privileged``
       - signature → ``aosp_signature``
    6. AOSP + ``normal`` → ``aosp_normal``
    7. AOSP + ``dangerous`` → ``aosp_dangerous``
    8. else → ``unknown_unresolved``

    ``permission_string`` is not used to invent signature/privileged lanes from
    name heuristics.
    """
    _ = permission_string
    src = _norm_source(pi_bucket_source)
    dang = _norm_bucket(dangerous_bucket)
    base = _norm_protection_level(base_protection_level)

    if src == "UNKNOWN":
        return LANE_UNKNOWN_UNRESOLVED
    if src == "APP_DEFINED" or dang == "app_defined":
        return LANE_APP_DEFINED
    if src == "OEM" or dang == "oem_vendor":
        return LANE_OEM_PLATFORM
    if src == "GOOGLE" or dang == "google":
        return LANE_GOOGLE_PLATFORM

    if src == "AOSP" and base:
        if base == "signature":
            if _has_privileged_flag(protection_flags):
                return LANE_AOSP_SIGNATURE_PRIVILEGED
            return LANE_AOSP_SIGNATURE
        if base == "normal" or dang == "normal":
            return LANE_AOSP_NORMAL
        if base == "dangerous" or dang == "dangerous":
            return LANE_AOSP_DANGEROUS
        return LANE_UNKNOWN_UNRESOLVED

    if src == "AOSP":
        if dang == "normal":
            return LANE_AOSP_NORMAL
        if dang == "dangerous":
            return LANE_AOSP_DANGEROUS
        # AOSP with unknown/empty dangerous_bucket and no structured protection
        # level → unresolved (do not invent signature/privileged).
        return LANE_UNKNOWN_UNRESOLVED
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
    """Copy audit frame and attach lane + preserved protection fact columns."""
    frame = audit.copy()
    src_col = "pi_bucket_source" if "pi_bucket_source" in frame.columns else None
    dang_col = "dangerous_bucket" if "dangerous_bucket" in frame.columns else None
    perm_col = "permission_string" if "permission_string" in frame.columns else None
    base_col = "base_protection_level" if "base_protection_level" in frame.columns else None
    flags_col = "protection_flags" if "protection_flags" in frame.columns else None

    if src_col is None and dang_col is None and base_col is None:
        frame["protection_governance_lane"] = LANE_UNKNOWN_UNRESOLVED
        frame["headline_lane"] = LANE_UNKNOWN_UNRESOLVED
        frame["governance_namespace"] = ""
        frame["base_protection_level"] = ""
        frame["protection_flags"] = ""
        return frame

    lanes: list[str] = []
    namespaces: list[str] = []
    bases: list[str] = []
    flags: list[str] = []
    for row in frame.to_dict(orient="records"):
        src = row.get(src_col, "") if src_col else ""
        dang = row.get(dang_col, "") if dang_col else ""
        perm = row.get(perm_col, "") if perm_col else ""
        base = row.get(base_col, "") if base_col else ""
        fl = row.get(flags_col, "") if flags_col else ""
        lane = classify_protection_lane(
            pi_bucket_source=src,
            dangerous_bucket=dang,
            permission_string=perm,
            base_protection_level=base,
            protection_flags=fl,
        )
        lanes.append(lane)
        namespaces.append(_norm_source(src))
        bases.append(_norm_protection_level(base))
        flags.append(str(fl or "").strip())
    frame["protection_governance_lane"] = lanes
    frame["headline_lane"] = lanes
    frame["governance_namespace"] = namespaces
    if base_col is None:
        frame["base_protection_level"] = bases
    if flags_col is None:
        frame["protection_flags"] = flags
    return frame


def permission_lane_lookup(audit: pd.DataFrame) -> dict[str, str]:
    """Map lowercased permission_string → headline lane."""
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


def governance_field_contract_rows(audit: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    """Durable field-contract rows (observed values from audit when provided)."""
    frame = audit if audit is not None else pd.DataFrame()

    def _obs(col: str) -> tuple[str, int, float, bool]:
        if frame.empty or col not in frame.columns:
            return "field absent from completed-run audit", int(len(frame)), 1.0, False
        series = frame[col]
        nullish = int(series.isna().sum())
        if series.dtype == object:
            nullish += int(series.fillna("").astype(str).str.strip().isin(["", "nan", "None"]).sum())
        rate = float(nullish) / float(max(len(series), 1))
        vals = sorted({str(v) for v in series.dropna().astype(str).unique().tolist()})
        observed = ",".join(vals[:12]) if len(vals) <= 12 else f"{len(vals)} distinct values"
        return observed, nullish, rate, True

    specs = [
        ("permission_string", "Canonical permission token", "permission_feature_audit.csv", True),
        ("pi_bucket_source", "Governance / namespace bucket", "permission_feature_audit.csv", True),
        ("dangerous_bucket", "Coarse protection/governance class", "permission_feature_audit.csv", True),
        ("feature_column", "ML feature column name", "permission_feature_audit.csv", True),
        ("feature_group", "Capability grouping label", "permission_feature_audit.csv", False),
        ("global_support", "Cohort-wide positive sample support", "permission_feature_audit.csv", True),
        ("max_family_support", "Max positives in one family", "permission_feature_audit.csv", False),
        ("max_type_support", "Max positives in one type", "permission_feature_audit.csv", False),
        ("retained_after_pruning", "Whether token retained for modeling", "permission_feature_audit.csv", True),
        ("pruned_as_leakage", "Leakage pruning flag", "permission_feature_audit.csv", False),
        (
            "base_protection_level",
            "Structured Android base protection level",
            "permission_feature_audit.csv (optional)",
            False,
        ),
        (
            "protection_flags",
            "Structured Android protection flags (privileged, …)",
            "permission_feature_audit.csv (optional)",
            False,
        ),
        (
            "normalized_permission / alias_resolution",
            "Explicit alias-resolution column",
            "absent offline",
            False,
        ),
        (
            "review_status / governance_confidence",
            "Human review / confidence fields",
            "absent offline",
            False,
        ),
    ]
    rows: list[dict[str, Any]] = []
    for field, meaning, source, headline_usable_default in specs:
        observed, null_count, null_rate, present = _obs(field)
        usable = bool(headline_usable_default and present and null_rate < 1.0)
        ambiguity = "Use observed values only; do not invent"
        if field in {"base_protection_level", "protection_flags"}:
            ambiguity = (
                "Absent on completed-run audit → signature/privileged headline lanes stay empty; "
                "AOSP+unknown dangerous_bucket → unknown_unresolved"
            )
            usable = False
        if field.startswith("normalized_permission") or field.startswith("review_status"):
            ambiguity = "Not present; do not invent"
            usable = False
        rows.append(
            {
                "field_name": field,
                "source_artifact": source,
                "meaning": meaning,
                "observed_values": observed,
                "null_count": null_count if present else "",
                "null_rate": round(null_rate, 6) if present else 1.0,
                "authority": "LOCAL_OBSERVED" if present else "ABSENT",
                "usable_in_headline_analysis": usable,
                "ambiguity_handling": ambiguity,
                "governance_field_contract_version": GOVERNANCE_FIELD_CONTRACT_VERSION,
            }
        )
    return rows


def governance_field_contract_table() -> list[dict[str, str]]:
    """Backward-compatible compact contract (string fields only)."""
    return [
        {
            "source_field": row["field_name"],
            "meaning": str(row["meaning"]),
            "allowed_values_observed": str(row["observed_values"]),
            "null_rate": str(row["null_rate"]),
            "mapping_authority": str(row["source_artifact"]),
            "report_lane": "see protection-lane contract 2.0.0",
            "ambiguity_handling": str(row["ambiguity_handling"]),
        }
        for row in governance_field_contract_rows()
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
    leave_dominant_sensitive: bool = False,
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
    lane_s = str(lane)
    if lane_s in {LANE_UNKNOWN_UNRESOLVED, LANE_AOSP_PROTECTION_UNRESOLVED}:
        return "protection_level_unresolved"
    if lane_s == LANE_APP_DEFINED:
        if int(families_with_permission) < int(thr["app_defined_min_families_for_headline"]):
            return "identity_risk"
        if float(largest_family_share) >= float(thr["app_defined_max_family_concentration"]):
            return "identity_risk"
        return "app_defined_high_cardinality"
    if int(positive_samples) < int(thr["min_sample_support"]):
        return "insufficient_sample_support"
    if int(families_with_permission) < int(thr["min_family_support"]):
        return "insufficient_family_support"
    if float(largest_family_share) >= float(thr["dominance_threshold"]):
        return "single_family_dominated"
    if leave_dominant_sensitive:
        return "dominant_family_sensitive"
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
        "governance_field_contract_version": GOVERNANCE_FIELD_CONTRACT_VERSION,
        "canonical_lanes": list(CANONICAL_PROTECTION_LANES),
        "conceptual_lane_notes": CONCEPTUAL_LANE_NOTES,
        "reportability_statuses": list(REPORTABILITY_STATUSES),
        "default_thresholds": dict(DEFAULT_THRESHOLDS),
        "classification_precedence": [
            "UNKNOWN source → unknown_unresolved",
            "APP_DEFINED source or app_defined bucket → app_defined",
            "OEM source or oem_vendor bucket → oem_platform",
            "GOOGLE source or google bucket → google_platform",
            "AOSP + structured signature(+privileged) → aosp_signature[_privileged]",
            "AOSP + normal → aosp_normal",
            "AOSP + dangerous → aosp_dangerous",
            "else → unknown_unresolved",
        ],
        "preserved_fact_columns": [
            "base_protection_level",
            "protection_flags",
            "governance_namespace",
            "headline_lane",
        ],
        "signature_privileged_note": (
            "Structured signature/privileged protection flags are absent from the "
            "completed-run permission_feature_audit.csv unless those columns are added; "
            "aosp_signature* lanes remain empty when fields are missing."
        ),
        "governance_field_contract": governance_field_contract_table(),
        "v1_migration": {
            "aosp_protection_unresolved": "unknown_unresolved (when structured flags absent)",
            "oem_or_google": "split into oem_platform | google_platform",
        },
    }


__all__ = [
    "PROTECTION_LANE_CONTRACT_VERSION",
    "GOVERNANCE_FIELD_CONTRACT_VERSION",
    "CANONICAL_PROTECTION_LANES",
    "CONCEPTUAL_LANE_NOTES",
    "REPORTABILITY_STATUSES",
    "DEFAULT_THRESHOLDS",
    "LANE_AOSP_NORMAL",
    "LANE_AOSP_DANGEROUS",
    "LANE_AOSP_SIGNATURE",
    "LANE_AOSP_SIGNATURE_PRIVILEGED",
    "LANE_OEM_PLATFORM",
    "LANE_GOOGLE_PLATFORM",
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
    "governance_field_contract_rows",
    "governance_field_contract_table",
    "classify_permission_row_reportability",
    "classify_headline_strength",
    "contract_metadata",
]
