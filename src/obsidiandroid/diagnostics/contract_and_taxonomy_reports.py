"""Write headline vs ablation contract comparison and taxonomy authority review artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.diagnostics.headline_ablation_parity import build_feature_contract_comparison


def write_headline_vs_ablation_contract_reports(
    diagnostics_dir: Path,
    run_id: str,
    *,
    manifest_context: dict[str, Any] | None = None,
    runtime_headline_hash: str | None = None,
) -> tuple[Path | None, Path | None, dict[str, Any]]:
    """Emit ``headline_vs_ablation_contract_comparison.{md,csv}`` under diagnostics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_feature_contract_comparison(
        diagnostics_dir,
        run_id,
        manifest_context=manifest_context,
        runtime_headline_hash=runtime_headline_hash,
    )
    apples = payload.get("apples_to_apples")
    apples_txt = "yes" if apples is True else "no" if apples is False else "unknown"

    md_lines = [
        "# Feature contract comparison (headline vs ablation full_fused)",
        "",
        f"Run ID: `{run_id}`",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| headline_feature_column_hash | `{payload.get('headline_feature_column_hash') or '—'}` |",
        f"| headline_hash_source | `{payload.get('headline_hash_source') or '—'}` |",
        f"| ablation_full_fused_feature_column_hash | `{payload.get('ablation_full_fused_feature_column_hash') or '—'}` |",
        f"| ablation_summary_source | `{payload.get('ablation_summary_source') or '—'}` |",
        f"| split_hash | `{payload.get('split_hash') or '—'}` |",
        f"| label_target | `{payload.get('label_target') or '—'}` |",
        f"| apples_to_apples | **{apples_txt}** |",
        "",
        "## Interpretation",
        "",
        "- Headline leaderboard metrics use the **headline** training matrix (hash above).",
        "- Ablation row **`full_fused`** / **`family_canonical_default`** uses the **ablation harness** matrix.",
        "- Macro-F1 / accuracy between those two are comparable only when feature hashes match.",
        "",
    ]
    if apples is False:
        md_lines.extend(
            [
                "### ⚠ Not directly comparable",
                "",
                f"> {payload.get('incommensurable_message', '')}",
                "",
            ]
        )

    csv_path = diagnostics_dir / f"headline_vs_ablation_contract_comparison_{run_id}.csv"
    md_path = diagnostics_dir / f"headline_vs_ablation_contract_comparison_{run_id}.md"
    row = {
        **{k: v for k, v in payload.items() if k != "incommensurable_message"},
        "apples_to_apples_yes_no": apples_txt,
        "not_comparable_warning": ""
        if apples is not False
        else str(payload.get("incommensurable_message") or ""),
    }
    fieldnames = list(row.keys())
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerow(row)

    md_text = "\n".join(md_lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=csv_path.name,
        csv_text=csv_path.read_text(encoding="utf-8"),
        global_latest_name="headline_vs_ablation_contract_comparison.latest.csv",
    )
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="headline_vs_ablation_contract_comparison.latest.md",
    )

    return md_path, csv_path, payload


