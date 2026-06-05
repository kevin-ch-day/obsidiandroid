"""ATT&CK-Mobile hypothesis builders from permission prevalence surfaces."""

from __future__ import annotations

from typing import Any

import pandas as pd

from obsidiandroid.governance.mobile_attack_permission_mapping import (
    mobile_attack_permission_mapping_payload,
)
from obsidiandroid.pipeline.permission_trends.pattern_framework import (
    classify_prevalence_pattern,
    normalize_pattern_basis,
    pattern_label_for_level,
)


_CONFIDENCE_ORDER = {"direct": 0, "strong_inference": 1, "weak_inference": 2}
_PATTERN_CONFIDENCE_ORDER = {
    "none": 0,
    "very_low": 1,
    "low": 2,
    "moderate": 3,
    "high": 4,
    "very_high": 5,
}
_PATTERN_CONFIDENCE_BY_ATTACK_CONFIDENCE = {
    "direct": "high",
    "strong_inference": "moderate",
    "weak_inference": "low",
}
_HYPOTHESIS_LEVEL_CAP = {
    "direct": 6,
    "strong_inference": 5,
    "weak_inference": 4,
}


def _aggregate_hypothesis_pattern(
    *,
    matched_rows: list[pd.Series],
    group_kind: str,
    mapping_confidence: str,
    matched_permission_count: int,
) -> dict[str, Any]:
    evidence_levels = [
        int(pd.to_numeric(row.get("pattern_level", 3), errors="coerce"))
        for row in matched_rows
    ]
    evidence_scores = [
        float(pd.to_numeric(row.get("pattern_score", 0.0), errors="coerce"))
        for row in matched_rows
    ]
    evidence_confidences = [
        str(row.get("pattern_confidence", "low") or "low").strip().lower()
        for row in matched_rows
    ]
    level_cap = _HYPOTHESIS_LEVEL_CAP.get(str(mapping_confidence).strip().lower(), 4)
    base_level = min(evidence_levels) if evidence_levels else 1
    pattern_level = max(0, min(base_level, level_cap))
    mean_score = round(sum(evidence_scores) / max(len(evidence_scores), 1), 2) if evidence_scores else 0.0
    mapping_conf_cap = _PATTERN_CONFIDENCE_BY_ATTACK_CONFIDENCE.get(
        str(mapping_confidence).strip().lower(),
        "low",
    )
    confidence_rank = min(
        [_PATTERN_CONFIDENCE_ORDER.get(mapping_conf_cap, 2)]
        + [_PATTERN_CONFIDENCE_ORDER.get(value, 2) for value in evidence_confidences]
    )
    pattern_confidence = next(
        key for key, value in _PATTERN_CONFIDENCE_ORDER.items() if value == confidence_rank
    )
    group_level = "TYPE_LEVEL" if str(group_kind).strip().lower() == "type" else "FAMILY_LEVEL"
    evidence_labels = sorted({pattern_label_for_level(level) for level in evidence_levels})
    evidence_label_text = ", ".join(evidence_labels) if evidence_labels else pattern_label_for_level(pattern_level)
    evidence_bases = sorted(
        {
            str(row.get("pattern_basis", "") or "").strip()
            for row in matched_rows
            if str(row.get("pattern_basis", "") or "").strip()
        }
    )
    if evidence_bases:
        normalized_bases = {normalize_pattern_basis(value) for value in evidence_bases}
        if len(normalized_bases) == 1:
            base_basis = normalized_bases.pop()
            if "+TYPE_LEVEL" in base_basis:
                pattern_basis = "BEHAVIOR+TYPE_LEVEL+MIXED"
            elif "+FAMILY_LEVEL" in base_basis:
                pattern_basis = "BEHAVIOR+FAMILY_LEVEL+MIXED"
            else:
                pattern_basis = f"BEHAVIOR+{group_level}+MIXED"
        else:
            pattern_basis = f"BEHAVIOR+{group_level}+MIXED"
    else:
        pattern_basis = f"BEHAVIOR+{group_level}+MIXED"
    return {
        "pattern_score": mean_score,
        "pattern_level": pattern_level,
        "pattern_label": pattern_label_for_level(pattern_level),
        "pattern_basis": pattern_basis,
        "pattern_confidence": pattern_confidence,
        "pattern_reason": (
            f"permission-derived hypothesis from {matched_permission_count} matched permissions; "
            f"upstream evidence={evidence_label_text}; mapping_confidence={mapping_confidence}"
        ),
    }


