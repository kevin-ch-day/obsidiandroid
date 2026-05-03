"""Structured taxonomy / classification label QA from taxonomy consistency artifacts."""

from __future__ import annotations

import json
from pathlib import Path


def write_taxonomy_label_quality_audit(*, diagnostics_dir: Path, run_id: str) -> Path:
    """Write ``taxonomy_label_quality_audit.md`` from ``taxonomy_consistency_summary`` JSON."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    out_path = diagnostics_dir / "taxonomy_label_quality_audit.md"

    candidates = [
        diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json",
        diagnostics_dir / "taxonomy_consistency_summary.latest.json",
    ]
    summary_path = next((p for p in candidates if p.exists()), None)

    lines: list[str] = [
        "# Taxonomy & structured label quality audit",
        "",
        "Source: `classification_label_resolver._export_taxonomy_consistency_audit` exports. ",
        "Counts separate **taxonomy construction issues** (label string vs expected metadata) from **model prediction errors**.",
        "",
    ]

    if summary_path is None:
        lines.append("_No `taxonomy_consistency_summary_*.json` found — run label export with taxonomy audit enabled._\n")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path

    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pylint: disable=broad-except
        lines.append(f"_Failed reading JSON ({summary_path.name}): `{exc}`_\n")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path

    rows_eval = int(payload.get("rows_evaluated", 0) or 0)
    type_eval = int(payload.get("type_rows_evaluated", 0) or 0)
    family_eval = int(payload.get("family_rows_evaluated", 0) or 0)
    missing = int(payload.get("type_missing_label_count", 0) or 0)
    noncanon = int(payload.get("type_noncanonical_count", 0) or 0)
    type_map = int(payload.get("type_mismatch_count", 0) or 0)
    fam_lab = int(payload.get("family_label_mismatch_count", 0) or 0)
    tax_total = int(payload.get("taxonomy_mismatch_count", 0) or 0)
    pred_err = int(payload.get("prediction_error_count", 0) or 0)

    lines.extend(
        [
            f"**Evidence file:** `{summary_path.name}`",
            "",
            "## Headline counts",
            "",
            "| Field | Value | Interpretation |",
            "|-------|-------|----------------|",
            f"| rows_evaluated | {rows_eval} | Labeled classification rows audited |",
            f"| type_rows_evaluated | {type_eval} | Rows where `type_slug_expected` was populated |",
            f"| family_rows_evaluated | {family_eval} | Rows where expected family metadata present |",
            f"| type_missing_label_count | {missing} | `type_label_missing` — label string lacks extractable type |",
            f"| type_noncanonical_count | {noncanon} | Type token not in canonical configured set |",
            f"| type_mismatch_count | {type_map} | Canonical type token differs from expected metadata |",
            f"| family_label_mismatch_count | {fam_lab} | Family slug from label mismatches projected prediction family token |",
            f"| taxonomy_mismatch_count | {tax_total} | Union taxonomy issues (not pure prediction disagreement) |",
            f"| prediction_error_count | {pred_err} | Predicted family ≠ expected cohort family when both present |",
            "",
            "## Scientific validity checklist",
            "",
            "- **`type_missing` / `type_mapping` conflicts:** invalidate cross-type summaries that assume label builder always emits canonical `type_slug`.",
            "- **Noncanonical tokens:** taxonomy dictionary gaps or stale `CANONICAL_TYPE_SLUGS` — revisit before comparative type-level claims.",
            "- **Prediction errors vs taxonomy errors:** separate when attributing confusion matrices to modeling vs labeling pipeline.",
            "- **Predicted family on wrong type:** inspect `taxonomy_consistency_mismatches_*.csv` rows with both type and family flags.",
            "",
            "### Linked CSVs",
            "",
            f"- `{payload.get('mismatch_csv_path', 'taxonomy_consistency_mismatches_*.csv')}`",
            f"- `{payload.get('prediction_errors_csv_path', 'prediction_errors_*.csv')}`",
            f"- `{payload.get('noncanonical_type_tokens_csv_path', 'taxonomy_noncanonical_type_tokens_*.csv')}`",
            "",
            f"**type_expected_source mode:** `{payload.get('type_expected_source', '')}`",
            "",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


__all__ = ["write_taxonomy_label_quality_audit"]