def _read_taxonomy_summary(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    p = oh.resolve_taxonomy_consistency_summary_path(diagnostics_dir, run_id)
    if p.is_file():
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            return blob if isinstance(blob, dict) else {}
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def write_taxonomy_type_authority_reports(
    diagnostics_dir: Path,
    run_id: str,
) -> tuple[Path | None, Path | None]:
    """Emit ``taxonomy_type_authority_review.{md,csv}`` with policy + counts + examples."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    summary = _read_taxonomy_summary(diagnostics_dir, run_id)
    summary_present = bool(summary)

    mismatch_globs = sorted(
        diagnostics_dir.glob("taxonomy_consistency_mismatches*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    mismatch_path = None
    for p in mismatch_globs:
        if run_id in p.name or "latest" in p.name:
            mismatch_path = p
            break
    if mismatch_path is None and mismatch_globs:
        mismatch_path = mismatch_globs[0]

    df = pd.DataFrame()
    if mismatch_path is not None and mismatch_path.is_file():
        try:
            df = pd.read_csv(mismatch_path)
        except Exception:
            df = pd.DataFrame()

    distinct_cohort = distinct_label = None
    if not df.empty and "type_slug_expected" in df.columns:
        distinct_cohort = int(df["type_slug_expected"].fillna("").astype(str).str.strip().replace("", pd.NA).nunique())
    if not df.empty and "label_type_slug" in df.columns:
        distinct_label = int(df["label_type_slug"].fillna("").astype(str).str.strip().replace("", pd.NA).nunique())

    if summary_present:
        rows_eval: int | None = int(summary.get("rows_evaluated", 0) or 0)
        fam_eval: int | None = int(summary.get("family_rows_evaluated", 0) or 0)
        pred_err: int | None = int(summary.get("prediction_error_count", 0) or 0)
        type_map: int | None = int(summary.get("type_mismatch_count", 0) or 0)
        type_miss: int | None = int(summary.get("type_missing_label_count", 0) or 0)
        type_nonc: int | None = int(summary.get("type_noncanonical_count", 0) or 0)
        fam_lab_mm: int | None = int(summary.get("family_label_mismatch_count", 0) or 0)
        tax_total: int | None = int(summary.get("taxonomy_mismatch_count", 0) or 0)
    else:
        rows_eval = fam_eval = pred_err = type_map = type_miss = type_nonc = fam_lab_mm = tax_total = None

    fam_correct_est = (
        max(0, fam_eval - pred_err)
        if fam_eval is not None and pred_err is not None and fam_eval
        else None
    )

    md_lines = [
        "# Taxonomy authority decision",
        "",
        f"Run ID: `{run_id}`",
        "",
        "## Policy (recommended)",
        "",
        "- **Cohort `type_slug`** is authoritative for **type-level reporting** (prevalence, cohort composition).",
        "- **`classification_label`** strings (and label-derived type tokens) are **not** type ground truth.",
        "- Treat **label-derived type** (`label_type_slug`) as a parser/rendering artifact unless explicitly approved.",
        "",
        "## Headline counts",
        "",
        "| Metric | Value | Notes |",
        "| --- | ---: | --- |",
        f"| rows_evaluated (taxonomy audit) | {rows_eval if rows_eval is not None else '—'} | structured classification rows |",
        f"| family_rows_evaluated | {fam_eval if fam_eval is not None else '—'} | rows with cohort family metadata |",
        f"| distinct cohort types (taxonomy-flag CSV) | {distinct_cohort if distinct_cohort is not None else '—'} | unique `type_slug_expected` in mismatch export |",
        f"| distinct label-derived types (taxonomy-flag CSV) | {distinct_label if distinct_label is not None else '—'} | unique `label_type_slug` in mismatch export |",
        f"| taxonomy_mismatch rows (union) | {tax_total if tax_total is not None else '—'} | cohort vs label-string inconsistency flags |",
        f"| type_mapping_mismatch | {type_map if type_map is not None else '—'} | cohort type ≠ canonical label-derived type |",
        f"| type_label_missing | {type_miss if type_miss is not None else '—'} | label string lacks extractable type |",
        f"| type_label_noncanonical | {type_nonc if type_nonc is not None else '—'} | label-derived type not in configured canonical set |",
        f"| label_family_mismatch | {fam_lab_mm if fam_lab_mm is not None else '—'} | label family token ≠ normalized predicted family |",
        f"| family_prediction_errors | {pred_err if pred_err is not None else '—'} | **model** predicted family ≠ cohort family |",
        f"| family_prediction_match (est.) | {fam_correct_est if fam_correct_est is not None else '—'} | family_rows − prediction_errors |",
        "",
        "## Warning taxonomy (how to read diagnostics)",
        "",
        "| Issue | Meaning |",
        "| --- | --- |",
        "| Family prediction errors | Real holdout classification error vs cohort family. |",
        "| Type mapping mismatches | Authority/rendering: cohort type vs type implied by `classification_label`. |",
        "| Missing type in label | Data quality: label string missing extractable type token. |",
        "| Label family mismatch | Parser/consistency: structured label family token vs model output token. |",
        "",
    ]

    md_lines.append("## Examples (sample rows)\n")
    if not summary_present and df.empty:
        md_lines.extend(
            [
                "> NOTE: No taxonomy-consistency summary or mismatch export was found for this run.",
                "> This report is policy-only (counts are unavailable).",
                "",
            ]
        )

    def _sample(reason: str, n: int = 3) -> None:
        if df.empty or "mismatch_reason" not in df.columns:
            return
        sub = df[df["mismatch_reason"].astype(str) == reason].head(n)
        if sub.empty:
            return
        md_lines.append(f"### `{reason}`\n")
        md_lines.append(sub.head(n).to_markdown(index=False))
        md_lines.append("")

    _sample("type_mapping_mismatch", 4)
    _sample("type_label_missing", 3)
    _sample("type_label_noncanonical", 3)
    _sample("label_family_mismatch", 3)

    pred_path = diagnostics_dir / f"prediction_errors_{run_id}.csv"
    if not pred_path.is_file():
        pred_path = diagnostics_dir / "prediction_errors.latest.csv"
    if pred_path.is_file():
        try:
            pdf = pd.read_csv(pred_path)
            if not pdf.empty:
                md_lines.append("### `family_prediction_errors` (prediction_errors export)\n")
                md_lines.append(pdf.head(5).to_markdown(index=False))
                md_lines.append("")
        except Exception:
            pass

    csv_payload = {
        "run_id": run_id,
        "rows_evaluated": rows_eval if rows_eval is not None else "",
        "family_rows_evaluated": fam_eval if fam_eval is not None else "",
        "distinct_cohort_type_slug_taxonomy_csv": distinct_cohort if distinct_cohort is not None else "",
        "distinct_label_derived_type_slug_taxonomy_csv": distinct_label if distinct_label is not None else "",
        "taxonomy_mismatch_rows": tax_total if tax_total is not None else "",
        "type_mapping_mismatch_rows": type_map if type_map is not None else "",
        "type_label_missing_rows": type_miss if type_miss is not None else "",
        "type_label_noncanonical_rows": type_nonc if type_nonc is not None else "",
        "label_family_mismatch_rows": fam_lab_mm if fam_lab_mm is not None else "",
        "family_prediction_errors": pred_err if pred_err is not None else "",
        "family_prediction_match_est": fam_correct_est if fam_correct_est is not None else "",
        "mismatch_csv_path": str(mismatch_path) if mismatch_path else "",
    }

    md_path = diagnostics_dir / f"taxonomy_type_authority_review_{run_id}.md"
    csv_path = diagnostics_dir / f"taxonomy_type_authority_review_{run_id}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv_payload.keys()))
        w.writeheader()
        w.writerow(csv_payload)
    md_text = "\n".join(md_lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=csv_path.name,
        csv_text=csv_path.read_text(encoding="utf-8"),
        global_latest_name="taxonomy_type_authority_review.latest.csv",
    )
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="taxonomy_type_authority_review.latest.md",
    )

    return md_path, csv_path


__all__ = [
    "write_headline_vs_ablation_contract_reports",
    "write_taxonomy_type_authority_reports",
]
