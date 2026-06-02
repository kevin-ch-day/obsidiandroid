"""Cohort target-surface summaries for family/type/taxonomy supervision tuning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.governance import family_tier_authority
from obsidiandroid.governance.support_floor_policy import SUPPORT_DIAGNOSTIC_FLOORS


def _resolve_support_floor_mode(samples_df: pd.DataFrame) -> str:
    attrs = getattr(samples_df, "attrs", {}) if isinstance(getattr(samples_df, "attrs", None), dict) else {}
    return str(attrs.get("support_floor_mode", "") or "").strip().lower()


def _resolve_benchmark_support_floor(samples_df: pd.DataFrame, min_support: int | None) -> int | None:
    mode = _resolve_support_floor_mode(samples_df)
    if mode != "benchmark_eligibility":
        return None
    if min_support in (None, ""):
        return None
    return max(1, int(min_support))

def _clean_token(value: Any, *, generic_tokens: set[str] | None = None) -> str:
    blocked = generic_tokens if generic_tokens is not None else set(family_tier_authority.EMPTY_TOKENS)
    return family_tier_authority.clean_tier_token(value, generic_tokens=blocked)


def _series_from(df: pd.DataFrame, column: str, *, generic_tokens: set[str] | None = None) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    return df[column].map(lambda value: _clean_token(value, generic_tokens=generic_tokens))


def _build_family_within_type(df: pd.DataFrame) -> pd.Series:
    family = _series_from(df, "family_canonical")
    type_slug = _series_from(df, "type_slug")
    mask = family.ne("") & type_slug.ne("")
    out = pd.Series([""] * len(df), index=df.index, dtype="object")
    out.loc[mask] = type_slug.loc[mask] + "::" + family.loc[mask]
    return out


def _numeric_family_id_series(df: pd.DataFrame) -> pd.Series:
    if "family_id" not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")
    return pd.to_numeric(df["family_id"], errors="coerce")


def _first_present_token(*values: Any) -> str:
    for value in values:
        token = _clean_token(value)
        if token:
            return token
    return ""


def _major_minor_generic_unresolved_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    return family_tier_authority.build_family_tier_masks(df)


def _build_family_tier_summary(df: pd.DataFrame, *, benchmark_support_floor: int | None) -> dict[str, Any]:
    masks = _major_minor_generic_unresolved_masks(df)
    family_canonical = _series_from(df, "family_canonical")
    type_slug = _series_from(df, "type_slug")
    major_payload = family_tier_authority.major_family_authority_payload()
    generic_payload = family_tier_authority.generic_coarse_token_policy_payload()
    major_set = family_tier_authority.major_family_name_set()

    support_rows: list[dict[str, Any]] = []
    mapped_df = df[masks["mapped_family"]].copy()
    if not mapped_df.empty:
        mapped_df = mapped_df.assign(
            family_canonical_norm=family_canonical.loc[mapped_df.index],
            type_slug_norm=type_slug.loc[mapped_df.index],
        )
        support = (
            mapped_df.groupby("family_canonical_norm", dropna=False)
            .agg(
                sample_count=("family_canonical_norm", "size"),
                type_slug=("type_slug_norm", lambda values: next((v for v in values if str(v).strip()), "")),
            )
            .reset_index()
            .rename(columns={"family_canonical_norm": "family_canonical"})
            .sort_values(by=["sample_count", "family_canonical"], ascending=[False, True], kind="mergesort")
        )
        support["family_tier"] = support["family_canonical"].map(
            lambda value: "major" if str(value).strip().lower() in major_set else "minor"
        )
        support["authority_eligible"] = True
        if benchmark_support_floor is not None:
            support["benchmark_eligible"] = support["sample_count"].map(
                lambda value: int(value) >= int(benchmark_support_floor)
            )
            support["benchmark_exclusion_reason"] = support["benchmark_eligible"].map(
                lambda value: "" if bool(value) else f"support_below_{int(benchmark_support_floor)}"
            )
        else:
            support["benchmark_eligible"] = pd.NA
            support["benchmark_exclusion_reason"] = ""
        support_rows = support.to_dict(orient="records")
        major_present = [str(row.get("family_canonical", "")).strip().lower() for row in support_rows if row.get("family_tier") == "major"]
        minor_present = [str(row.get("family_canonical", "")).strip().lower() for row in support_rows if row.get("family_tier") == "minor"]
    else:
        major_present = []
        minor_present = []

    major_missing = sorted(major_set - set(major_present))

    floor_rows: list[dict[str, Any]] = []
    for floor in SUPPORT_DIAGNOSTIC_FLOORS:
        major_family_count = sum(
            1 for row in support_rows if row.get("family_tier") == "major" and int(row.get("sample_count", 0)) >= floor
        )
        major_row_count = sum(
            int(row.get("sample_count", 0))
            for row in support_rows
            if row.get("family_tier") == "major" and int(row.get("sample_count", 0)) >= floor
        )
        minor_family_count = sum(
            1 for row in support_rows if row.get("family_tier") == "minor" and int(row.get("sample_count", 0)) >= floor
        )
        minor_row_count = sum(
            int(row.get("sample_count", 0))
            for row in support_rows
            if row.get("family_tier") == "minor" and int(row.get("sample_count", 0)) >= floor
        )
        type_trainable = (
            int(
                type_slug[masks["type_target_eligible"]]
                .value_counts()
                .loc[lambda s: s >= floor]
                .shape[0]
            )
            if int(masks["type_target_eligible"].sum()) > 0
            else 0
        )
        floor_rows.append(
            {
                "support_floor": int(floor),
                "major_family_count": int(major_family_count),
                "major_sample_count": int(major_row_count),
                "minor_family_count": int(minor_family_count),
                "minor_sample_count": int(minor_row_count),
                "family_target_family_count": int(major_family_count + minor_family_count),
                "family_target_sample_count": int(major_row_count + minor_row_count),
                "type_target_class_count": int(type_trainable),
            }
        )

    tier_counts = {
        "total_android_malware_samples": int(len(df)),
        "mapped_family_samples": int(masks["mapped_family"].sum()),
        "major_family_samples": int(masks["major_family"].sum()),
        "minor_family_samples": int(masks["minor_family"].sum()),
        "generic_coarse_label_samples": int(masks["generic_coarse"].sum()),
        "unresolved_samples": int(masks["unresolved"].sum()),
        "type_target_eligible_samples": int(masks["type_target_eligible"].sum()),
        "family_target_eligible_samples": int(masks["family_target_eligible"].sum()),
    }
    if benchmark_support_floor is not None and support_rows:
        benchmark_families = [
            row for row in support_rows if bool(row.get("benchmark_eligible"))
        ]
        benchmark_samples = sum(int(row.get("sample_count", 0)) for row in benchmark_families)
        excluded_rows = [
            row for row in support_rows if row.get("benchmark_exclusion_reason")
        ]
        excluded_samples = sum(int(row.get("sample_count", 0)) for row in excluded_rows)
    else:
        benchmark_families = []
        benchmark_samples = 0
        excluded_rows = []
        excluded_samples = 0
    tier_counts["authority_eligible_samples"] = int(tier_counts["family_target_eligible_samples"])
    tier_counts["benchmark_eligible_samples"] = int(benchmark_samples)
    tier_counts["excluded_below_benchmark_support_samples"] = int(excluded_samples)
    tier_counts["excluded_non_family_target_samples"] = int(
        len(df) - int(tier_counts["family_target_eligible_samples"])
    )
    return {
        "tier_counts": tier_counts,
        "benchmark_support_policy": {
            "support_floor_mode": "benchmark_eligibility" if benchmark_support_floor is not None else "",
            "benchmark_min_support": int(benchmark_support_floor) if benchmark_support_floor is not None else None,
            "authority_eligible_family_count": int(len(support_rows)),
            "benchmark_eligible_family_count": int(len(benchmark_families)),
            "excluded_below_support_family_count": int(len(excluded_rows)),
            "excluded_below_support_families": [
                {
                    "family_canonical": str(row.get("family_canonical", "") or ""),
                    "family_tier": str(row.get("family_tier", "") or ""),
                    "sample_count": int(row.get("sample_count", 0) or 0),
                }
                for row in excluded_rows
            ],
        },
        "support_diagnostics": floor_rows,
        "per_family_support": support_rows,
        "major_family_coverage": {
            "authority_family_count": int(len(major_set)),
            "present_major_family_count": int(len(major_present)),
            "missing_major_family_count": int(len(major_missing)),
            "present_major_families": major_present,
            "missing_major_families": major_missing,
            "present_minor_family_count": int(len(minor_present)),
            "present_minor_families": minor_present,
        },
        "major_family_authority": major_payload,
        "generic_coarse_token_policy": generic_payload,
    }


def build_family_tier_audit_rows(samples_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Build a row-level family tier audit with reasons and support diagnostics."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return []

    masks = _major_minor_generic_unresolved_masks(samples_df)
    family_canonical = _series_from(samples_df, "family_canonical")
    family_ids = _numeric_family_id_series(samples_df)
    type_slug = _series_from(samples_df, "type_slug")
    category_primary = _series_from(
        samples_df,
        "category_primary",
        generic_tokens=set(family_tier_authority.GENERIC_PRIMARY_TOKENS),
    )
    category_subtype = _series_from(samples_df, "category_subtype")
    sample_label_kind = _series_from(samples_df, "sample_label_kind")
    generic_tokens = family_tier_authority.generic_coarse_token_set()
    major_payload = family_tier_authority.major_family_authority_payload()
    generic_payload = family_tier_authority.generic_coarse_token_policy_payload()
    attrs = getattr(samples_df, "attrs", {}) if isinstance(getattr(samples_df, "attrs", None), dict) else {}
    benchmark_support_floor = _resolve_benchmark_support_floor(
        samples_df,
        attrs.get("configured_min_samples_per_family") or attrs.get("diagnostic_min_samples_per_family"),
    )

    audit_df = samples_df.copy()
    audit_df = audit_df.assign(
        family_canonical_norm=family_canonical,
        family_id_num=family_ids,
        type_slug_norm=type_slug,
        category_primary_norm=category_primary,
        category_subtype_norm=category_subtype,
        sample_label_kind_norm=sample_label_kind,
        family_target_eligible=masks["family_target_eligible"],
        type_target_eligible=masks["type_target_eligible"],
    )

    audit_df["authority_tier"] = "unresolved"
    audit_df.loc[masks["major_family"], "authority_tier"] = "major"
    audit_df.loc[masks["minor_family"], "authority_tier"] = "minor"
    audit_df.loc[masks["generic_coarse"], "authority_tier"] = "generic_or_coarse"

    audit_df["tier_reason"] = "no_safe_family_mapping"
    audit_df.loc[masks["major_family"], "tier_reason"] = "listed_in_major_family_authority"
    audit_df.loc[masks["minor_family"], "tier_reason"] = "mapped_family_not_in_major_authority"

    generic_reason = pd.Series([""] * len(audit_df), index=audit_df.index, dtype="object")
    family_generic = audit_df["family_canonical_norm"].isin(generic_tokens)
    subtype_generic = audit_df["category_subtype_norm"].isin(
        generic_tokens | set(family_tier_authority.CANONICAL_TYPE_TOKENS)
    )
    primary_generic = audit_df["category_primary_norm"].isin(
        generic_tokens | set(family_tier_authority.CANONICAL_TYPE_TOKENS)
    )
    weak_kind = audit_df["sample_label_kind_norm"].isin(set(family_tier_authority.WEAK_LABEL_KINDS))
    generic_reason.loc[family_generic] = "generic_family_token"
    generic_reason.loc[(generic_reason == "") & subtype_generic] = "generic_or_type_like_subtype"
    generic_reason.loc[(generic_reason == "") & primary_generic] = "generic_or_type_like_primary"
    generic_reason.loc[(generic_reason == "") & weak_kind] = "weak_sample_label_kind"
    audit_df.loc[masks["generic_coarse"], "tier_reason"] = generic_reason.loc[masks["generic_coarse"]]

    audit_df["audit_label"] = ""
    audit_df.loc[audit_df["authority_tier"].isin({"major", "minor"}), "audit_label"] = audit_df.loc[
        audit_df["authority_tier"].isin({"major", "minor"}), "family_canonical_norm"
    ]
    unresolved_generic_mask = audit_df["authority_tier"].isin({"generic_or_coarse", "unresolved"})
    audit_df.loc[unresolved_generic_mask, "audit_label"] = audit_df.loc[unresolved_generic_mask].apply(
        lambda row: _first_present_token(
            row.get("family_canonical_norm", ""),
            row.get("category_subtype_norm", ""),
            row.get("category_primary_norm", ""),
            row.get("type_slug_norm", ""),
            row.get("sample_label_kind_norm", ""),
        )
        or "__unresolved__",
        axis=1,
    )

    group_cols = ["authority_tier", "tier_reason", "audit_label"]
    grouped = []
    for _, group in audit_df.groupby(group_cols, dropna=False, sort=False):
        sample_count = int(len(group))
        support_flags = {f"support_ge_{floor}": bool(sample_count >= floor) for floor in SUPPORT_DIAGNOSTIC_FLOORS}
        family_id_values = pd.to_numeric(group["family_id_num"], errors="coerce").dropna()
        family_id_value = int(family_id_values.iloc[0]) if not family_id_values.empty else None
        family_slug = str(group["audit_label"].iloc[0] or "").strip().lower()
        family_canonical_value = str(group["family_canonical_norm"].replace("", pd.NA).dropna().iloc[0]).strip() if group["family_canonical_norm"].replace("", pd.NA).dropna().shape[0] else ""
        type_slug_value = str(group["type_slug_norm"].replace("", pd.NA).dropna().iloc[0]).strip() if group["type_slug_norm"].replace("", pd.NA).dropna().shape[0] else ""
        top_source_batch = ""
        if "source_batch_label" in group.columns:
            source_counts = (
                group["source_batch_label"]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace("", pd.NA)
                .dropna()
                .value_counts()
            )
            if not source_counts.empty:
                top_source_batch = str(source_counts.index[0]).strip()
        grouped.append(
            {
                "family_id": family_id_value,
                "family_slug": family_slug,
                "family_canonical": family_canonical_value,
                "type_slug": type_slug_value,
                "authority_tier": str(group["authority_tier"].iloc[0]),
                "tier_reason": str(group["tier_reason"].iloc[0]),
                "major_authority_version": str(major_payload.get("version", "") or ""),
                "major_authority_hash": str(major_payload.get("hash", "") or ""),
                "generic_policy_version": str(generic_payload.get("version", "") or ""),
                "generic_policy_hash": str(generic_payload.get("hash", "") or ""),
                "sample_count": sample_count,
                "authority_eligible": bool(group["family_target_eligible"].any()),
                "benchmark_support_floor": int(benchmark_support_floor) if benchmark_support_floor is not None else None,
                "benchmark_eligible": bool(
                    benchmark_support_floor is not None
                    and bool(group["family_target_eligible"].any())
                    and sample_count >= int(benchmark_support_floor)
                ),
                "benchmark_exclusion_reason": (
                    ""
                    if benchmark_support_floor is None
                    else (
                        ""
                        if bool(group["family_target_eligible"].any())
                        and sample_count >= int(benchmark_support_floor)
                        else (
                            f"support_below_{int(benchmark_support_floor)}"
                            if bool(group["family_target_eligible"].any())
                            else "non_family_target"
                        )
                    )
                ),
                "family_target_eligible": bool(group["family_target_eligible"].any()),
                "type_target_eligible": bool(group["type_target_eligible"].any()),
                "is_generic_or_coarse": bool(str(group["authority_tier"].iloc[0]) == "generic_or_coarse"),
                "is_unresolved": bool(str(group["authority_tier"].iloc[0]) == "unresolved"),
                "top_source_batch": top_source_batch,
                "notes": "",
                **support_flags,
            }
        )
    grouped.sort(
        key=lambda row: (
            {"major": 0, "minor": 1, "generic_or_coarse": 2, "unresolved": 3}.get(str(row.get("authority_tier", "")), 9),
            -int(row.get("sample_count", 0)),
            str(row.get("family_slug", "")),
        )
    )
    return grouped


def _surface_summary(
    surface_name: str,
    labels: pd.Series,
    *,
    authority_tier: str,
    recommended_use: str,
    min_support: int | None,
    notes: str,
) -> dict[str, Any]:
    nonempty = labels[labels.astype(str).str.strip() != ""]
    present_rows = int(len(nonempty))
    counts = nonempty.value_counts()
    effective_min_support = max(1, int(min_support or 1))
    trainable = counts[counts >= effective_min_support]
    top_label = str(counts.index[0]) if not counts.empty else ""
    top_count = int(counts.iloc[0]) if not counts.empty else 0
    top_share_pct = round((float(top_count) / float(present_rows)) * 100.0, 2) if present_rows else 0.0
    return {
        "surface_name": surface_name,
        "authority_tier": authority_tier,
        "recommended_use": recommended_use,
        "present_rows": present_rows,
        "present_pct": round((float(present_rows) / float(len(labels))) * 100.0, 2) if len(labels) else 0.0,
        "unique_classes": int(counts.shape[0]),
        "trainable_classes_at_min_support": int(trainable.shape[0]),
        "trainable_rows_at_min_support": int(trainable.sum()) if not trainable.empty else 0,
        "top_class": top_label,
        "top_class_count": top_count,
        "top_class_share_pct": top_share_pct,
        "min_support": int(effective_min_support),
        "notes": notes,
    }


def build_taxonomy_target_surface_summary(
    samples_df: pd.DataFrame,
    *,
    min_support: int | None,
) -> dict[str, Any]:
    """Summarize target/label surfaces available in the prepared cohort."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return {"row_count": 0, "targets": [], "alignment": {}, "label_strategy": {}}

    family_id = _series_from(samples_df, "family_id")
    family_canonical = _series_from(samples_df, "family_canonical")
    type_slug = _series_from(samples_df, "type_slug")
    category_primary = _series_from(
        samples_df,
        "category_primary",
        generic_tokens=set(family_tier_authority.GENERIC_PRIMARY_TOKENS),
    )
    category_subtype = _series_from(samples_df, "category_subtype")
    family_within_type = _build_family_within_type(samples_df)

    raw_primary_subtype = pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    both_mask = category_primary.ne("") & category_subtype.ne("")
    raw_primary_subtype.loc[both_mask] = (
        category_primary.loc[both_mask] + "::" + category_subtype.loc[both_mask]
    )

    targets = [
        _surface_summary(
            "family_id",
            family_id,
            authority_tier="authoritative",
            recommended_use="preferred_supervised_target",
            min_support=min_support,
            notes="Primary fine-grained supervised family target.",
        ),
        _surface_summary(
            "family_canonical",
            family_canonical,
            authority_tier="display_authority",
            recommended_use="preferred_reporting_surface",
            min_support=min_support,
            notes="Human-readable family surface paired to authoritative family_id.",
        ),
        _surface_summary(
            "type_slug",
            type_slug,
            authority_tier="authoritative",
            recommended_use="preferred_coarse_target",
            min_support=min_support,
            notes="Primary-class Android malware taxonomy target.",
        ),
        _surface_summary(
            "family_within_type",
            family_within_type,
            authority_tier="hierarchical",
            recommended_use="preferred_hierarchical_target",
            min_support=min_support,
            notes="Hierarchical target combining authoritative type and family.",
        ),
        _surface_summary(
            "category_primary",
            category_primary,
            authority_tier="auxiliary_raw",
            recommended_use="avoid_primary_claim_target",
            min_support=min_support,
            notes="Raw catalog primary-class string; useful for audits, not authoritative family supervision.",
        ),
        _surface_summary(
            "category_subtype",
            category_subtype,
            authority_tier="auxiliary_raw",
            recommended_use="auxiliary_audit_surface",
            min_support=min_support,
            notes="Raw catalog subclass string; useful for audits, not authoritative family supervision.",
        ),
        _surface_summary(
            "category_primary_subtype",
            raw_primary_subtype,
            authority_tier="auxiliary_raw",
            recommended_use="auxiliary_audit_surface",
            min_support=min_support,
            notes="Raw primary/subtype pair for subclass-shape coverage analysis.",
        ),
    ]

    present_type_mask = type_slug.ne("")
    inferred_type = pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    subtype_is_type = category_subtype.isin(set(family_tier_authority.CANONICAL_TYPE_TOKENS))
    primary_is_type = category_primary.isin(set(family_tier_authority.CANONICAL_TYPE_TOKENS))
    trojan_bridge = category_primary.eq("trojan") & subtype_is_type
    inferred_type.loc[subtype_is_type] = category_subtype.loc[subtype_is_type]
    inferred_type.loc[(inferred_type == "") & primary_is_type] = category_primary.loc[
        (inferred_type == "") & primary_is_type
    ]
    inferred_type.loc[(inferred_type == "") & trojan_bridge] = category_subtype.loc[
        (inferred_type == "") & trojan_bridge
    ]

    subtype_match = present_type_mask & category_subtype.ne("") & category_subtype.eq(type_slug)
    primary_match = present_type_mask & category_primary.ne("") & category_primary.eq(type_slug)
    inferred_match = present_type_mask & inferred_type.ne("") & inferred_type.eq(type_slug)

    alignment = {
        "rows_with_authoritative_type": int(present_type_mask.sum()),
        "rows_with_raw_primary": int(category_primary.ne("").sum()),
        "rows_with_raw_subtype": int(category_subtype.ne("").sum()),
        "rows_with_subtype_exact_type_match": int(subtype_match.sum()),
        "rows_with_primary_exact_type_match": int(primary_match.sum()),
        "rows_with_inferred_type_match": int(inferred_match.sum()),
        "subtype_exact_type_match_pct": round(
            (float(subtype_match.sum()) / float(present_type_mask.sum())) * 100.0,
            2,
        )
        if int(present_type_mask.sum()) > 0
        else 0.0,
        "primary_exact_type_match_pct": round(
            (float(primary_match.sum()) / float(present_type_mask.sum())) * 100.0,
            2,
        )
        if int(present_type_mask.sum()) > 0
        else 0.0,
        "inferred_type_match_pct": round(
            (float(inferred_match.sum()) / float(present_type_mask.sum())) * 100.0,
            2,
        )
        if int(present_type_mask.sum()) > 0
        else 0.0,
    }

    subtype_match_pct = float(alignment.get("subtype_exact_type_match_pct", 0.0) or 0.0)
    primary_match_pct = float(alignment.get("primary_exact_type_match_pct", 0.0) or 0.0)
    inferred_match_pct = float(alignment.get("inferred_type_match_pct", 0.0) or 0.0)
    if subtype_match_pct >= (primary_match_pct + 20.0):
        alignment_interpretation = (
            "Raw subtype aligns materially better than raw primary; prefer authoritative type_slug for type truth "
            "and keep category_subtype as an auxiliary audit surface."
        )
    elif primary_match_pct >= (subtype_match_pct + 20.0):
        alignment_interpretation = (
            "Raw primary currently aligns better than raw subtype, but authoritative type_slug should still anchor "
            "coarse-class claims."
        )
    elif inferred_match_pct > max(subtype_match_pct, primary_match_pct):
        alignment_interpretation = (
            "Raw labels are mixed; inferred raw type improves alignment, but authoritative type_slug remains the "
            "publication-safe coarse target."
        )
    else:
        alignment_interpretation = (
            "Authoritative type_slug remains the main coarse target; raw primary/subtype surfaces are better used "
            "for audits than for primary family/type claims."
        )

    major_authority = family_tier_authority.major_family_authority_payload()
    generic_policy = family_tier_authority.generic_coarse_token_policy_payload()
    label_strategy = {
        "preferred_family_target": "family_id",
        "preferred_family_reporting_surface": "family_canonical",
        "preferred_type_target": "type_slug",
        "preferred_hierarchical_target": "family_within_type",
        "auxiliary_audit_surfaces": ["category_subtype", "category_primary_subtype"],
        "avoid_for_primary_claims": ["category_primary"],
        "major_family_target_scope": "curated_major_family_authority",
        "major_family_authority_version": major_authority.get("version"),
        "major_family_authority_hash": major_authority.get("hash"),
        "generic_coarse_token_policy_version": generic_policy.get("version"),
        "generic_coarse_token_policy_hash": generic_policy.get("hash"),
        "alignment_interpretation": alignment_interpretation,
    }

    benchmark_support_floor = _resolve_benchmark_support_floor(samples_df, min_support)
    tier_summary = _build_family_tier_summary(
        samples_df,
        benchmark_support_floor=benchmark_support_floor,
    )

    return {
        "row_count": int(len(samples_df)),
        "targets": targets,
        "alignment": alignment,
        "label_strategy": label_strategy,
        **tier_summary,
    }