def _permission_pattern_row(
    *,
    permission_rows: pd.DataFrame,
    prevalence_field: str,
    sample_count_field: str,
    basis: str,
) -> pd.Series | None:
    if permission_rows.empty:
        return None
    top = permission_rows.sort_values(by=prevalence_field, ascending=False, kind="mergesort").iloc[0].copy()
    missing_pattern_fields = {
        "pattern_level",
        "pattern_score",
        "pattern_confidence",
        "pattern_basis",
        "pattern_reason",
    } - set(permission_rows.columns)
    if missing_pattern_fields:
        fallback = classify_prevalence_pattern(
            prevalence_pct=float(pd.to_numeric(top.get(prevalence_field), errors="coerce") or 0.0) * 100.0,
            positive_count=int(
                round(
                    float(pd.to_numeric(top.get(prevalence_field), errors="coerce") or 0.0)
                    * float(pd.to_numeric(top.get(sample_count_field), errors="coerce") or 0.0)
                )
            ),
            group_support=int(pd.to_numeric(top.get(sample_count_field), errors="coerce") or 0),
            basis=basis,
        )
        for key, value in fallback.items():
            top[key] = value
    return top


def build_attack_mobile_hypotheses(
    *,
    prevalence_df: pd.DataFrame,
    run_id: str,
    group_field: str,
    group_kind: str,
    sample_count_field: str = "sample_count",
    prevalence_field: str = "prevalence",
    permission_field: str = "permission",
) -> pd.DataFrame:
    """Build ATT&CK-Mobile capability hypotheses from permission prevalence rows."""
    if (
        not isinstance(prevalence_df, pd.DataFrame)
        or prevalence_df.empty
        or group_field not in prevalence_df.columns
        or permission_field not in prevalence_df.columns
        or prevalence_field not in prevalence_df.columns
    ):
        return pd.DataFrame()

    mapping = mobile_attack_permission_mapping_payload()
    rules = list(mapping.get("rules", []) or [])
    if not rules:
        return pd.DataFrame()

    work = prevalence_df.copy()
    work[group_field] = work[group_field].fillna("").astype(str).str.strip()
    work[permission_field] = work[permission_field].fillna("").astype(str).str.strip().str.lower()
    work[prevalence_field] = pd.to_numeric(work[prevalence_field], errors="coerce").fillna(0.0)
    if sample_count_field in work.columns:
        work[sample_count_field] = pd.to_numeric(work[sample_count_field], errors="coerce").fillna(0).astype(int)
    else:
        work[sample_count_field] = 0
    work = work[(work[group_field] != "") & (work[permission_field] != "")]
    if work.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for group_value, group in work.groupby(group_field, dropna=False):
        permission_prevalence = (
            group.groupby(permission_field)[prevalence_field].max().to_dict()
        )
        sample_count = int(group[sample_count_field].max()) if sample_count_field in group.columns else 0
        for rule in rules:
            required_any = [str(value).strip().lower() for value in rule.get("required_any", []) if str(value).strip()]
            required_count = int(rule.get("required_count", 1) or 1)
            min_prevalence = float(rule.get("min_prevalence", 0.0) or 0.0)
            matched = [
                permission
                for permission in required_any
                if float(permission_prevalence.get(permission, 0.0)) >= min_prevalence
            ]
            if len(matched) < required_count:
                continue
            evidence_prevalence = [float(permission_prevalence.get(permission, 0.0)) for permission in matched]
            matched_rows = []
            for permission in matched:
                permission_rows = group[group[permission_field] == permission]
                basis = f"permission_prevalence_by_{'type' if str(group_kind).strip().lower() == 'type' else 'family'}"
                top_row = _permission_pattern_row(
                    permission_rows=permission_rows,
                    prevalence_field=prevalence_field,
                    sample_count_field=sample_count_field,
                    basis=basis,
                )
                if top_row is not None:
                    matched_rows.append(top_row)
            attack_confidence = str(rule.get("confidence", "") or "").strip()
            pattern_payload = _aggregate_hypothesis_pattern(
                matched_rows=matched_rows,
                group_kind=group_kind,
                mapping_confidence=attack_confidence,
                matched_permission_count=len(matched),
            )
            rows.append(
                {
                    "run_id": run_id,
                    "group_kind": group_kind,
                    "group_value": str(group_value).strip(),
                    "sample_count": int(sample_count),
                    "attack_id": str(rule.get("attack_id", "") or "").strip(),
                    "attack_name": str(rule.get("attack_name", "") or "").strip(),
                    "attack_url": str(rule.get("attack_url", "") or "").strip(),
                    "tactic": str(rule.get("tactic", "") or "").strip(),
                    "confidence": attack_confidence,
                    "required_permission_count": int(len(required_any)),
                    "matched_permission_count": int(len(matched)),
                    "min_required_prevalence": float(min_prevalence),
                    "evidence_permissions": ", ".join(matched),
                    "evidence_prevalence_mean": round(sum(evidence_prevalence) / max(len(evidence_prevalence), 1), 6),
                    "evidence_prevalence_min": round(min(evidence_prevalence), 6),
                    "mapping_version": str(mapping.get("version", "") or "").strip(),
                    "mapping_hash": str(mapping.get("hash", "") or "").strip(),
                    **pattern_payload,
                }
            )
    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    out = out.sort_values(
        by=[
            "group_kind",
            "sample_count",
            "confidence",
            "matched_permission_count",
            "evidence_prevalence_mean",
            "attack_id",
            "group_value",
        ],
        ascending=[True, False, True, False, False, True, True],
        key=lambda series: (
            series.map(_CONFIDENCE_ORDER).fillna(9)
            if series.name == "confidence"
            else series
        ),
        kind="mergesort",
    ).reset_index(drop=True)
    return out


