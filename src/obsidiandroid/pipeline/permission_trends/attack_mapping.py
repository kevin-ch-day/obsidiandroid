"""ATT&CK-Mobile hypothesis builders from permission prevalence surfaces."""

from __future__ import annotations

from typing import Any

import pandas as pd

from obsidiandroid.governance.mobile_attack_permission_mapping import (
    mobile_attack_permission_mapping_payload,
)


_CONFIDENCE_ORDER = {"direct": 0, "strong_inference": 1, "weak_inference": 2}


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
                    "confidence": str(rule.get("confidence", "") or "").strip(),
                    "required_permission_count": int(len(required_any)),
                    "matched_permission_count": int(len(matched)),
                    "min_required_prevalence": float(min_prevalence),
                    "evidence_permissions": ", ".join(matched),
                    "evidence_prevalence_mean": round(sum(evidence_prevalence) / max(len(evidence_prevalence), 1), 6),
                    "evidence_prevalence_min": round(min(evidence_prevalence), 6),
                    "mapping_version": str(mapping.get("version", "") or "").strip(),
                    "mapping_hash": str(mapping.get("hash", "") or "").strip(),
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
                    f"  - `{row['attack_id']}` {row['attack_name']} [{row['confidence']}] via "
                    f"`{row['evidence_permissions']}`"
                )
    return "\n".join(lines) + "\n"


__all__ = [
    "build_attack_mobile_hypotheses",
    "build_attack_mobile_hypotheses_markdown",
]