def export_taxonomy_target_surface_reports(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame,
    min_support: int,
) -> list[str]:
    """Write run-scoped taxonomy target-surface artifacts and return their paths."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    summary = build_taxonomy_target_surface_summary(samples_df, min_support=min_support)
    family_tier_audit_rows = build_family_tier_audit_rows(samples_df)
    targets_df = pd.DataFrame(summary.get("targets", []))
    tier_audit_df = pd.DataFrame(family_tier_audit_rows)

    csv_path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.csv"
    json_path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json"
    md_path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.md"
    tier_csv_path = diagnostics_dir / f"family_tier_audit_{run_id}.csv"
    tier_json_path = diagnostics_dir / f"family_tier_audit_{run_id}.json"
    tier_md_path = diagnostics_dir / f"family_tier_audit_{run_id}.md"

    csv_text = targets_df.to_csv(index=False)
    csv_path.write_text(csv_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=csv_path.name,
        csv_text=csv_text,
        global_latest_name="taxonomy_target_surfaces.latest.csv",
    )

    json_payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_payload, encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        payload=summary,
        global_latest_name="taxonomy_target_surfaces.latest.json",
    )

    tier_csv_text = tier_audit_df.to_csv(index=False)
    tier_csv_path.write_text(tier_csv_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=tier_csv_path.name,
        csv_text=tier_csv_text,
        global_latest_name="family_tier_audit.latest.csv",
    )

    tier_json_payload = json.dumps(family_tier_audit_rows, indent=2, sort_keys=True) + "\n"
    tier_json_path.write_text(tier_json_payload, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=tier_json_path.name,
        text=tier_json_payload,
        global_latest_name="family_tier_audit.latest.json",
    )

    lines = [
        "# Taxonomy Target Surfaces",
        "",
        f"Run ID: `{run_id}`",
        f"Cohort rows: **{int(summary.get('row_count', 0))}**",
        "",
        "## Target surfaces",
        "",
        "| surface | authority | recommended use | present rows | classes | trainable classes | trainable rows | top class | top share |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary.get("targets", []):
        lines.append(
            f"| `{row.get('surface_name', '')}` | `{row.get('authority_tier', '')}` | "
            f"`{row.get('recommended_use', '')}` | "
            f"{int(row.get('present_rows', 0))} ({float(row.get('present_pct', 0.0)):.2f}%) | "
            f"{int(row.get('unique_classes', 0))} | "
            f"{int(row.get('trainable_classes_at_min_support', 0))} | "
            f"{int(row.get('trainable_rows_at_min_support', 0))} | "
            f"`{row.get('top_class', '')}` | {float(row.get('top_class_share_pct', 0.0)):.2f}% |"
        )
    tier_counts = summary.get("tier_counts", {}) if isinstance(summary.get("tier_counts"), dict) else {}
    benchmark_policy = (
        summary.get("benchmark_support_policy")
        if isinstance(summary.get("benchmark_support_policy"), dict)
        else {}
    )
    benchmark_floor = benchmark_policy.get("benchmark_min_support")
    support_excluded_family_text = ", ".join(
        f"`{str(row.get('family_canonical', '') or '')}` ({int(row.get('sample_count', 0) or 0)})"
        for row in benchmark_policy.get("excluded_below_support_families", [])
        if isinstance(row, dict)
    ) or "none"
    major_authority = (
        summary.get("major_family_authority")
        if isinstance(summary.get("major_family_authority"), dict)
        else {}
    )
    major_coverage = (
        summary.get("major_family_coverage")
        if isinstance(summary.get("major_family_coverage"), dict)
        else {}
    )
    generic_policy = (
        summary.get("generic_coarse_token_policy")
        if isinstance(summary.get("generic_coarse_token_policy"), dict)
        else {}
    )
    lines.extend(
        [
            "",
            "## Family Tiers",
            "",
            f"- total Android malware samples: **{int(tier_counts.get('total_android_malware_samples', 0))}**",
            f"- mapped family samples: **{int(tier_counts.get('mapped_family_samples', 0))}**",
            f"- major-family samples: **{int(tier_counts.get('major_family_samples', 0))}**",
            f"- minor-family samples: **{int(tier_counts.get('minor_family_samples', 0))}**",
            f"- generic/coarse-label samples: **{int(tier_counts.get('generic_coarse_label_samples', 0))}**",
            f"- unresolved samples: **{int(tier_counts.get('unresolved_samples', 0))}**",
            f"- type-target-eligible samples: **{int(tier_counts.get('type_target_eligible_samples', 0))}**",
            f"- family-target-eligible samples: **{int(tier_counts.get('family_target_eligible_samples', 0))}**",
            f"- authority-eligible family-target samples: **{int(tier_counts.get('authority_eligible_samples', 0))}**",
            f"- benchmark-eligible family-target samples: **{int(tier_counts.get('benchmark_eligible_samples', 0))}**",
            f"- excluded due to support <{benchmark_floor if benchmark_floor not in (None, '') else 'n/a'}: **{int(tier_counts.get('excluded_below_benchmark_support_samples', 0))}**",
            f"- excluded due to generic/coarse or unresolved non-family targets: **{int(tier_counts.get('excluded_non_family_target_samples', 0))}**",
            "",
            f"- major-family authority version: `{major_authority.get('version', '')}`",
            f"- major-family authority hash: `{major_authority.get('hash', '')}`",
            f"- benchmark support mode: `{benchmark_policy.get('support_floor_mode', '') or 'not applied'}`",
            f"- benchmark minimum family support: `{benchmark_policy.get('benchmark_min_support')}`",
            f"- benchmark-eligible family count: **{int(benchmark_policy.get('benchmark_eligible_family_count', 0))}**",
            f"- support-<{benchmark_floor if benchmark_floor not in (None, '') else 'n/a'} excluded family count: **{int(benchmark_policy.get('excluded_below_support_family_count', 0))}**",
            f"- present major-family count: **{int(major_coverage.get('present_major_family_count', 0))}** / "
            f"**{int(major_coverage.get('authority_family_count', 0))}**",
            f"- missing major families: {', '.join(f'`{item}`' for item in major_coverage.get('missing_major_families', [])) or 'none'}",
            f"- support-<{benchmark_floor if benchmark_floor not in (None, '') else 'n/a'} excluded families: {support_excluded_family_text}",
            f"- generic/coarse token policy version: `{generic_policy.get('version', '')}`",
            f"- generic/coarse token policy hash: `{generic_policy.get('hash', '')}`",
            "- generic/coarse rows are retained broad-corpus residue (generic malware tokens, type-like raw labels, or weak labels), not valid `family_id` targets.",
            "- unresolved rows remain only when no safe family mapping and no generic/coarse policy bucket can be assigned.",
            "- benchmark support eligibility affects only supervised family benchmark training/evaluation, not broad corpus-health, taxonomy, or permission-pattern diagnostics.",
            "",
            "## Support Diagnostics",
            "",
            "| support floor | major families | major samples | minor families | minor samples | family-target families | family-target samples | type-target classes |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary.get("support_diagnostics", []):
        lines.append(
            f"| {int(row.get('support_floor', 0))} | {int(row.get('major_family_count', 0))} | "
            f"{int(row.get('major_sample_count', 0))} | {int(row.get('minor_family_count', 0))} | "
            f"{int(row.get('minor_sample_count', 0))} | {int(row.get('family_target_family_count', 0))} | "
            f"{int(row.get('family_target_sample_count', 0))} | {int(row.get('type_target_class_count', 0))} |"
        )
    alignment = summary.get("alignment", {})
    lines.extend(
        [
            "",
            "## Raw label / taxonomy alignment",
            "",
            f"- rows with authoritative `type_slug`: {int(alignment.get('rows_with_authoritative_type', 0))}",
            f"- rows with raw `category_primary`: {int(alignment.get('rows_with_raw_primary', 0))}",
            f"- rows with raw `category_subtype`: {int(alignment.get('rows_with_raw_subtype', 0))}",
            f"- raw subtype exactly matches authoritative type: {float(alignment.get('subtype_exact_type_match_pct', 0.0)):.2f}%",
            f"- raw primary exactly matches authoritative type: {float(alignment.get('primary_exact_type_match_pct', 0.0)):.2f}%",
            f"- raw primary/subtype can be inferred to authoritative type: {float(alignment.get('inferred_type_match_pct', 0.0)):.2f}%",
            "",
            "## Recommended label strategy",
            "",
            f"- preferred family supervision target: `{summary.get('label_strategy', {}).get('preferred_family_target', '')}`",
            f"- preferred family reporting surface: `{summary.get('label_strategy', {}).get('preferred_family_reporting_surface', '')}`",
            f"- preferred coarse type target: `{summary.get('label_strategy', {}).get('preferred_type_target', '')}`",
            f"- preferred hierarchical target: `{summary.get('label_strategy', {}).get('preferred_hierarchical_target', '')}`",
            f"- auxiliary audit surfaces: {', '.join(f'`{item}`' for item in summary.get('label_strategy', {}).get('auxiliary_audit_surfaces', [])) or 'none'}",
            f"- avoid for primary claims: {', '.join(f'`{item}`' for item in summary.get('label_strategy', {}).get('avoid_for_primary_claims', [])) or 'none'}",
            f"- alignment interpretation: {summary.get('label_strategy', {}).get('alignment_interpretation', '')}",
            "",
            "## Guidance",
            "",
            "- Use `family_id` / `family_canonical` for fine-grained family supervision.",
            "- Use authoritative `type_slug` for primary-class reporting and auxiliary type tasks.",
            "- Treat raw `category_primary` / `category_subtype` as auxiliary audit surfaces, not stronger than taxonomy.",
        ]
    )
    md_text = "\n".join(lines).strip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="taxonomy_target_surfaces.latest.md",
    )

    tier_lines = [
        "# Family Tier Audit",
        "",
        f"Run ID: `{run_id}`",
        f"Rows: **{len(family_tier_audit_rows)}**",
        "",
        "| tier | reason | family | type | samples | benchmark eligible | benchmark exclusion | family-target | type-target | >=20 | >=10 | >=5 | >=1 | source batch |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in family_tier_audit_rows:
        tier_lines.append(
            f"| `{row.get('authority_tier', '')}` | `{row.get('tier_reason', '')}` | "
            f"`{row.get('family_slug', '')}` | `{row.get('type_slug', '')}` | "
            f"{int(row.get('sample_count', 0))} | "
            f"{'yes' if row.get('benchmark_eligible') else 'no'} | "
            f"`{row.get('benchmark_exclusion_reason', '')}` | "
            f"{'yes' if row.get('family_target_eligible') else 'no'} | "
            f"{'yes' if row.get('type_target_eligible') else 'no'} | "
            f"{'yes' if row.get('support_ge_20') else 'no'} | "
            f"{'yes' if row.get('support_ge_10') else 'no'} | "
            f"{'yes' if row.get('support_ge_5') else 'no'} | "
            f"{'yes' if row.get('support_ge_1') else 'no'} | "
            f"`{row.get('top_source_batch', '')}` |"
        )
    tier_md_text = "\n".join(tier_lines).strip() + "\n"
    tier_md_path.write_text(tier_md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=tier_md_path.name,
        text=tier_md_text,
        global_latest_name="family_tier_audit.latest.md",
    )
    return [
        str(json_path),
        str(csv_path),
        str(md_path),
        str(tier_json_path),
        str(tier_csv_path),
        str(tier_md_path),
    ]