def build_attack_mobile_hypotheses_markdown(
    *,
    hypotheses_df: pd.DataFrame,
    run_id: str,
) -> str:
    """Render operator-readable ATT&CK-Mobile hypothesis summary."""
    lines = [
        f"# ATT&CK-Mobile Hypotheses ({run_id})",
        "",
        "Permission-derived capability hypotheses only.",
        "These are static-capability inferences from declared permission prevalence surfaces, not proof of runtime behavior.",
    ]
    if not isinstance(hypotheses_df, pd.DataFrame) or hypotheses_df.empty:
        lines.extend(["", "- No ATT&CK-Mobile hypotheses met the configured prevalence rules."])
        return "\n".join(lines) + "\n"

    for group_kind, group_df in hypotheses_df.groupby("group_kind", sort=False):
        lines.extend(["", f"## {str(group_kind).replace('_', ' ').title()}"])
        for group_value, subgroup in group_df.groupby("group_value", sort=False):
            sample_count = int(pd.to_numeric(subgroup["sample_count"], errors="coerce").fillna(0).max())
            lines.append(f"- `{group_value}` (n={sample_count})")
            for _, row in subgroup.head(4).iterrows():
                lines.append(
                    f"  - `{row['attack_id']}` {row['attack_name']} [{row['confidence']}; "
                    f"{row.get('pattern_label', 'Inconclusive')}, {row.get('pattern_confidence', 'low')}] via "
                    f"`{row['evidence_permissions']}`"
                )
    return "\n".join(lines) + "\n"


__all__ = [
    "build_attack_mobile_hypotheses",
    "build_attack_mobile_hypotheses_markdown",
]
