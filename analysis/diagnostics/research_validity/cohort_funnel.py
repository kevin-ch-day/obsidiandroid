"""Cohort funnel row counts and row-authority classification."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from config import app_config


def classify_main_training_row_authority(
    *,
    governed_cohort_rows: int,
    vendor_merge_rows: int | None,
    fused_feature_rows: int | None,
    aligned_rows: int | None,
    main_uses_frozen_zero_fill: bool,
) -> str:
    """Return training row authority label for the primary (non-ablation) training path."""
    if main_uses_frozen_zero_fill:
        return "frozen_cohort_zero_fill"
    gc = int(governed_cohort_rows or 0)
    al = int(aligned_rows or 0)
    if gc > 0 and al < gc:
        return "intersection"
    vm = int(vendor_merge_rows or 0)
    if vm > 0 and gc > 0 and vm < gc:
        return "intersection"
    return "vendor_available"


def finalize_cohort_funnel_dict(manifest_context: dict[str, Any]) -> None:
    """Populate ``manifest_context['cohort_funnel']`` + ``main_training_row_authority`` from collected counts."""
    stages: list[dict[str, Any]] = []
    snap = manifest_context.get("analysis_snapshot") or {}
    raw = manifest_context.get("raw_candidate_rows")
    if raw is None:
        raw = snap.get("snapshot_row_count")
    raw = int(raw or 0)

    mapped = manifest_context.get("mapped_known_type_samples")
    if mapped is None:
        mapped = int(manifest_context.get("governed_cohort_rows") or 0)
    else:
        mapped = int(mapped)

    gov = int(manifest_context.get("governed_cohort_rows") or 0)
    perm_n = manifest_context.get("permission_unique_rows")
    if perm_n is not None:
        perm_n = int(perm_n)

    vm = manifest_context.get("vendor_merge_row_count")
    if vm is not None:
        vm = int(vm)
    fused = manifest_context.get("fused_feature_rows")
    if fused is not None:
        fused = int(fused)
    aligned = manifest_context.get("aligned_supervised_rows")
    if aligned is not None:
        aligned = int(aligned)
    post_ls = manifest_context.get("post_low_support_training_rows")
    if post_ls is not None:
        post_ls = int(post_ls)
    feat_matrix_rows = manifest_context.get("feature_matrix_row_count")
    if feat_matrix_rows is not None:
        feat_matrix_rows = int(feat_matrix_rows)
    train_n = manifest_context.get("train_sample_count")
    if train_n is not None:
        train_n = int(train_n)
    test_n = manifest_context.get("test_sample_count")
    if test_n is not None:
        test_n = int(test_n)

    stages.append(
        {
            "stage": "raw_candidates",
            "row_count": raw,
            "notes": "SQL/snapshot lineage (see analysis_snapshot.snapshot_row_count)",
        }
    )
    stages.append(
        {
            "stage": "mapped_known_type_samples",
            "row_count": mapped,
            "notes": "Rows after cohort mapping / filters (fallback = governed cohort if unset)",
        }
    )
    stages.append({"stage": "governed_cohort", "row_count": gov, "notes": "Prepared samples_df"})
    stages.append(
        {
            "stage": "permission_feature_unique_samples",
            "row_count": perm_n if perm_n is not None else "",
            "notes": "Distinct sample_id with permission feature frame rows",
        }
    )
    stages.append(
        {
            "stage": "vendor_feature_rows",
            "row_count": vm if vm is not None else "",
            "notes": "Vendor-merge authority count (extras left-joined onto vendor index)",
        }
    )
    stages.append(
        {
            "stage": "fused_feature_rows",
            "row_count": fused if fused is not None else "",
            "notes": "Final built feature_matrix row count prior to supervised alignment",
        }
    )
    stages.append(
        {
            "stage": "aligned_supervised_rows",
            "row_count": aligned if aligned is not None else "",
            "notes": "Intersection(features, cohort labels)",
        }
    )
    stages.append(
        {
            "stage": "post_low_support_training_rows",
            "row_count": post_ls if post_ls is not None else "",
            "notes": "After min-support family pruning (training matrix rows)",
        }
    )
    stages.append(
        {
            "stage": "training_feature_matrix_rows",
            "row_count": feat_matrix_rows if feat_matrix_rows is not None else "",
            "notes": "After low-information / leakage pruning (fitted columns)",
        }
    )
    stages.append(
        {
            "stage": "eval_train_rows_split_audit",
            "row_count": train_n if train_n is not None else "",
            "notes": "Held-out train shard from deterministic split_audit",
        }
    )
    stages.append(
        {
            "stage": "eval_test_rows_split_audit",
            "row_count": test_n if test_n is not None else "",
            "notes": "Held-out test shard from deterministic split_audit",
        }
    )

    manifest_context["cohort_funnel"] = stages
    manifest_context["main_training_row_authority"] = classify_main_training_row_authority(
        governed_cohort_rows=gov,
        vendor_merge_rows=vm,
        fused_feature_rows=fused,
        aligned_rows=aligned,
        main_uses_frozen_zero_fill=bool(manifest_context.get("main_training_uses_zero_fill", False)),
    )


def build_cohort_funnel_table(manifest_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Materialize funnel rows from ``manifest_context['cohort_funnel']``."""
    raw = manifest_context.get("cohort_funnel")
    if isinstance(raw, list):
        return [dict(row) for row in raw if isinstance(row, dict)]
    return []


def write_cohort_funnel_artifacts(
    *,
    diagnostics_dir: Path,
    manifest_context: dict[str, Any],
) -> list[Path]:
    """Write ``cohort_funnel.csv`` / ``cohort_funnel.md`` and optional PNG."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    rows = build_cohort_funnel_table(manifest_context)
    paths: list[Path] = []
    csv_path = diagnostics_dir / "cohort_funnel.csv"
    if rows:
        fieldnames = sorted({key for row in rows for key in row.keys()})
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        paths.append(csv_path)

    authority = manifest_context.get("main_training_row_authority", "")
    md_path = diagnostics_dir / "cohort_funnel.md"
    lines = [
        "# Cohort funnel (row accountability)",
        "",
        f"- **main_training_row_authority:** `{authority}`",
        "",
        "| stage | row_count | notes |",
        "|-------|-----------|-------|",
    ]
    for row in rows:
        stage = row.get("stage", "")
        count = row.get("row_count", "")
        notes = str(row.get("notes", "") or "").replace("|", "\\|")
        lines.append(f"| {stage} | {count} | {notes} |")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    paths.append(md_path)

    png_path = diagnostics_dir / "cohort_funnel.png"
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        if rows:
            labels = [str(r.get("stage", "")) for r in rows]
            vals = [float(r.get("row_count") or 0) for r in rows]
            fig, ax = plt.subplots(figsize=(10, max(3.5, 0.35 * len(rows))), dpi=140)
            ax.barh(labels[::-1], vals[::-1], color="#4C72B0")
            ax.set_xlabel("Row count")
            ax.set_title("Cohort funnel")
            fig.tight_layout()
            fig.savefig(png_path, bbox_inches="tight")
            plt.close(fig)
            paths.append(png_path)
    except Exception:
        if png_path.exists():
            png_path.unlink(missing_ok=True)

    setattr(app_config, "RUNTIME_COHORT_FUNNEL_CSV_PATH", str(csv_path))
    return paths
