"""Trace where ``unknown_feature_builder_drop`` samples leave the feature pipeline.

Read-only: uses the same merge/extract logic as training (``merge_vendor_features``,
``generate_binary_detection_matrix``) but does not change model behavior.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from config import app_config
from obsidiandroid.common import output_hygiene as oh

STAGE_SLUGS: tuple[str, ...] = (
    "after_sample_prep",
    "av_binary_matrix",
    "vendor_parser_output",
    "top_k_vendor_field_merge",
    "permission_feature_frame",
    "metadata_feature_frame",
    "enrichment_frame",
    "final_feature_matrix",
)

# Column -> first stage where a False value is reported as the drop point.
TRACE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("in_labels", "after_sample_prep"),
    ("in_av_matrix", "av_binary_matrix"),
    ("in_parsed_vendor_any", "vendor_parser_output"),
    ("in_vendor_gate_merge", "top_k_vendor_field_merge"),
    ("in_permission_row", "permission_feature_frame"),
    ("in_metadata_row", "metadata_feature_frame"),
    ("in_enrichment_frame", "enrichment_frame"),
    ("in_final_feature_matrix", "final_feature_matrix"),
)


def resolve_diagnostics_dir(run_root: Path | None, diagnostics_dir: Path | None) -> Path:
    if diagnostics_dir is not None:
        return Path(diagnostics_dir)
    if run_root is not None:
        return Path(run_root) / "diagnostics"
    raise ValueError("Provide run_root or diagnostics_dir")


def load_selected_vendors_from_gate_csv(path: Path) -> list[str]:
    """Return vendor names with ``selected_flag == 1`` from vendor gate debug export."""
    df = pd.read_csv(path)
    if "vendor" not in df.columns or "selected_flag" not in df.columns:
        raise ValueError(f"Expected vendor + selected_flag in {path}")
    sel = df.loc[pd.to_numeric(df["selected_flag"], errors="coerce").fillna(0).astype(int) == 1]
    return [str(v).strip() for v in sel["vendor"].tolist() if str(v).strip()]


def load_cohort_membership(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_gap_unknown_builder_rows(
    alignment_gap_csv: Path,
) -> pd.DataFrame:
    df = pd.read_csv(alignment_gap_csv)
    col = "likely_missing_reason"
    if col not in df.columns:
        raise ValueError(f"Expected column {col} in {alignment_gap_csv}")
    return df[df[col] == "unknown_feature_builder_drop"].copy()


def _sample_ids_in_any_parsed_vendor(parsed_data: dict[str, pd.DataFrame]) -> set[int]:
    acc: set[int] = set()
    for frame in parsed_data.values():
        if not isinstance(frame, pd.DataFrame) or frame.empty or "sample_id" not in frame.columns:
            continue
        s = pd.to_numeric(frame["sample_id"], errors="coerce").dropna()
        acc.update(int(x) for x in s.tolist())
    return acc


def _sample_ids_in_topk_merge(
    parsed_data: dict[str, pd.DataFrame],
    selected_vendors: list[str],
    fields: list[str],
) -> set[int]:
    from ml_classification.vectorization.feature_vendor_extractor import (
        extract_vendor_fields,
        merge_vendor_features,
    )

    frames = extract_vendor_fields(parsed_data, selected_vendors, fields)
    if not frames:
        return set()
    merged = merge_vendor_features(frames)
    if merged.empty or "sample_id" not in merged.columns:
        return set()
    s = pd.to_numeric(merged["sample_id"], errors="coerce").dropna()
    return {int(x) for x in s.tolist()}


def infer_first_missing_stage(row: pd.Series) -> str:
    """First pipeline boundary where the trace row is False (see ``TRACE_COLUMNS``)."""
    for col, slug in TRACE_COLUMNS:
        if col not in row.index:
            continue
        val = row[col]
        if isinstance(val, str):
            if val.lower() in {"false", "0", ""}:
                return slug
        elif val == 0 or not bool(val):
            return slug
    return "complete"


def _likely_cause(slug: str) -> str:
    return {
        "after_sample_prep": "Sample id not present in cohort_membership export for this run.",
        "av_binary_matrix": "Dropped during AV wide/melt/pivot: no non-null engine verdict tokens "
        "long enough to survive melt (or missing wide verdict row).",
        "vendor_parser_output": "Parser produced no rows for this sample for any vendor "
        "(empty / skipped vendor outputs).",
        "top_k_vendor_field_merge": "Sample absent from outer-merge of top-k vendor parsed frames "
        "only: appears in no selected vendor's parsed dataframe (row authority for encoded matrix).",
        "permission_feature_frame": "No permission feature row (unexpected if cohort row exists).",
        "metadata_feature_frame": "No metadata feature row (unexpected if cohort row exists).",
        "enrichment_frame": "Missing from enriched_matrix lineage (should match AV binary rows).",
        "final_feature_matrix": "Not in encoded vendor matrix index before alignment "
        "(matches top_k merge unless encoding dropped rows).",
        "complete": "All traced stages True — investigate alignment / label join.",
    }.get(slug, slug)


@dataclass
class TraceSets:
    cohort_ids: set[int]
    av_matrix_ids: set[int]
    parsed_any_ids: set[int]
    topk_merge_ids: set[int]
    perm_row_ids: set[int]
    meta_row_ids: set[int]


def _build_samples_df_for_parser(gap_df: pd.DataFrame, cohort_df: pd.DataFrame) -> pd.DataFrame:
    """Minimal ``samples_df`` for ``parse_vendor_classifications``."""
    ids = gap_df[["sample_id"]].drop_duplicates()
    merged = ids.merge(cohort_df, on="sample_id", how="left")
    if "family_canonical" in merged.columns:
        merged["family_canonical"] = merged["family_canonical"].fillna("")
    else:
        merged["family_canonical"] = ""
    if merged["family_canonical"].astype(str).str.strip().eq("").any() and "family_label" in gap_df.columns:
        labels = gap_df[["sample_id", "family_label"]].drop_duplicates(subset=["sample_id"])
        merged = merged.merge(labels, on="sample_id", how="left", suffixes=("", "_gap"))
        merged["family_canonical"] = merged["family_canonical"].where(
            merged["family_canonical"].astype(str).str.strip() != "",
            merged.get("family_label", ""),
        )
    merged["family_canonical"] = merged["family_canonical"].fillna("unknown").astype(str).str.strip()
    merged.loc[merged["family_canonical"] == "", "family_canonical"] = "unknown"
    return merged


def compute_trace_sets(
    gap_df: pd.DataFrame,
    cohort_df: pd.DataFrame,
    selected_vendors: list[str],
    *,
    parse_vendor_classifications: Callable[..., Any],
    generate_binary_detection_matrix: Callable[..., pd.DataFrame],
    build_permission_feature_frame: Callable[..., pd.DataFrame],
    build_metadata_feature_frame: Callable[..., pd.DataFrame],
    parser_fields: Optional[list[str]] = None,
) -> TraceSets:
    """Fetch DB-backed sets for each pipeline boundary."""
    fields = parser_fields or ["Parsed Family", "Threat Class", "Malware Type"]
    samples_parser = _build_samples_df_for_parser(gap_df, cohort_df)

    bin_df = generate_binary_detection_matrix(samples_parser, verbose=False)
    av_ids: set[int] = set()
    if isinstance(bin_df, pd.DataFrame) and not bin_df.empty and "sample_id" in bin_df.columns:
        av_ids = {int(x) for x in pd.to_numeric(bin_df["sample_id"], errors="coerce").dropna().tolist()}

    parsed_data, _, _, _ = parse_vendor_classifications(samples_parser, engine_metadata=None, verbose=False)
    if not isinstance(parsed_data, dict):
        parsed_data = {}

    parsed_any = _sample_ids_in_any_parsed_vendor(parsed_data)
    topk_merge = _sample_ids_in_topk_merge(parsed_data, selected_vendors, fields)

    perm_df = build_permission_feature_frame(samples_parser)
    perm_ids: set[int] = set()
    if isinstance(perm_df, pd.DataFrame) and not perm_df.empty and "sample_id" in perm_df.columns:
        perm_ids = {int(x) for x in pd.to_numeric(perm_df["sample_id"], errors="coerce").dropna().tolist()}

    meta_df = build_metadata_feature_frame(samples_parser)
    meta_ids: set[int] = set()
    if isinstance(meta_df, pd.DataFrame) and not meta_df.empty and "sample_id" in meta_df.columns:
        meta_ids = {int(x) for x in pd.to_numeric(meta_df["sample_id"], errors="coerce").dropna().tolist()}

    cohort_ids = {
        int(x)
        for x in pd.to_numeric(gap_df["sample_id"], errors="coerce").dropna().astype(int).tolist()
    }
    return TraceSets(
        cohort_ids=cohort_ids,
        av_matrix_ids=av_ids,
        parsed_any_ids=parsed_any,
        topk_merge_ids=topk_merge,
        perm_row_ids=perm_ids,
        meta_row_ids=meta_ids,
    )


def build_trace_table(
    gap_df: pd.DataFrame,
    cohort_df: pd.DataFrame,
    trace: TraceSets,
    *,
    trace_degraded: bool = False,
) -> pd.DataFrame:
    """Per-sample boolean trace + first_missing_stage + likely_cause."""
    cohort_set = {int(x) for x in pd.to_numeric(cohort_df["sample_id"], errors="coerce").dropna().tolist()}

    rows: list[dict[str, Any]] = []
    for _, r in gap_df.iterrows():
        sid = int(pd.to_numeric(r["sample_id"], errors="coerce"))
        in_labels = sid in cohort_set
        in_av = sid in trace.av_matrix_ids
        in_parsed_any = sid in trace.parsed_any_ids
        in_gate_merge = sid in trace.topk_merge_ids
        in_perm_row = sid in trace.perm_row_ids
        in_meta_row = sid in trace.meta_row_ids
        in_enrich = in_av
        in_final = in_gate_merge

        trace_series = pd.Series(
            {
                "in_labels": in_labels,
                "in_av_matrix": in_av,
                "in_parsed_vendor_any": in_parsed_any,
                "in_vendor_gate_merge": in_gate_merge,
                "in_permission_row": in_perm_row,
                "in_metadata_row": in_meta_row,
                "in_enrichment_frame": in_enrich,
                "in_final_feature_matrix": in_final,
            }
        )
        first = infer_first_missing_stage(trace_series)
        cause = (
            "trace_degraded: re-run with primary + PI DB access to populate stage membership "
            f"(preliminary first_missing_stage={first})."
            if trace_degraded
            else _likely_cause(first)
        )
        rec = {
            "sample_id": sid,
            "sha256": r.get("sha256", ""),
            "family_label": r.get("family_label", ""),
            "classification_primary": r.get("classification_primary", ""),
            "in_labels": bool(in_labels),
            "in_av_matrix": bool(in_av),
            "in_parsed_vendor_data": bool(in_parsed_any),
            "in_vendor_gate_table": bool(in_gate_merge),
            "in_permission_features": bool(in_perm_row),
            "in_metadata_features": bool(in_meta_row),
            "in_enrichment_frame": bool(in_enrich),
            "in_final_feature_matrix": bool(in_final),
            "has_pi_permissions": bool(int(r.get("has_pi_permissions", 0) or 0)),
            "first_missing_stage": first,
            "likely_cause": cause,
        }
        rows.append(rec)

    return pd.DataFrame(rows)


def build_summary(
    trace_df: pd.DataFrame,
    trace_sets: TraceSets,
    *,
    trace_degraded: bool = False,
    trace_degraded_reason: str | None = None,
    aligned_export_sample_count: int | None = None,
    feature_build_coverage: dict[str, Any] | None = None,
    gap_sample_count: int = 0,
) -> dict[str, Any]:
    stage_counts = Counter(trace_df["first_missing_stage"].tolist())
    dominant = stage_counts.most_common(1)[0] if stage_counts else ("none", 0)
    notes = [
        "in_vendor_gate_table reflects membership in merge_vendor_features(extract_vendor_fields("
        "top_k)) — same row universe as the encoded AV-vendor-string matrix before extras join.",
        "_merge_extra_features left-aligns extras on explicit sample_id (column or index): cohort "
        "samples missing from encoded rows never appear in the final matrix.",
        "in_enrichment_frame is approximated as in_av_matrix (enriched_matrix preserves binary rows).",
    ]
    if trace_degraded:
        notes.insert(
            0,
            "TRACE DEGRADED: AV/parser/permission DB queries failed or returned empty — "
            "first_missing_stage defaults to early failures and is not authoritative. "
            "Re-run this diagnostic with primary + Permission Intel DB access.",
        )
    coverage_consistent: bool | None = None
    if feature_build_coverage is not None and gap_sample_count > 0:
        exported_missing = int(
            feature_build_coverage.get("cohort_rows_missing_from_feature_matrix", -1)
        )
        coverage_consistent = exported_missing == gap_sample_count
        notes.append(
            "feature_build_coverage.latest.json present: "
            f"exported cohort_missing_from_matrix={exported_missing}, "
            f"unknown_feature_builder_drop rows in this trace={gap_sample_count}, "
            f"counts_match={coverage_consistent}."
        )
    summary: dict[str, Any] = {
        "dominant_first_missing_stage": dominant[0],
        "dominant_count": int(dominant[1]),
        "first_missing_stage_counts": dict(stage_counts),
        "trace_set_sizes": {
            "gap_samples": int(len(trace_df)),
            "cohort_ids_in_gap": len(trace_sets.cohort_ids),
            "av_binary_rows": len(trace_sets.av_matrix_ids),
            "parsed_any_vendor": len(trace_sets.parsed_any_ids),
            "top_k_vendor_merge": len(trace_sets.topk_merge_ids),
            "permission_rows": len(trace_sets.perm_row_ids),
            "metadata_rows": len(trace_sets.meta_row_ids),
        },
        "notes": notes,
        "trace_degraded": trace_degraded,
        "trace_degraded_reason": trace_degraded_reason,
        "aligned_export_sample_count": aligned_export_sample_count,
        "feature_build_coverage_export": feature_build_coverage,
        "gap_vs_exported_missing_consistent": coverage_consistent,
        "smallest_safe_fix_hint": (
            "If dominant stage is top_k_vendor_field_merge (with healthy DB trace): build encoded "
            "features on the validated cohort sample_id index (reindex / left-join vendor merges, "
            "fill zeros, add missing-source flags). "
            "If dominant stage is av_binary_matrix, inspect melt/pivot drops (all-null engine cells). "
            "If trace_degraded is true, fix DB connectivity first, then re-run."
        ),
    }
    return summary


def write_feature_builder_drop_artifacts(
    trace_df: pd.DataFrame,
    summary: dict[str, Any],
    out_dir: Path,
) -> tuple[Path, Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_p = out_dir / "feature_builder_drop_trace.csv"
    json_p = out_dir / "feature_builder_drop_summary.json"
    md_p = out_dir / "feature_builder_drop_summary.md"
    trace_df.to_csv(csv_p, index=False)
    json_p.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    dom = summary.get("dominant_first_missing_stage", "")
    dc = summary.get("dominant_count", 0)
    degraded = summary.get("trace_degraded", False)
    ac = summary.get("aligned_export_sample_count")
    lines = [
        "# Feature builder drop trace",
        "",
        f"Dominant **first_missing_stage**: `{dom}` ({dc} rows).",
        "",
        f"**Trace degraded (DB)**: `{degraded}`.",
        f"**Aligned feature export unique sample_id count** (if present): `{ac}`.",
        "",
        "## Stage counts",
        "",
        "```text",
        json.dumps(summary.get("first_missing_stage_counts", {}), indent=2),
        "```",
        "",
        "## Set sizes (pipeline boundaries)",
        "",
        "```text",
        json.dumps(summary.get("trace_set_sizes", {}), indent=2),
        "```",
        "",
        "## Notes",
        "",
        "\n".join(f"- {n}" for n in summary.get("notes", [])),
        "",
        "## Smallest safe fix (directional)",
        "",
        str(summary.get("smallest_safe_fix_hint", "")),
        "",
    ]
    md_p.write_text("\n".join(lines), encoding="utf-8")
    return csv_p, json_p, md_p


def load_feature_build_coverage_summary(diagnostics_dir: Path) -> dict[str, Any] | None:
    """Load ``feature_build_coverage.latest.json`` from a run diagnostics directory."""
    path = Path(diagnostics_dir) / "feature_build_coverage.latest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _aligned_export_sample_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        af = pd.read_csv(path, usecols=["sample_id"])
        return int(af["sample_id"].nunique())
    except Exception:
        return None


def run_feature_builder_drop_trace(
    *,
    run_root: Path | None = None,
    diagnostics_dir: Path | None = None,
    alignment_gap_csv: Path | None = None,
    cohort_csv: Path | None = None,
    vendor_gate_csv: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """End-to-end trace for ``unknown_feature_builder_drop`` rows."""
    diag = resolve_diagnostics_dir(run_root, diagnostics_dir)
    gap_path = alignment_gap_csv or (diag / "alignment_gap_diagnostics.csv")
    cohort_path = cohort_csv or (diag / "cohort_membership.csv")
    gate_path = vendor_gate_csv or (diag / "vendor_gate_debug.latest.csv")

    gap_df = load_gap_unknown_builder_rows(gap_path)
    cohort_df = load_cohort_membership(cohort_path)
    vendors = load_selected_vendors_from_gate_csv(gate_path)

    rid = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "")
    aligned_path = oh.resolve_aligned_features_cache_path(diag, rid)
    aligned_count = _aligned_export_sample_count(aligned_path) if aligned_path.is_file() else None
    coverage_snap = load_feature_build_coverage_summary(diag)

    from analysis.evaluation import vendor_classification_parser as vcp
    from analysis.matrix import av_binary_matrix_builder as avb
    from analysis.orchestration import permission_features as pf
    from analysis.pipeline import sample_preparation as sp

    trace_sets = compute_trace_sets(
        gap_df,
        cohort_df,
        vendors,
        parse_vendor_classifications=vcp.parse_vendor_classifications,
        generate_binary_detection_matrix=avb.generate_binary_detection_matrix,
        build_permission_feature_frame=pf.build_permission_feature_frame,
        build_metadata_feature_frame=sp.build_metadata_feature_frame,
    )

    trace_degraded = bool(len(trace_sets.av_matrix_ids) == 0 and not gap_df.empty)
    degraded_reason = None
    if trace_degraded:
        degraded_reason = (
            "Binary AV matrix query returned no rows for gap cohort — typically DB auth failure, "
            "empty verdict fetch, or environment mismatch."
        )

    trace_df = build_trace_table(gap_df, cohort_df, trace_sets, trace_degraded=trace_degraded)
    summary = build_summary(
        trace_df,
        trace_sets,
        trace_degraded=trace_degraded,
        trace_degraded_reason=degraded_reason,
        aligned_export_sample_count=aligned_count,
        feature_build_coverage=coverage_snap,
        gap_sample_count=int(len(gap_df)),
    )
    write_feature_builder_drop_artifacts(trace_df, summary, diag)
    return trace_df, summary


__all__ = [
    "STAGE_SLUGS",
    "build_summary",
    "build_trace_table",
    "compute_trace_sets",
    "infer_first_missing_stage",
    "load_feature_build_coverage_summary",
    "load_selected_vendors_from_gate_csv",
    "resolve_diagnostics_dir",
    "run_feature_builder_drop_trace",
    "write_feature_builder_drop_artifacts",
]
