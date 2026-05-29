"""Cohort funnel row counts and row-authority classification."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from config import app_config

from ..cohort_vocabulary import read_prepared_cohort_row_count, read_sql_scope_row_count


def _format_top_family_counts(counts: dict[str, Any], *, limit: int = 8) -> str:
    """Render top family count pairs for compact markdown notes."""
    if not isinstance(counts, dict) or not counts:
        return ""
    rows: list[tuple[str, int]] = []
    for key, value in counts.items():
        try:
            rows.append((str(key), int(value)))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda item: (-item[1], item[0].lower()))
    preview = [f"{name}={count}" for name, count in rows[: max(1, int(limit))]]
    if len(rows) > len(preview):
        preview.append("…")
    return ", ".join(preview)


def _format_low_support_drop_detail(rows: list[dict[str, Any]], *, limit: int = 10) -> str:
    """Render compact low-support family drop detail for markdown narratives."""
    if not isinstance(rows, list) or not rows:
        return ""
    normalized: list[tuple[str, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        family = str(row.get("family", "")).strip()
        if not family:
            continue
        try:
            support = int(row.get("aligned_support"))
        except (TypeError, ValueError):
            continue
        normalized.append((family, support))
    normalized.sort(key=lambda item: (item[1], item[0].lower()))
    preview = [f"{family}={support}" for family, support in normalized[: max(1, int(limit))]]
    if len(normalized) > len(preview):
        preview.append("…")
    return ", ".join(preview)


def classify_main_training_row_authority(
    *,
    prepared_cohort_rows: int,
    vendor_merge_rows: int | None,
    fused_feature_rows: int | None,
    aligned_rows: int | None,
    main_uses_frozen_zero_fill: bool,
    feature_matrix_row_authority: str | None = None,
) -> str:
    """Return training row authority label for the primary (non-ablation) training path."""
    if main_uses_frozen_zero_fill:
        return "frozen_cohort_zero_fill"
    auth = str(feature_matrix_row_authority or "").strip().lower()
    if auth == "governed_cohort":
        return "governed_cohort"
    gc = int(prepared_cohort_rows or 0)
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
    sql_scope = read_sql_scope_row_count(manifest_context)
    if sql_scope is None:
        try:
            sql_scope = int(snap.get("snapshot_row_count") or 0)
        except (TypeError, ValueError):
            sql_scope = 0
    sql_scope_rows = int(sql_scope or 0)

    gov = int(read_prepared_cohort_row_count(manifest_context) or 0)
    perm_n = manifest_context.get("permission_unique_rows")
    if perm_n is not None:
        perm_n = int(perm_n)

    vm = manifest_context.get("vendor_merge_row_count")
    if vm is not None:
        vm = int(vm)
    fused = manifest_context.get("fused_feature_rows")
    if fused is not None:
        fused = int(fused)
    auth_raw = str(manifest_context.get("feature_matrix_row_authority") or "").strip()
    aligned = manifest_context.get("aligned_supervised_rows")
    if aligned is not None:
        aligned = int(aligned)
    alignment_attrition = (
        manifest_context.get("alignment_attrition_stats")
        if isinstance(manifest_context.get("alignment_attrition_stats"), dict)
        else {}
    )
    authority_drop = alignment_attrition.get("alignment_non_authoritative_family_drop_count")
    if authority_drop is not None:
        authority_drop = int(authority_drop)
    authority_rescued = alignment_attrition.get("alignment_live_authority_rescue_count")
    if authority_rescued is not None:
        authority_rescued = int(authority_rescued)
    post_authority = alignment_attrition.get("alignment_rows_post_authority_filter")
    if post_authority is not None:
        post_authority = int(post_authority)
    post_ls = manifest_context.get("post_low_support_training_rows")
    if post_ls is not None:
        post_ls = int(post_ls)
    feat_cols_post = manifest_context.get("feature_matrix_cols_post_prune")
    if feat_cols_post is None:
        feat_cols_post = manifest_context.get("feature_matrix_row_count")
    if feat_cols_post is not None:
        feat_cols_post = int(feat_cols_post)
    train_n = manifest_context.get("train_sample_count")
    if train_n is not None:
        train_n = int(train_n)
    test_n = manifest_context.get("test_sample_count")
    if test_n is not None:
        test_n = int(test_n)
    temporal = manifest_context.get("split", {}) if isinstance(manifest_context.get("split"), dict) else {}
    temporal = temporal.get("temporal_split_summary") if isinstance(temporal, dict) else None
    temporal_dropped = None
    if isinstance(temporal, dict):
        try:
            temporal_dropped = int(temporal.get("test_rows_dropped_unseen_train_classes"))
        except (TypeError, ValueError):
            temporal_dropped = None
    post_temporal = None
    if post_ls is not None and temporal_dropped is not None:
        post_temporal = max(int(post_ls) - int(temporal_dropped), 0)

    stages.append(
        {
            "stage": "cohort_sql_scope",
            "row_count": sql_scope_rows,
            "notes": "Database head count for profile cohort SQL (joins + time contract + gates); not samples_df length",
        }
    )
    stages.append(
        {
            "stage": "prepared_cohort",
            "row_count": gov,
            "notes": "Rows in samples_df after load_and_prepare_samples (what downstream stages consume)",
        }
    )
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
    fused_notes = "Final built feature_matrix row count prior to supervised alignment"
    if auth_raw.lower() == "governed_cohort":
        fused_notes = (
            "Fused ML matrix rows reindexed to governed cohort (vendor gaps unknown/zero-filled; "
            "same row count as prepared cohort unless duplicates/null-label policy applies)"
        )
    stages.append(
        {
            "stage": "fused_feature_rows",
            "row_count": fused if fused is not None else "",
            "notes": fused_notes,
        }
    )
    stages.append(
        {
            "stage": "aligned_supervised_rows",
            "row_count": aligned if aligned is not None else "",
            "notes": "Intersection(features, cohort labels)",
        }
    )
    if post_authority is not None and authority_drop is not None:
        rescue_note = ""
        if authority_rescued:
            rescue_note = f"; rescued {authority_rescued} live-authority family row(s) absent from local registry"
        stages.append(
            {
                "stage": "post_family_authority_filter_rows",
                "row_count": post_authority,
                "notes": (
                    "Rows remaining after family-authority admissibility checks before min-support filtering"
                    f" (dropped {authority_drop} non-authoritative family rows{rescue_note})"
                ),
            }
        )
    stages.append(
        {
            "stage": "post_low_support_training_rows",
            "row_count": post_ls if post_ls is not None else "",
            "notes": (
                "Post-family-support trainable pool: rows after min-family-support filtering "
                "(not cohort size; column pruning does not drop rows)"
            ),
        }
    )
    if post_temporal is not None:
        stages.append(
            {
                "stage": "post_temporal_known_class_rows",
                "row_count": post_temporal,
                "notes": (
                    "Rows remaining after temporal future-only unseen-class exclusion and before train/test split"
                    f" (dropped {temporal_dropped} temporal unseen-class rows)"
                ),
            }
        )
    stages.append(
        {
            "stage": "training_feature_cols_post_prune",
            "row_count": feat_cols_post if feat_cols_post is not None else "",
            "column_count": feat_cols_post if feat_cols_post is not None else "",
            "metric_kind": "training_feature_column_count",
            "notes": (
                "Feature column count after low-information / leakage pruning (not sample rows). "
                "``row_count`` mirrors ``column_count`` for legacy CSV/PNG readers."
            ),
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
        prepared_cohort_rows=gov,
        vendor_merge_rows=vm,
        fused_feature_rows=fused,
        aligned_rows=aligned,
        main_uses_frozen_zero_fill=bool(manifest_context.get("main_training_uses_zero_fill", False)),
        feature_matrix_row_authority=str(manifest_context.get("feature_matrix_row_authority") or ""),
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
        "# Cohort funnel (SQL scope → prepared rows → features)",
        "",
        f"- **main_training_row_authority:** `{authority}`",
        "",
        "| stage | value | notes |",
        "|-------|-------|-------|",
    ]
    for row in rows:
        stage = row.get("stage", "")
        val = row.get("column_count")
        if val in (None, ""):
            val = row.get("row_count", "")
        notes = str(row.get("notes", "") or "").replace("|", "\\|")
        lines.append(f"| {stage} | {val} | {notes} |")
    lines.append("")
    cohort_policy = (
        manifest_context.get("cohort_policy_snapshot")
        if isinstance(manifest_context.get("cohort_policy_snapshot"), dict)
        else {}
    )
    cohort_gate_rows = (
        manifest_context.get("cohort_gate_rows")
        if isinstance(manifest_context.get("cohort_gate_rows"), list)
        else []
    )
    if cohort_policy or cohort_gate_rows:
        lines.extend(
            [
                "## Prepared cohort policy detail",
                "",
            ]
        )
        if cohort_policy:
            lines.append(
                f"- **exclude_families_deferred_by_snapshot_lock:** `{cohort_policy.get('exclude_families_deferred_by_snapshot_lock')}`"
            )
            lines.append(
                f"- **min_samples_per_family_applied_in_sql:** `{cohort_policy.get('min_samples_per_family_applied_in_sql')}`"
            )
            lines.append(
                f"- **configured_min_samples_per_family:** `{cohort_policy.get('configured_min_samples_per_family')}`"
            )
            lines.append(
                f"- **min_samples_per_family_sql_value:** `{cohort_policy.get('min_samples_per_family_sql_value')}`"
            )
            requested = cohort_policy.get("requested_exclude_families") or []
            if isinstance(requested, list):
                lines.append(
                    f"- **requested_exclude_families:** `{', '.join(str(x) for x in requested) or '(none)'}`"
                )
        if cohort_gate_rows:
            first_gate = cohort_gate_rows[0] if isinstance(cohort_gate_rows[0], dict) else {}
            if first_gate:
                lines.append(
                    f"- **first gate:** `{first_gate.get('gate_name', '')}` "
                    f"({first_gate.get('count_before', '')} → {first_gate.get('count_after', '')}; "
                    f"dropped {first_gate.get('dropped', '')})"
                )
                details = str(first_gate.get("details", "") or "").strip()
                if details:
                    lines.append(f"- **first gate details:** {details}")
        lines.append("")
    alignment_attrition_details = (
        manifest_context.get("alignment_attrition_details")
        if isinstance(manifest_context.get("alignment_attrition_details"), dict)
        else {}
    )
    rescued_families = (
        alignment_attrition_details.get("alignment_live_authority_rescue_families")
        if isinstance(alignment_attrition_details, dict)
        else {}
    )
    dropped_families = (
        alignment_attrition_details.get("alignment_non_authoritative_family_drop_families")
        if isinstance(alignment_attrition_details, dict)
        else {}
    )
    rescued_line = _format_top_family_counts(rescued_families)
    dropped_line = _format_top_family_counts(dropped_families)
    if rescued_line or dropped_line:
        lines.extend(
            [
                "## Alignment attrition detail",
                "",
            ]
        )
        if rescued_line:
            lines.append(f"- **Live-authority family rescues:** {rescued_line}")
        if dropped_line:
            lines.append(f"- **Remaining non-authoritative family drops:** {dropped_line}")
        lines.append("")
    low_support_detail = (
        manifest_context.get("low_support_family_drop_detail")
        if isinstance(manifest_context.get("low_support_family_drop_detail"), list)
        else []
    )
    low_support_line = _format_low_support_drop_detail(low_support_detail)
    if low_support_line:
        lines.extend(
            [
                "## Low-support drop detail",
                "",
                f"- **Families removed by support threshold:** {low_support_line}",
                "",
            ]
        )
    temporal = manifest_context.get("split", {}) if isinstance(manifest_context.get("split"), dict) else {}
    temporal = temporal.get("temporal_split_summary") if isinstance(temporal, dict) else None
    if isinstance(temporal, dict) and temporal:
        cutoff = temporal.get("test_year_floor")
        ymin = temporal.get("observed_year_min")
        ymax = temporal.get("observed_year_max")
        dropped = temporal.get("test_rows_dropped_unseen_train_classes")
        dropped_families = (
            temporal.get("test_rows_dropped_unseen_train_class_families")
            if isinstance(temporal.get("test_rows_dropped_unseen_train_class_families"), dict)
            else {}
        )
        lines.extend(
            [
                "## Temporal holdout",
                "",
                f"- **cutoff year:** `{cutoff}`",
                f"- **observed year span:** `{ymin}` — `{ymax}`",
                f"- **future-only class rows dropped from test:** `{dropped}`",
            ]
        )
        dropped_family_line = _format_top_family_counts(dropped_families)
        if dropped_family_line:
            lines.append(f"- **Future-only class families dropped from test:** {dropped_family_line}")
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

            def _funnel_bar_value(row: dict[str, Any]) -> float:
                cc = row.get("column_count")
                if cc not in (None, ""):
                    try:
                        return float(cc)
                    except (TypeError, ValueError):
                        pass
                rc = row.get("row_count")
                try:
                    return float(rc or 0)
                except (TypeError, ValueError):
                    return 0.0

            vals = [_funnel_bar_value(r) for r in rows]
            fig, ax = plt.subplots(figsize=(10, max(3.5, 0.35 * len(rows))), dpi=140)
            ax.barh(labels[::-1], vals[::-1], color="#4C72B0")
            ax.set_xlabel("Count (rows or feature columns — see cohort_funnel.csv metric_kind)")
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
