"""Normalized permission-pattern scoring for ObsidianDroid canonical.

canonical uses a 0–9 structural association ladder. Levels describe declared-capability
pattern strength across malware types/families — not proof of malware behavior,
runtime causality, or dynamic-analysis findings.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

import pandas as pd

PATTERN_SCALE_NAME = "obsidiandroid_canonical_structural_permission_pattern_0_9"
PATTERN_SCALE_VERSION = "canonical_structural_0_9"

PATTERN_LEVEL_LABELS: dict[int, str] = {
    9: "Certain Pattern",
    8: "Very Strong Pattern",
    7: "Strong Pattern",
    6: "Moderate-Strong Pattern",
    5: "Moderate Pattern",
    4: "Weak-Moderate Pattern",
    3: "Weak Pattern",
    2: "Very Weak Pattern",
    1: "Trace Pattern",
    0: "Null / Absent Pattern",
}

PATTERN_LEVEL_DEFINITIONS: dict[int, str] = {
    9: "Structural association is near-universal or overwhelmingly dominant on the focus surface.",
    8: "Very strong recurring structural association with broad support.",
    7: "Strong recurring structural association with adequate support.",
    6: "Moderate-strong association; prevalence-only evidence is capped here without comparative support.",
    5: "Moderate association visible but not dominant.",
    4: "Weak-moderate association with limited comparative separation.",
    3: "Weak association; contrast or support remains thin.",
    2: "Very weak association or conflicting comparative evidence.",
    1: "Trace association only; support or separation is below benchmark evidence floors.",
    0: "No structural association detected on this surface.",
}

PATTERN_CLAIM_BOUNDARY = (
    "Permission-pattern levels describe structural declared-capability associations across "
    "malware types or families. They do not prove malware by themselves, do not establish "
    "runtime behavior or causality, and do not substitute for dynamic analysis."
)

PATTERN_UNSUPPORTED_CLAIMS: tuple[str, ...] = (
    "permission_alone_proves_malware",
    "static_permission_implies_runtime_behavior",
    "pattern_level_establishes_causality",
    "mitre_attack_mapping_as_primary_claim",
    "deep_learning_model_inference",
    "dynamic_analysis_execution",
)

_BASIS_ALIASES: dict[str, str] = {
    "permission_prevalence_by_type": "RAW_PERMISSION+TYPE_LEVEL",
    "permission_prevalence_by_family": "RAW_PERMISSION+FAMILY_LEVEL",
    "signal_prevalence_by_type": "PERMISSION_GROUP+TYPE_LEVEL",
    "signal_prevalence_by_family": "PERMISSION_GROUP+FAMILY_LEVEL",
    "type_enrichment_vs_rest": "RAW_PERMISSION+TYPE_LEVEL+MIXED",
    "family_enrichment_vs_rest": "RAW_PERMISSION+FAMILY_LEVEL+MIXED",
    "type_permission_profile": "RAW_PERMISSION+TYPE_LEVEL",
    "family_permission_profile": "RAW_PERMISSION+FAMILY_LEVEL",
    "capability_bundle_prevalence_by_type": "CAPABILITY+TYPE_LEVEL",
    "capability_bundle_prevalence_by_family": "CAPABILITY+FAMILY_LEVEL",
    "family_permission_similarity": "RAW_PERMISSION+FAMILY_LEVEL+MIXED",
    "type_permission_similarity": "RAW_PERMISSION+TYPE_LEVEL+MIXED",
    "family_signal_similarity": "PERMISSION_GROUP+FAMILY_LEVEL+MIXED",
    "banker_temporal_permission_trend": "RAW_PERMISSION+TYPE_LEVEL+TEMPORAL",
}

COMPARISON_SCOPES: dict[str, str] = {
    "type_vs_global": "Type-level enrichment or prevalence contrasted against the remaining corpus.",
    "family_vs_global": "Family-level enrichment or prevalence contrasted against the remaining corpus.",
    "family_vs_type": "Family-level similarity or profile contrasted within or across type contexts.",
    "type_prevalence": "Type-level prevalence without mandatory background contrast.",
    "family_prevalence": "Family-level prevalence without mandatory background contrast.",
    "pairwise_similarity": "Pairwise permission-profile similarity between families or types.",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if isfinite(out) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def pattern_label_for_level(level: int) -> str:
    """Return the canonical pattern label for a normalized level."""
    clamped = max(0, min(int(level), 9))
    return PATTERN_LEVEL_LABELS.get(clamped, PATTERN_LEVEL_LABELS[3])


def build_pattern_scale_contract() -> dict[str, Any]:
    """Return the machine-readable canonical permission-pattern scale contract."""
    return {
        "scale_name": PATTERN_SCALE_NAME,
        "scale_version": PATTERN_SCALE_VERSION,
        "level_min": 0,
        "level_max": 9,
        "framing": "structural_association_strength",
        "claim_boundary": PATTERN_CLAIM_BOUNDARY,
        "unsupported_claims": list(PATTERN_UNSUPPORTED_CLAIMS),
        "comparison_scopes": dict(COMPARISON_SCOPES),
        "levels": [
            {
                "level": level,
                "label": PATTERN_LEVEL_LABELS[level],
                "definition": PATTERN_LEVEL_DEFINITIONS[level],
            }
            for level in sorted(PATTERN_LEVEL_LABELS)
        ],
    }


def normalize_pattern_basis(basis: str) -> str:
    """Normalize a pattern basis string to a stable machine-readable enum shape."""
    raw = str(basis).strip()
    if not raw:
        return "MIXED"
    normalized = _BASIS_ALIASES.get(raw.lower())
    if normalized:
        return normalized
    return raw.upper().replace(" ", "_")


def _has_comparative_evidence(basis: str) -> bool:
    normalized = normalize_pattern_basis(basis)
    return "MIXED" in normalized or "TEMPORAL" in normalized or "LINEAGE_SUPPORTED" in normalized


def _default_confidence(level: int, *, support: int = 0, basis: str = "MIXED") -> str:
    comparative = _has_comparative_evidence(basis)
    if level <= 0:
        return "none"
    if level <= 2:
        return "very_low" if support < 5 else "low"
    if level == 3:
        return "low" if support >= 3 else "very_low"
    if not comparative:
        if level <= 4:
            return "low" if support < 10 else "moderate"
        return "moderate" if support < 10 else "high"
    if level <= 5:
        return "moderate"
    if level <= 7:
        return "high" if support >= 5 else "moderate"
    return "very_high" if support >= 10 else "high"


def _pattern_payload(
    *,
    score: float,
    level: int,
    basis: str,
    reason: str,
    support: int = 0,
    confidence: str | None = None,
) -> dict[str, Any]:
    normalized = max(0, min(int(level), 9))
    normalized_basis = normalize_pattern_basis(basis)
    return {
        "pattern_score": round(_safe_float(score), 2),
        "pattern_level": normalized,
        "pattern_label": pattern_label_for_level(normalized),
        "pattern_basis": normalized_basis,
        "pattern_confidence": str(
            confidence or _default_confidence(normalized, support=support, basis=normalized_basis)
        ).strip(),
        "pattern_reason": str(reason).strip(),
    }


def classify_prevalence_pattern(
    *,
    prevalence_pct: float,
    positive_count: int,
    group_support: int,
    basis: str,
) -> dict[str, Any]:
    """Classify a prevalence-only signal into the canonical structural pattern ladder."""
    support = max(_safe_int(group_support), 0)
    positive = max(_safe_int(positive_count), 0)
    prevalence = _safe_float(prevalence_pct)
    score = max(0.0, min(prevalence, 100.0))
    if support <= 0 or positive <= 0 or prevalence <= 0.0:
        return _pattern_payload(
            score=0.0,
            level=0,
            basis=basis,
            support=support,
            reason="structural association absent on this surface",
        )
    if support < 3:
        return _pattern_payload(
            score=score,
            level=1,
            basis=basis,
            support=support,
            reason=f"support {support} is below the benchmark evidence floor",
        )
    if prevalence >= 95.0 and positive >= max(5, support - 1):
        level = 9
    elif prevalence >= 85.0 and positive >= 4:
        level = 8
    elif prevalence >= 70.0 and positive >= 3:
        level = 7
    elif prevalence >= 55.0:
        level = 6
    elif prevalence >= 35.0:
        level = 5
    else:
        level = 4
    capped = False
    if level > 6:
        level = 6
        capped = True
    reason = f"prevalence={prevalence:.1f}% across {positive}/{support} samples"
    if capped:
        reason += "; prevalence-only evidence is capped at moderate-strong until comparative support exists"
    return _pattern_payload(
        score=score,
        level=level,
        basis=basis,
        support=support,
        reason=reason,
    )


def classify_enrichment_pattern(
    *,
    subject_prevalence_pct: float,
    background_prevalence_pct: float,
    odds_ratio: float,
    q_value: float,
    support: int,
    basis: str,
) -> dict[str, Any]:
    """Classify enrichment-vs-background evidence into the canonical structural pattern ladder."""
    subject = _safe_float(subject_prevalence_pct)
    background = _safe_float(background_prevalence_pct)
    support_n = max(_safe_int(support), 0)
    or_raw = _safe_float(odds_ratio)
    q_raw = _safe_float(q_value, default=1.0)
    gap = subject - background
    abs_gap = abs(gap)
    strength_or = or_raw if or_raw >= 1.0 else (1.0 / max(or_raw, 1e-9))
    score = max(0.0, min(100.0, (abs_gap * 1.35) + max(0.0, strength_or - 1.0) * 12.0))
    if support_n < 3:
        return _pattern_payload(
            score=score,
            level=1,
            basis=basis,
            support=support_n,
            reason=f"support {support_n} is below the benchmark evidence floor",
        )
    if subject <= 0.0 and background <= 0.0:
        return _pattern_payload(
            score=0.0,
            level=0,
            basis=basis,
            support=support_n,
            reason="structural association absent in both the focus and background surfaces",
        )
    if abs_gap < 5.0 and max(subject, background) >= 20.0:
        return _pattern_payload(
            score=score,
            level=2,
            basis=basis,
            support=support_n,
            reason=f"subject/background prevalences are too similar ({subject:.1f}% vs {background:.1f}%)",
        )
    if not isfinite(or_raw) or not isfinite(q_raw):
        return _pattern_payload(
            score=score,
            level=3,
            basis=basis,
            support=support_n,
            reason="statistical evidence unavailable for this contrast",
        )
    if q_raw >= 0.05:
        if max(subject, background) < 10.0:
            return _pattern_payload(
                score=score,
                level=1,
                basis=basis,
                support=support_n,
                reason="signal remains too sparse to support a structural association",
            )
        if abs_gap < 10.0:
            return _pattern_payload(
                score=score,
                level=2,
                basis=basis,
                support=support_n,
                reason=f"non-significant contrast with similar prevalences ({subject:.1f}% vs {background:.1f}%)",
            )
        return _pattern_payload(
            score=score,
            level=3,
            basis=basis,
            support=support_n,
            reason=f"contrast remains non-significant (q={q_raw:.3g})",
        )
    if strength_or >= 6.0 and abs_gap >= 60.0:
        level = 9
    elif strength_or >= 4.0 and abs_gap >= 45.0:
        level = 8
    elif strength_or >= 2.5 and abs_gap >= 30.0:
        level = 7
    elif strength_or >= 1.75 and abs_gap >= 20.0:
        level = 6
    elif strength_or >= 1.35 and abs_gap >= 10.0:
        level = 5
    else:
        level = 4
    direction = "enriched" if gap >= 0.0 else "depleted"
    return _pattern_payload(
        score=score,
        level=level,
        basis=basis,
        support=support_n,
        reason=(
            f"{direction} vs background; prevalence gap={gap:+.1f} pts, "
            f"OR={or_raw:.2f}, q={q_raw:.3g}"
        ),
    )


def classify_similarity_pattern(
    *,
    cosine_similarity: float,
    jaccard_similarity: float,
    spearman_correlation: float,
    support_a: int,
    support_b: int,
    basis: str,
    same_type: bool | None = None,
) -> dict[str, Any]:
    """Classify pairwise similarity evidence into the canonical structural pattern ladder."""
    cosine = max(0.0, min(_safe_float(cosine_similarity), 1.0))
    jaccard = max(0.0, min(_safe_float(jaccard_similarity), 1.0))
    spearman = max(-1.0, min(_safe_float(spearman_correlation), 1.0))
    spearman_norm = (spearman + 1.0) / 2.0
    min_support = max(0, min(_safe_int(support_a), _safe_int(support_b)))
    max_support = max(_safe_int(support_a), _safe_int(support_b), 0)
    score = ((cosine * 0.45) + (jaccard * 0.35) + (spearman_norm * 0.20)) * 100.0

    if min_support < 3:
        return _pattern_payload(
            score=score,
            level=1,
            basis=basis,
            support=min_support,
            confidence="very_low",
            reason=f"pair support floor is too small ({support_a} vs {support_b})",
        )

    metric_span = max(cosine, jaccard, spearman_norm) - min(cosine, jaccard, spearman_norm)
    if cosine < 0.15 and jaccard < 0.15 and spearman_norm < 0.35:
        return _pattern_payload(
            score=score,
            level=0,
            basis=basis,
            support=min_support,
            confidence="moderate" if min_support >= 10 else "low",
            reason=(
                f"no shared structural association; cosine={cosine:.2f}, "
                f"jaccard={jaccard:.2f}, spearman={spearman:.2f}"
            ),
        )
    if metric_span >= 0.45 or (cosine >= 0.5 and spearman < 0.0) or (cosine >= 0.75 and jaccard >= 0.75 and abs(spearman) < 0.15):
        return _pattern_payload(
            score=score,
            level=2,
            basis=basis,
            support=min_support,
            confidence="moderate" if min_support >= 10 else "low",
            reason=(
                f"similarity metrics disagree; cosine={cosine:.2f}, "
                f"jaccard={jaccard:.2f}, spearman={spearman:.2f}"
            ),
        )

    mean_similarity = (cosine + jaccard + spearman_norm) / 3.0
    if mean_similarity >= 0.90:
        level = 9
    elif mean_similarity >= 0.80:
        level = 8
    elif mean_similarity >= 0.68:
        level = 7
    elif mean_similarity >= 0.55:
        level = 6
    elif mean_similarity >= 0.40:
        level = 5
    else:
        level = 4

    capped_cross_type = False
    if same_type is False and level > 6:
        level = 6
        capped_cross_type = True

    confidence = "high" if min_support >= 10 else "moderate"
    if max_support <= 5:
        confidence = "moderate"
    if same_type is False and confidence == "high":
        confidence = "moderate"
    reason = (
        f"shared-pattern similarity; cosine={cosine:.2f}, "
        f"jaccard={jaccard:.2f}, spearman={spearman:.2f}"
    )
    if capped_cross_type:
        reason += "; cross-type pair is capped at moderate-strong until stronger lineage support exists"
    return _pattern_payload(
        score=score,
        level=level,
        basis=basis,
        support=min_support,
        confidence=confidence,
        reason=reason,
    )


def annotate_prevalence_patterns(
    df: pd.DataFrame,
    *,
    support_col: str,
    positive_count_col: str = "positive_count",
    prevalence_col: str = "prevalence_pct",
    basis: str,
) -> pd.DataFrame:
    """Append normalized canonical pattern fields to prevalence-style outputs."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    pattern_rows = out.apply(
        lambda row: classify_prevalence_pattern(
            prevalence_pct=_safe_float(pd.to_numeric(row.get(prevalence_col), errors="coerce")),
            positive_count=_safe_int(pd.to_numeric(row.get(positive_count_col), errors="coerce")),
            group_support=_safe_int(pd.to_numeric(row.get(support_col), errors="coerce")),
            basis=basis,
        ),
        axis=1,
        result_type="expand",
    )
    for column in pattern_rows.columns:
        out[column] = pattern_rows[column]
    return out


