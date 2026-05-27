"""Cohort target-surface summaries for family/type/taxonomy supervision tuning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh

_EMPTY_TOKENS = {"", "unknown", "none", "null", "nan", "n/a"}
_GENERIC_PRIMARY_TOKENS = _EMPTY_TOKENS | {"malware"}
_CANONICAL_TYPE_TOKENS = {
    "adware",
    "banker",
    "dropper",
    "rat",
    "sms-trojan",
    "spyware",
    "stealer",
}


def _clean_token(value: Any, *, generic_tokens: set[str] | None = None) -> str:
    token = str(value or "").strip().lower()
    blocked = generic_tokens if generic_tokens is not None else _EMPTY_TOKENS
    if token in blocked:
        return ""
    return token


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


def _surface_summary(
    surface_name: str,
    labels: pd.Series,
    *,
    authority_tier: str,
    recommended_use: str,
    min_support: int,
    notes: str,
) -> dict[str, Any]:
    nonempty = labels[labels.astype(str).str.strip() != ""]
    present_rows = int(len(nonempty))
    counts = nonempty.value_counts()
    trainable = counts[counts >= max(1, int(min_support))]
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
        "min_support": int(min_support),
        "notes": notes,
    }


def build_taxonomy_target_surface_summary(
    samples_df: pd.DataFrame,
    *,
    min_support: int,
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
        generic_tokens=_GENERIC_PRIMARY_TOKENS,
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
    subtype_is_type = category_subtype.isin(_CANONICAL_TYPE_TOKENS)
    primary_is_type = category_primary.isin(_CANONICAL_TYPE_TOKENS)
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

    label_strategy = {
        "preferred_family_target": "family_id",
        "preferred_family_reporting_surface": "family_canonical",
        "preferred_type_target": "type_slug",
        "preferred_hierarchical_target": "family_within_type",
        "auxiliary_audit_surfaces": ["category_subtype", "category_primary_subtype"],
        "avoid_for_primary_claims": ["category_primary"],
        "alignment_interpretation": alignment_interpretation,
    }

    return {
        "row_count": int(len(samples_df)),
        "targets": targets,
        "alignment": alignment,
        "label_strategy": label_strategy,
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
    targets_df = pd.DataFrame(summary.get("targets", []))

    csv_path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.csv"
    json_path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json"
    md_path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.md"

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
    return [str(json_path), str(csv_path), str(md_path)]
