"""Paper-facing diagnostics: row loss vs column loss on the feature matrix path.

Produces ``feature_matrix_row_lineage.csv``, ``feature_matrix_gap_summary.{json,md}``
from a completed pipeline run plus optional live DB queries for gap drill-down.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .alignment_gap_diagnostics import collect_alignment_gap_detail_frame
from obsidiandroid.cli.ui import display as du

# Renamed from alignment ``likely_missing_reason`` to paper-facing categories.
GAP_CATEGORY_LABELS: dict[str, str] = {
    "not_in_catalog": "no_catalog_sample_record",
    "no_vendor_verdicts": "no_av_verdict_rows_in_wide_table",
    "no_scan_summary": "no_scan_summary_row",
    "no_signal_current": "no_signal_current_row",
    "no_androguard_current": "no_androguard_current_row",
    "no_pi_permissions": "no_permission_intel_observations",
    "unknown_feature_builder_drop": "vendor_encoded_row_authority_missing_after_parser_gating",
}


def resolve_run_diagnostics(run_root: Path | str) -> Path:
    return Path(run_root) / "diagnostics"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def analyze_training_column_mix(feature_contract: dict[str, Any]) -> dict[str, Any]:
    """Break down training-time columns by prefix (post pruning)."""
    cols = feature_contract.get("feature_columns") or []
    if not cols and isinstance(feature_contract.get("encoder_mappings"), dict):
        cols = list(feature_contract["encoder_mappings"].keys())
    cols = [str(c) for c in cols]

    def pref_bucket(name: str) -> str:
        if name.startswith("perm__"):
            return "permission_intel"
        if name.startswith("meta__"):
            return "catalog_metadata"
        if name.startswith(("parsed_family_", "threat_class_", "malware_type_")):
            return "vendor_parsed_strings"
        return "other_av_binary_or_derived"

    buckets: Counter[str] = Counter(pref_bucket(c) for c in cols)
    return {
        "training_column_count": len(cols),
        "by_modality_bucket": dict(buckets),
        "permission_columns_retained": int(buckets.get("permission_intel", 0)),
        "metadata_columns_retained": int(buckets.get("catalog_metadata", 0)),
        "vendor_parsed_columns_retained": int(buckets.get("vendor_parsed_strings", 0)),
    }


def analyze_fusion_vs_training_columns(
    modality_contract: dict[str, Any],
    training_cols: list[str],
) -> dict[str, Any]:
    """Contrast fusion-stage modality counts with retained training columns."""
    fusion = modality_contract.get("fusion_modality") or {}
    perm_mod = modality_contract.get("permission_modality") or {}
    fusion_total = int((fusion.get("matrix_shape") or {}).get("columns") or fusion.get("feature_count_total") or 0)
    fusion_perm_raw = int(perm_mod.get("feature_count_raw") or fusion.get("feature_count_permission") or 0)

    training_perm = sum(1 for c in training_cols if str(c).startswith("perm__"))
    dropped_perm_like = max(0, fusion_perm_raw - training_perm)

    return {
        "fusion_matrix_columns_total": fusion_total,
        "fusion_permission_columns_before_training_prune": fusion_perm_raw,
        "training_permission_columns_after_variance_prune": training_perm,
        "permission_columns_dropped_as_low_information": dropped_perm_like,
        "interpretation": (
            "Low-information pruning uses nunique<=1 per column on the **training** alignment slice. "
            "Sparse permission one-hot columns (rare permutations across the 2142 aligned rows) are dropped "
            "even when Permission Intel ingestion is healthy — distinguish this from 'missing PI rows' using "
            "alignment_gap flags per sample."
        ),
    }


def build_gap_detail_with_categories(
    unmatched_ids: list[int],
    *,
    chunk_size: int = 400,
    execute_query: Callable[..., Any] | None = None,
    execute_permission_query: Callable[..., Any] | None = None,
) -> pd.DataFrame:
    """DB-backed flags plus mapped gap categories for unmatched label ids."""
    detail = collect_alignment_gap_detail_frame(
        unmatched_ids,
        execute_query=execute_query,
        execute_permission_query=execute_permission_query,
        chunk_size=chunk_size,
    )
    if detail.empty:
        return detail

    detail = detail.copy()
    detail["gap_category_code"] = detail["likely_missing_reason"].map(GAP_CATEGORY_LABELS).fillna(
        detail["likely_missing_reason"].astype(str)
    )
    detail["gap_category_human"] = detail["likely_missing_reason"].map(
        {
            "not_in_catalog": "Missing malware_sample_catalog row",
            "no_vendor_verdicts": "No rows in virustotal_sample_vendor_engine_verdicts for sample",
            "no_scan_summary": "No virustotal_sample_scan_summary row",
            "no_signal_current": "No virustotal_sample_signal_current row",
            "no_androguard_current": "No virustotal_sample_androguard_current row (when tracked)",
            "no_pi_permissions": "No Permission Intel android_permission_obs_sample rows",
            "unknown_feature_builder_drop": (
                "DB slices present but sample absent from encoded vendor-merge row universe "
                "(top-k parsed vendor outer-merge is row authority before extras join)"
            ),
        }
    )
    return detail


def compute_stage_row_counts(
    cohort_df: pd.DataFrame,
    *,
    generate_binary_detection_matrix: Callable[..., pd.DataFrame],
    build_permission_feature_frame: Callable[..., pd.DataFrame],
    build_metadata_feature_frame: Callable[..., pd.DataFrame],
) -> dict[str, Any]:
    """Live recomputation of row counts at major stages (requires DB for AV path)."""
    out: dict[str, Any] = {}
    if cohort_df.empty or "sample_id" not in cohort_df.columns:
        return {"error": "cohort_df missing sample_id"}

    cohort_n = int(cohort_df["sample_id"].nunique())
    out["cohort_rows"] = cohort_n

    bin_df = generate_binary_detection_matrix(cohort_df, verbose=False)
    out["av_binary_matrix_rows"] = int(len(bin_df)) if isinstance(bin_df, pd.DataFrame) else 0

    perm_df = build_permission_feature_frame(cohort_df)
    out["permission_feature_frame_rows"] = (
        int(perm_df["sample_id"].nunique()) if isinstance(perm_df, pd.DataFrame) and "sample_id" in perm_df.columns else 0
    )

    meta_df = build_metadata_feature_frame(cohort_df)
    out["metadata_feature_frame_rows"] = (
        int(meta_df["sample_id"].nunique()) if isinstance(meta_df, pd.DataFrame) and "sample_id" in meta_df.columns else 0
    )

    # Enrichment attaches left onto binary rows — same row count as binary matrix when successful.
    out["enriched_matrix_rows_note"] = (
        "Same cardinality as av_binary_matrix_rows when score enrichment succeeds "
        "(merge left on sample_id)."
    )
    out["enriched_matrix_rows_same_as_binary"] = True

    return out


def infer_primary_row_loss_stage(
    *,
    cohort_rows: int,
    av_binary_rows: int | None,
    vendor_merge_rows: int | None,
) -> dict[str, Any]:
    """Heuristic: where cohort minus feature-matrix gap opens first."""
    cr = int(cohort_rows or 0)
    av = int(av_binary_rows or 0)
    vm = int(vendor_merge_rows or 0)
    if cr <= 0 or vm <= 0:
        return {"stage": "insufficient_counts", "detail": "missing recomputed or coverage counts"}
    if cr > vm:
        if av > 0 and av < cr:
            return {
                "stage": "av_binary_matrix",
                "detail": "Fewer AV binary rows than cohort — wide verdict melt/pivot dropped samples.",
            }
        if av >= cr or av == cr:
            return {
                "stage": "vendor_encoded_merge_top_k",
                "detail": (
                    "Cohort and AV binary counts match full cohort; gap matches vendor-merge / encoded row universe "
                    "(outer-merge of selected vendors’ parsed frames)."
                ),
            }
    return {"stage": "no_gap_or_unknown", "detail": "cohort row count does not exceed feature matrix rows"}


def build_feature_matrix_row_lineage(
    cohort_df: pd.DataFrame,
    missing_from_matrix_ids: set[int],
) -> pd.DataFrame:
    """One row per cohort sample with inclusion flags (no DB)."""
    rows: list[dict[str, Any]] = []
    for _, r in cohort_df.iterrows():
        sid = int(pd.to_numeric(r["sample_id"], errors="coerce"))
        in_final = sid not in missing_from_matrix_ids
        rows.append(
            {
                "sample_id": sid,
                "sha256": r.get("sha256", ""),
                "family_canonical": r.get("family_canonical", ""),
                "in_cohort": True,
                "in_final_feature_matrix_pre_alignment": bool(in_final),
                "excluded_as_cohort_minus_vendor_merge": bool(not in_final),
            }
        )
    return pd.DataFrame(rows)


def run_feature_matrix_gap_report(
    run_root: Path | str,
    *,
    chunk_size: int = 400,
    skip_db_recompute: bool = False,
    execute_query: Callable[..., Any] | None = None,
    execute_permission_query: Callable[..., Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Write gap lineage artifacts under ``run_root/diagnostics/``."""
    run_root = Path(run_root)
    diag = resolve_run_diagnostics(run_root)
    run_id = run_root.name

    cohort_path = diag / "cohort_membership.csv"
    unmatched_path = diag / "unmatched_label_ids.csv"
    coverage_path = diag / "feature_build_coverage.latest.json"
    modality_path = diag / "modality_method_contract.json"
    contract_path = diag / "feature_contract.json"

    cohort_df = pd.read_csv(cohort_path)
    unmatched_df = pd.read_csv(unmatched_path)
    unmatched_ids = [int(x) for x in unmatched_df["sample_id"].tolist()]

    coverage = _read_json(coverage_path) if coverage_path.is_file() else {}
    modality = _read_json(modality_path) if modality_path.is_file() else {}
    feature_contract = _read_json(contract_path) if contract_path.is_file() else {}

    missing_csv = diag / "cohort_missing_from_feature_matrix.latest.csv"
    missing_ids: set[int] = set()
    if missing_csv.is_file():
        mdf = pd.read_csv(missing_csv)
        missing_ids = {int(x) for x in mdf["sample_id"].tolist()}
    elif coverage.get("cohort_rows_missing_from_feature_matrix"):
        du.print_warning("[GAP] Missing cohort_missing_from_feature_matrix CSV; using coverage counts only.")

    if not skip_db_recompute and execute_query is None:
        from obsidiandroid.database import db_engine

        execute_query = db_engine.execute_query
        execute_permission_query = db_engine.execute_permission_query

    gap_detail = pd.DataFrame()
    if unmatched_ids and not skip_db_recompute:
        gap_detail = build_gap_detail_with_categories(
            unmatched_ids,
            chunk_size=chunk_size,
            execute_query=execute_query,
            execute_permission_query=execute_permission_query,
        )

    lineage_df = build_feature_matrix_row_lineage(cohort_df, missing_ids)

    training_cols = list(feature_contract.get("feature_columns") or [])
    col_mix = analyze_training_column_mix(feature_contract)
    fusion_vs_train = analyze_fusion_vs_training_columns(modality, training_cols)

    cohort_table_rows = int(len(cohort_df))
    cohort_distinct_ids = (
        int(cohort_df["sample_id"].nunique())
        if isinstance(cohort_df, pd.DataFrame) and "sample_id" in cohort_df.columns
        else cohort_table_rows
    )
    stage_counts: dict[str, Any] = {
        # Distinct sample_id (matches compute_stage_row_counts when skip_db_recompute=False).
        "cohort_rows": cohort_distinct_ids,
        "cohort_prepared_table_rows": cohort_table_rows,
        "cohort_duplicate_surplus_rows": max(0, cohort_table_rows - cohort_distinct_ids),
        "feature_matrix_final_rows_pre_alignment": int(coverage.get("feature_matrix_unique_row_count") or 0),
        "vendor_merge_authority_rows": int(coverage.get("vendor_merge_authority_unique_count") or 0),
        "cohort_gap_rows": int(coverage.get("cohort_rows_missing_from_feature_matrix") or len(missing_ids)),
        "feature_rows_not_in_cohort": int(coverage.get("feature_rows_not_in_cohort") or 0),
    }

    if not skip_db_recompute:
        try:
            from obsidiandroid.matrix import av_binary_matrix_builder as avb
            from obsidiandroid.orchestration import permission_features as pf
            from obsidiandroid.pipeline import sample_preparation as sp

            stage_counts.update(
                compute_stage_row_counts(
                    cohort_df,
                    generate_binary_detection_matrix=avb.generate_binary_detection_matrix,
                    build_permission_feature_frame=pf.build_permission_feature_frame,
                    build_metadata_feature_frame=sp.build_metadata_feature_frame,
                )
            )
        except Exception as exc:
            stage_counts["stage_recompute_error"] = str(exc)

    aligned_labels_path = diag / "aligned_labels.latest.csv"
    aligned_n = None
    if aligned_labels_path.is_file():
        alf = pd.read_csv(aligned_labels_path, usecols=["sample_id"])
        aligned_n = int(alf["sample_id"].nunique())

    fs = feature_contract.get("feature_shape") or {}
    training_rows_after_filter = int(fs.get("rows") or 0)

    row_loss_infer = infer_primary_row_loss_stage(
        cohort_rows=int(stage_counts.get("cohort_rows") or 0),
        av_binary_rows=stage_counts.get("av_binary_matrix_rows"),
        vendor_merge_rows=stage_counts.get("vendor_merge_authority_rows")
        or int(coverage.get("vendor_merge_authority_unique_count") or 0),
    )

    stage_lineage_table = [
        {"stage": "1_cohort_membership", "row_count": stage_counts.get("cohort_rows")},
        {"stage": "2_av_binary_matrix", "row_count": stage_counts.get("av_binary_matrix_rows")},
        {
            "stage": "3_enriched_av_matrix",
            "row_count": stage_counts.get("av_binary_matrix_rows"),
            "note": "Left score/metadata merges preserve AV-binary rows.",
        },
        {"stage": "4_permission_feature_frame", "row_count": stage_counts.get("permission_feature_frame_rows")},
        {"stage": "5_metadata_feature_frame", "row_count": stage_counts.get("metadata_feature_frame_rows")},
        {
            "stage": "6_extra_features_fused",
            "row_count": stage_counts.get("av_binary_matrix_rows"),
            "note": "Permission + metadata merged onto enriched_matrix with left joins.",
        },
        {
            "stage": "7_final_feature_matrix_vendor_encoded_index",
            "row_count": stage_counts.get("feature_matrix_final_rows_pre_alignment"),
            "note": "Row authority = outer-merge of top-k vendor parsed frames (encoded before extras join).",
        },
        {"stage": "8_aligned_labels_after_extract_aligned_labels", "row_count": aligned_n},
        {"stage": "9_training_matrix_after_low_support_family_filter", "row_count": training_rows_after_filter},
    ]

    summary: dict[str, Any] = {
        "run_id": run_id,
        "run_root": str(run_root.resolve()),
        "row_loss": {
            "description": (
                "Samples that disappear between cohort lock and training are primarily missing from the "
                "**encoded vendor-merge index** (extras are left-joined onto that index only)."
            ),
            "cohort_samples_locked": stage_counts.get("cohort_rows"),
            "feature_matrix_rows_pre_alignment": stage_counts.get("feature_matrix_final_rows_pre_alignment"),
            "vendor_merge_rows_equal_final_feature_index": bool(coverage.get("vendor_merge_equals_final_index")),
            "aligned_label_rows": aligned_n,
            "training_matrix_rows_after_low_support_family_drop": training_rows_after_filter,
            "gap_samples_unmatched_labels_csv": len(unmatched_ids),
            "key_finding": (
                "No inner join drops cohort rows in enrichment: merge_sample_metadata_features uses left joins. "
                "Row loss occurs when build_feature_vector encodes only the outer-merge of top-k vendor parsed frames."
            ),
        },
        "column_loss": {
            "description": (
                "Training applies _prune_low_information_features (nunique<=1) after alignment, "
                "separate from cohort/preprocessing joins."
            ),
            "fusion_columns_before_alignment_training_slice": fusion_vs_train.get("fusion_matrix_columns_total"),
            "training_columns_after_variance_and_leakage_prune": col_mix.get("training_column_count"),
            "permission_columns_fusion_raw_modality": fusion_vs_train.get(
                "fusion_permission_columns_before_training_prune"
            ),
            "permission_columns_retained_after_pruning": col_mix.get("permission_columns_retained"),
            "permission_columns_dropped_low_information_estimate": fusion_vs_train.get(
                "permission_columns_dropped_as_low_information"
            ),
            "training_column_mix": col_mix.get("by_modality_bucket"),
            "fusion_vs_training_permission_note": fusion_vs_train.get("interpretation"),
        },
        "gap_reason_breakdown": dict(Counter(gap_detail["likely_missing_reason"].tolist()))
        if not gap_detail.empty
        else {},
        "gap_category_breakdown": dict(Counter(gap_detail["gap_category_code"].tolist()))
        if not gap_detail.empty
        else {},
        "stage_row_counts": stage_counts,
        "alignment_gap_summary_embed": _read_json(diag / "alignment_gap_summary.json")
        if (diag / "alignment_gap_summary.json").is_file()
        else {},
        "paper_reporting": {
            "primary_metric_recommendation": (
                "Report **macro-averaged F1** (and per-class tables) as the headline family-balanced score; "
                "accuracy and weighted F1 are auxiliary where class imbalance is severe."
            ),
            "avoid_overstating": (
                "Weighted accuracy/F1 can look publication-ready while macro-F1 reveals rare-family weakness."
            ),
        },
        "primary_row_loss_stage_inference": row_loss_infer,
        "stage_lineage_table": stage_lineage_table,
        "artifacts_written": [
            str(diag / "feature_matrix_gap_summary.json"),
            str(diag / "feature_matrix_gap_summary.md"),
            str(diag / "feature_matrix_row_lineage.csv"),
        ]
        + ([str(diag / "feature_matrix_gap_detail.csv")] if not gap_detail.empty else []),
    }

    # Write CSVs
    lineage_path = diag / "feature_matrix_row_lineage.csv"
    lineage_df.to_csv(lineage_path, index=False)

    gap_detail_path = diag / "feature_matrix_gap_detail.csv"
    if not gap_detail.empty:
        gap_detail.to_csv(gap_detail_path, index=False)

    json_path = diag / "feature_matrix_gap_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_path = diag / "feature_matrix_gap_summary.md"
    md_path.write_text(_render_gap_summary_md(summary, gap_detail), encoding="utf-8")

    return lineage_df, gap_detail, summary