def annotate_enrichment_patterns(
    df: pd.DataFrame,
    *,
    support_col: str,
    subject_prevalence_col: str,
    background_prevalence_col: str,
    odds_ratio_col: str = "odds_ratio",
    q_value_col: str = "q_value_fdr",
    basis: str,
) -> pd.DataFrame:
    """Append normalized canonical pattern fields to enrichment-style outputs."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    pattern_rows = out.apply(
        lambda row: classify_enrichment_pattern(
            subject_prevalence_pct=_safe_float(pd.to_numeric(row.get(subject_prevalence_col), errors="coerce")),
            background_prevalence_pct=_safe_float(pd.to_numeric(row.get(background_prevalence_col), errors="coerce")),
            odds_ratio=_safe_float(pd.to_numeric(row.get(odds_ratio_col), errors="coerce")),
            q_value=_safe_float(pd.to_numeric(row.get(q_value_col), errors="coerce"), default=1.0),
            support=_safe_int(pd.to_numeric(row.get(support_col), errors="coerce")),
            basis=basis,
        ),
        axis=1,
        result_type="expand",
    )
    for column in pattern_rows.columns:
        out[column] = pattern_rows[column]
    return out


def annotate_similarity_patterns(
    df: pd.DataFrame,
    *,
    support_a_col: str,
    support_b_col: str,
    cosine_col: str = "cosine_similarity",
    jaccard_col: str = "jaccard_similarity",
    spearman_col: str = "spearman_correlation",
    same_type_col: str | None = None,
    basis: str,
) -> pd.DataFrame:
    """Append normalized canonical pattern fields to similarity-style outputs."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    pattern_rows = out.apply(
        lambda row: classify_similarity_pattern(
            cosine_similarity=_safe_float(pd.to_numeric(row.get(cosine_col), errors="coerce")),
            jaccard_similarity=_safe_float(pd.to_numeric(row.get(jaccard_col), errors="coerce")),
            spearman_correlation=_safe_float(pd.to_numeric(row.get(spearman_col), errors="coerce")),
            support_a=_safe_int(pd.to_numeric(row.get(support_a_col), errors="coerce")),
            support_b=_safe_int(pd.to_numeric(row.get(support_b_col), errors="coerce")),
            basis=basis,
            same_type=(
                None
                if same_type_col is None
                else bool(pd.to_numeric(row.get(same_type_col), errors="coerce"))
                if pd.notna(row.get(same_type_col))
                else None
            ),
        ),
        axis=1,
        result_type="expand",
    )
    for column in pattern_rows.columns:
        out[column] = pattern_rows[column]
    return out