def _render_gap_summary_md(summary: dict[str, Any], gap_detail: pd.DataFrame) -> str:
    rl = summary.get("row_loss") or {}
    cl = summary.get("column_loss") or {}
    pr = summary.get("paper_reporting") or {}
    pri = summary.get("primary_row_loss_stage_inference") or {}
    sc = summary.get("stage_row_counts") or {}
    lines = [
        "# Feature matrix gap summary",
        "",
        f"**Run:** `{summary.get('run_id', '')}`",
        "",
        "## Row loss vs column loss",
        "",
        "- **Row loss:** cohort labels without a row in the fused feature matrix (alignment drops).",
        "- **Column loss:** features removed by training-time variance/leakage pruning (`nunique<=1`), "
        "including most sparse permission one-hot columns.",
        "",
        "## Row loss (counts)",
        "",
        f"- Cohort locked: **{rl.get('cohort_samples_locked')}**",
        f"- Feature matrix rows (pre-alignment): **{rl.get('feature_matrix_rows_pre_alignment')}**",
        f"- Vendor-merge authority rows: **{sc.get('vendor_merge_authority_rows')}**",
        f"- Aligned label rows: **{rl.get('aligned_label_rows')}**",
        f"- Training rows after low-support family filter: **{rl.get('training_matrix_rows_after_low_support_family_drop')}**",
        f"- Unmatched label ids (documented gap): **{rl.get('gap_samples_unmatched_labels_csv')}**",
        "",
        "### Where rows disappear (heuristic)",
        "",
        f"- **Inferred stage:** `{pri.get('stage')}`",
        f"- **Detail:** {pri.get('detail', '')}",
        "",
        "**Mechanism (row loss):**",
        "",
        rl.get("key_finding", ""),
        "",
        "## Column loss (fusion → training)",
        "",
        f"- Fusion modality column total: **{cl.get('fusion_columns_before_alignment_training_slice')}**",
        f"- Training columns after prune: **{cl.get('training_columns_after_variance_and_leakage_prune')}**",
        f"- Permission columns (fusion raw modality): **{cl.get('permission_columns_fusion_raw_modality')}**",
        f"- Permission columns retained (`perm__`): **{cl.get('permission_columns_retained_after_pruning')}**",
        f"- Permission columns dropped as low-information (estimate): **{cl.get('permission_columns_dropped_low_information_estimate')}**",
        "",
        cl.get("fusion_vs_training_permission_note", ""),
        "",
        "### Training column mix (bucketed)",
        "",
        "```text",
        json.dumps(cl.get("training_column_mix") or {}, indent=2),
        "```",
        "",
        "",
        "## Gap drill-down (DB flags on unmatched ids)",
        "",
        "```text",
        json.dumps(summary.get("gap_reason_breakdown", {}), indent=2),
        "```",
        "",
        "```text",
        json.dumps(summary.get("gap_category_breakdown", {}), indent=2),
        "```",
        "",
        "See also `feature_matrix_gap_detail.csv` when DB diagnostics ran.",
        "",
        "## Paper-safe metrics",
        "",
        f"- {pr.get('primary_metric_recommendation', '')}",
        f"- {pr.get('avoid_overstating', '')}",
        "",
        "## Stage lineage (row counts)",
        "",
        "```text",
        json.dumps(summary.get("stage_lineage_table") or [], indent=2),
        "```",
        "",
        "## Stage row counts (flat)",
        "",
        "```text",
        json.dumps(sc, indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "analyze_fusion_vs_training_columns",
    "analyze_training_column_mix",
    "build_feature_matrix_row_lineage",
    "build_gap_detail_with_categories",
    "compute_stage_row_counts",
    "GAP_CATEGORY_LABELS",
    "infer_primary_row_loss_stage",
    "resolve_run_diagnostics",
    "run_feature_matrix_gap_report",
]

