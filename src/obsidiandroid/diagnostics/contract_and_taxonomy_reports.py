"""Write headline vs ablation contract comparison and taxonomy authority review artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.diagnostics.headline_ablation_parity import build_feature_contract_comparison
from obsidiandroid.diagnostics.family_type_authority_coverage import (
    LIVE_VIEW_MISSING_WARNING,
    build_bucket_summary,
    build_conflict_summary,
    build_missing_candidates,
    build_unknown_type_queue,
    load_authority_df,
)


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
        f"| headline_permission_feature_count | `{payload.get('headline_permission_feature_count') or 0}` |",
        f"| headline_vendor_semantic_feature_count | `{payload.get('headline_vendor_semantic_feature_count') or 0}` |",
        f"| headline_extra_non_vendor_permission_feature_count | `{payload.get('headline_extra_non_vendor_permission_feature_count') or 0}` |",
        f"| apples_to_apples | **{apples_txt}** |",
        "",
        "## Interpretation",
        "",
        "- Headline leaderboard metrics use the **headline** training matrix (hash above).",
        "- Ablation row **`full_fused`** / **`family_canonical_default`** uses the **ablation harness** matrix.",
        "- Macro-F1 / accuracy between those two are comparable only when feature hashes match.",
        "- If the headline contract reports extra non-vendor/non-permission columns, the mismatch is structural rather than incidental.",
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


def _normalize_sample_id_key(value: Any) -> str:
    """Normalize sample-id-like values into stable string keys."""
    try:
        fval = float(value)
        ival = int(fval)
        if fval == ival:
            return str(ival)
    except Exception:
        pass
    return str(value).strip()


def _load_runtime_run_cohort_sample_keys() -> tuple[set[str] | None, str]:
    """Best-effort run cohort sample-id scope for run-scoped authority filtering."""
    frame = getattr(oh.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", None)
    if not isinstance(frame, pd.DataFrame) or frame.empty or "sample_id" not in frame.columns:
        return None, ""
    keys = {
        _normalize_sample_id_key(value)
        for value in frame["sample_id"].tolist()
        if _normalize_sample_id_key(value) not in {"", "nan", "none", "null"}
    }
    if not keys:
        return None, ""
    return keys, "prepared_runtime_split_sample_metadata"


def _coerce_frame_count(frame: pd.DataFrame, column: str) -> int:
    """Sum a count-like column from a dataframe when present."""
    if frame.empty or column not in frame.columns:
        return 0
    try:
        return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())
    except Exception:
        return 0


def _authority_scope_payload(
    *,
    scope_name: str,
    source_mode: str,
    source_label: str,
    df: pd.DataFrame,
    note: str = "",
) -> dict[str, Any]:
    """Build summary payload for one authority scope."""
    available = not df.empty
    bucket_df = build_bucket_summary(df) if available else pd.DataFrame()
    missing_df = build_missing_candidates(df) if available else pd.DataFrame()
    unknown_type_df = build_unknown_type_queue(df) if available else pd.DataFrame()
    _conflict_summary_df, top_conflicts_df = build_conflict_summary(df) if available else (pd.DataFrame(), pd.DataFrame())

    generic_df = missing_df[missing_df["candidate_kind"] == "generic_or_coarse_label"].copy() if not missing_df.empty else pd.DataFrame()
    plausible_df = missing_df[missing_df["candidate_kind"] == "plausible_real_family_candidate"].copy() if not missing_df.empty else pd.DataFrame()

    return {
        "scope": scope_name,
        "source": source_label,
        "source_mode": source_mode,
        "available": bool(available),
        "note": str(note or "").strip(),
        "row_count": int(len(df)) if available else 0,
        "bucket_rows": bucket_df.to_dict(orient="records") if not bucket_df.empty else [],
        "bucket_counts": {
            str(row.get("authority_bucket", "")): int(row.get("row_count", 0))
            for row in bucket_df.to_dict(orient="records")
        } if not bucket_df.empty else {},
        "resolved_but_no_authority_family_rows": _coerce_frame_count(
            bucket_df[bucket_df["authority_bucket"] == "resolved_but_no_authority_family"]
            if not bucket_df.empty else pd.DataFrame(),
            "row_count",
        ),
        "generic_or_coarse_label_rows": _coerce_frame_count(generic_df, "row_count"),
        "generic_or_coarse_label_tokens": int(generic_df["resolved_family_lc"].nunique()) if not generic_df.empty else 0,
        "authority_family_unknown_type_rows": _coerce_frame_count(
            bucket_df[bucket_df["authority_bucket"] == "authority_family_unknown_type"]
            if not bucket_df.empty else pd.DataFrame(),
            "row_count",
        ),
        "authority_family_unknown_type_families": int(unknown_type_df["family_slug"].nunique()) if not unknown_type_df.empty else 0,
        "resolved_unknown_rows": _coerce_frame_count(
            bucket_df[bucket_df["authority_bucket"] == "resolved_unknown"]
            if not bucket_df.empty else pd.DataFrame(),
            "row_count",
        ),
        "plausible_missing_candidates_top": plausible_df.head(10).to_dict(orient="records") if not plausible_df.empty else [],
        "generic_or_coarse_candidates_top": generic_df.head(10).to_dict(orient="records") if not generic_df.empty else [],
        "unknown_type_families_top": unknown_type_df.head(10).to_dict(orient="records") if not unknown_type_df.empty else [],
        "raw_authority_conflicts_top": top_conflicts_df.head(10).to_dict(orient="records") if not top_conflicts_df.empty else [],
        "_bucket_df": bucket_df,
        "_missing_df": missing_df,
        "_unknown_type_df": unknown_type_df,
        "_top_conflicts_df": top_conflicts_df,
    }


def _taxonomy_split_reason_bucket(reason: str) -> str:
    """Map taxonomy mismatch reasons into operator-facing split categories."""
    token = str(reason or "").strip()
    if token in {"type_mapping_mismatch", "type_label_missing", "type_label_noncanonical", "label_family_mismatch"}:
        return "type_authority_vs_rendering_mismatch"
    return "other_taxonomy_rendering_issue"


def write_taxonomy_authority_split_reports(
    diagnostics_dir: Path,
    run_id: str,
) -> tuple[Path | None, Path | None, Path | None, Path | None]:
    """Emit scope-aware taxonomy authority split artifacts."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    summary = _read_taxonomy_summary(diagnostics_dir, run_id)
    mismatch_path = oh.resolve_taxonomy_consistency_mismatches_path(diagnostics_dir, run_id)
    prediction_path = oh.resolve_prediction_errors_path(diagnostics_dir, run_id)

    mismatch_df = pd.DataFrame()
    prediction_df = pd.DataFrame()
    if mismatch_path.is_file():
        try:
            mismatch_df = pd.read_csv(mismatch_path)
        except Exception:
            mismatch_df = pd.DataFrame()
    if prediction_path.is_file():
        try:
            prediction_df = pd.read_csv(prediction_path)
        except Exception:
            prediction_df = pd.DataFrame()

    authority_df, source_mode, warning = load_authority_df(require_live_view=True)
    global_scope = _authority_scope_payload(
        scope_name="global_authority_catalog",
        source_mode=str(source_mode or "unknown"),
        source_label="v_android_sample_family_type_authority",
        df=authority_df,
        note=str(warning or "").strip(),
    ) if not authority_df.empty else {
        "scope": "global_authority_catalog",
        "source": "v_android_sample_family_type_authority",
        "source_mode": str(source_mode or "unknown"),
        "available": False,
        "note": str(warning or LIVE_VIEW_MISSING_WARNING).strip(),
        "row_count": 0,
        "bucket_rows": [],
        "bucket_counts": {},
        "resolved_but_no_authority_family_rows": 0,
        "generic_or_coarse_label_rows": 0,
        "generic_or_coarse_label_tokens": 0,
        "authority_family_unknown_type_rows": 0,
        "authority_family_unknown_type_families": 0,
        "resolved_unknown_rows": 0,
        "plausible_missing_candidates_top": [],
        "generic_or_coarse_candidates_top": [],
        "unknown_type_families_top": [],
        "raw_authority_conflicts_top": [],
    }

    cohort_keys, cohort_source = _load_runtime_run_cohort_sample_keys()
    if authority_df.empty or not cohort_keys:
        run_scope = {
            "scope": "run_cohort_authority",
            "source": "v_android_sample_family_type_authority",
            "source_mode": str(source_mode or "unknown"),
            "available": False,
            "note": (
                "Run cohort filtering unavailable; report is global catalog authority only."
                if cohort_keys is None
                else str(warning or LIVE_VIEW_MISSING_WARNING).strip()
            ),
            "cohort_source": cohort_source or "",
            "row_count": 0,
            "bucket_rows": [],
            "bucket_counts": {},
            "resolved_but_no_authority_family_rows": 0,
            "generic_or_coarse_label_rows": 0,
            "generic_or_coarse_label_tokens": 0,
            "authority_family_unknown_type_rows": 0,
            "authority_family_unknown_type_families": 0,
            "resolved_unknown_rows": 0,
            "plausible_missing_candidates_top": [],
            "generic_or_coarse_candidates_top": [],
            "unknown_type_families_top": [],
            "raw_authority_conflicts_top": [],
        }
    else:
        scoped_df = authority_df.copy()
        scoped_df["sample_id_key"] = scoped_df["sample_id"].map(_normalize_sample_id_key)
        scoped_df = scoped_df[scoped_df["sample_id_key"].isin(cohort_keys)].copy()
        run_scope = _authority_scope_payload(
            scope_name="run_cohort_authority",
            source_mode=str(source_mode or "unknown"),
            source_label="v_android_sample_family_type_authority",
            df=scoped_df.drop(columns=["sample_id_key"], errors="ignore"),
            note=f"Cohort source: {cohort_source}",
        )
        run_scope["cohort_source"] = cohort_source

    rendering_df = mismatch_df.copy()
    if not rendering_df.empty:
        rendering_df["diagnostic_bucket"] = rendering_df["mismatch_reason"].map(_taxonomy_split_reason_bucket)
    rendering_csv_path = diagnostics_dir / f"taxonomy_rendering_mismatches_{run_id}.csv"
    rendering_df.to_csv(rendering_csv_path, index=False)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=rendering_csv_path.name,
        csv_text=rendering_df.to_csv(index=False),
        global_latest_name="taxonomy_rendering_mismatches.latest.csv",
    )

    prediction_export_df = prediction_df.copy()
    if not prediction_export_df.empty:
        prediction_export_df["diagnostic_bucket"] = "model_prediction_error"
    model_err_csv_path = diagnostics_dir / f"taxonomy_model_prediction_errors_{run_id}.csv"
    prediction_export_df.to_csv(model_err_csv_path, index=False)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=model_err_csv_path.name,
        csv_text=prediction_export_df.to_csv(index=False),
        global_latest_name="taxonomy_model_prediction_errors.latest.csv",
    )

    gap_rows: list[dict[str, Any]] = []
    for scope_blob in (global_scope, run_scope):
        scope_name = str(scope_blob.get("scope", ""))
        for bucket_row in scope_blob.get("bucket_rows", []) or []:
            gap_rows.append(
                {
                    "scope": scope_name,
                    "summary_group": "authority_bucket",
                    "key": str(bucket_row.get("authority_bucket", "")),
                    "row_count": int(bucket_row.get("row_count", 0)),
                    "secondary_count": int(bucket_row.get("family_count", 0)),
                    "secondary_label": "family_count",
                }
            )
        gap_rows.extend(
            [
                {
                    "scope": scope_name,
                    "summary_group": "generic_or_coarse_label_issue",
                    "key": "generic_or_coarse_label",
                    "row_count": int(scope_blob.get("generic_or_coarse_label_rows", 0)),
                    "secondary_count": int(scope_blob.get("generic_or_coarse_label_tokens", 0)),
                    "secondary_label": "token_count",
                },
                {
                    "scope": scope_name,
                    "summary_group": "unknown_type_family_issue",
                    "key": "authority_family_unknown_type",
                    "row_count": int(scope_blob.get("authority_family_unknown_type_rows", 0)),
                    "secondary_count": int(scope_blob.get("authority_family_unknown_type_families", 0)),
                    "secondary_label": "family_count",
                },
            ]
        )
    gap_summary_df = pd.DataFrame(gap_rows)
    gap_csv_path = diagnostics_dir / f"taxonomy_authority_gap_summary_{run_id}.csv"
    gap_summary_df.to_csv(gap_csv_path, index=False)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=gap_csv_path.name,
        csv_text=gap_summary_df.to_csv(index=False),
        global_latest_name="taxonomy_authority_gap_summary.latest.csv",
    )

    rendering_counts = {
        "type_mapping_mismatch": int(summary.get("type_mismatch_count", 0) or 0),
        "type_label_missing": int(summary.get("type_missing_label_count", 0) or 0),
        "type_label_noncanonical": int(summary.get("type_noncanonical_count", 0) or 0),
        "label_family_mismatch": int(summary.get("family_label_mismatch_count", 0) or 0),
    }
    prediction_error_count = int(summary.get("prediction_error_count", 0) or 0)

    json_payload = {
        "run_id": run_id,
        "authority_scopes": {
            "global_authority_catalog": {
                k: v for k, v in global_scope.items() if not str(k).startswith("_")
            },
            "run_cohort_authority": {
                k: v for k, v in run_scope.items() if not str(k).startswith("_")
            },
        },
        "taxonomy_split": {
            "authority_gap": {
                "split_note": "Authority coverage / curation debt from the live authority view; separate this from policy-held generic/coarse token residue.",
                "csv_path": str(gap_csv_path),
            },
            "type_authority_vs_rendering_mismatch": {
                "counts": rendering_counts,
                "csv_path": str(rendering_csv_path),
            },
            "model_prediction_error": {
                "count": prediction_error_count,
                "csv_path": str(model_err_csv_path),
            },
            "generic_or_coarse_label_issue": {
                "global_row_count": int(global_scope.get("generic_or_coarse_label_rows", 0)),
                "run_row_count": int(run_scope.get("generic_or_coarse_label_rows", 0)),
            },
            "unknown_type_family_issue": {
                "global_row_count": int(global_scope.get("authority_family_unknown_type_rows", 0)),
                "run_row_count": int(run_scope.get("authority_family_unknown_type_rows", 0)),
            },
        },
        "source_mode": str(source_mode or "unknown"),
        "authority_warning": str(warning or "").strip(),
    }
    json_path = diagnostics_dir / f"taxonomy_authority_split_{run_id}.json"
    json_text = json.dumps(json_payload, indent=2, sort_keys=True)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        payload=json_payload,
        global_latest_name="taxonomy_authority_split.latest.json",
    )

    def _append_scope_block(lines: list[str], blob: dict[str, Any]) -> None:
        lines.extend(
            [
                f"### {blob.get('scope')}",
                "",
                f"- Scope: `{blob.get('scope')}`",
                f"- Source: `{blob.get('source')}`",
                f"- Source mode: `{blob.get('source_mode')}`",
                f"- Rows evaluated: `{blob.get('row_count')}`",
            ]
        )
        note = str(blob.get("note", "") or "").strip()
        if note:
            lines.append(f"- Note: {note}")
        if not bool(blob.get("available", False)):
            lines.extend(["", "_Unavailable for this run._", ""])
            return
        lines.extend(["", "| authority_bucket | row_count | family_count |", "|---|---:|---:|"])
        for row in blob.get("bucket_rows", []) or []:
            lines.append(
                f"| `{row.get('authority_bucket', '')}` | {int(row.get('row_count', 0))} | {int(row.get('family_count', 0))} |"
            )
        lines.extend(["", f"- Generic/coarse label issue rows: **{int(blob.get('generic_or_coarse_label_rows', 0))}**", f"- Unknown-type family issue rows: **{int(blob.get('authority_family_unknown_type_rows', 0))}**", ""])

    md_lines = [
        "# Taxonomy Authority Split",
        "",
        f"Run ID: `{run_id}`",
        "",
        "This report separates authority coverage / curation debt from policy-held generic/coarse token residue, label-rendering mismatches, and real model prediction errors.",
        "",
        "## Scope",
        "",
    ]
    _append_scope_block(md_lines, global_scope)
    _append_scope_block(md_lines, run_scope)
    md_lines.extend(
        [
            "## Split Categories",
            "",
            "### 1. Authority gap",
            "",
            "- Uses the live authority view and separates true unresolved authority-family rows from policy-held generic/coarse token residue.",
            f"- Summary CSV: `{gap_csv_path}`",
            "",
            "### 2. Type authority vs rendering mismatch",
            "",
            f"- `type_mapping_mismatch`: **{rendering_counts['type_mapping_mismatch']}**",
            f"- `type_label_missing`: **{rendering_counts['type_label_missing']}**",
            f"- `type_label_noncanonical`: **{rendering_counts['type_label_noncanonical']}**",
            f"- `label_family_mismatch`: **{rendering_counts['label_family_mismatch']}**",
            f"- CSV: `{rendering_csv_path}`",
            "- These are rendering/taxonomy issues, not model-family errors.",
            "",
            "### 3. Model prediction error",
            "",
            f"- Count: **{prediction_error_count}**",
            f"- CSV: `{model_err_csv_path}`",
            "- These rows remain separate from type/rendering mismatches.",
            "",
            "### 4. Generic/coarse label issue",
            "",
            f"- Global rows: **{int(global_scope.get('generic_or_coarse_label_rows', 0))}**",
            f"- Run-cohort rows: **{int(run_scope.get('generic_or_coarse_label_rows', 0))}**",
            "- Examples: `trojan`, `adware`, `spyware`, `banker trojan`, `fraud financial apps`.",
            "",
            "### 5. Unknown-type family issue",
            "",
            f"- Global rows: **{int(global_scope.get('authority_family_unknown_type_rows', 0))}**",
            f"- Run-cohort rows: **{int(run_scope.get('authority_family_unknown_type_rows', 0))}**",
            "- These are type-curation candidates, not model errors.",
            "",
        ]
    )

    if global_scope.get("raw_authority_conflicts_top"):
        md_lines.extend(["## Top Raw-vs-Authority Conflicts", "", "| family_slug | type_slug | raw_primary | raw_subtype | row_count |", "|---|---|---|---|---:|"])
        for row in global_scope["raw_authority_conflicts_top"][:10]:
            md_lines.append(
                f"| `{row.get('family_slug', '')}` | `{row.get('type_slug', '')}` | `{row.get('raw_classification_primary', '')}` | `{row.get('raw_classification_subtype', '')}` | {int(row.get('row_count', 0))} |"
            )
        md_lines.append("")

    if global_scope.get("plausible_missing_candidates_top"):
        md_lines.extend(["## Top True Missing Authority-Family Candidates", "", "| resolved_family_lc | row_count | years_present | priority |", "|---|---:|---:|---:|"])
        for row in global_scope["plausible_missing_candidates_top"][:10]:
            md_lines.append(
                f"| `{row.get('resolved_family_lc', '')}` | {int(row.get('row_count', 0))} | {int(row.get('years_present', 0))} | {int(row.get('priority_family_curation_flag', 0))} |"
            )
        md_lines.append("")

    if global_scope.get("generic_or_coarse_candidates_top"):
        md_lines.extend(["## Top Policy-Held Generic/Coarse Token Residue", "", "| resolved_family_lc | row_count | years_present | priority |", "|---|---:|---:|---:|"])
        for row in global_scope["generic_or_coarse_candidates_top"][:10]:
            md_lines.append(
                f"| `{row.get('resolved_family_lc', '')}` | {int(row.get('row_count', 0))} | {int(row.get('years_present', 0))} | {int(row.get('priority_family_curation_flag', 0))} |"
            )
        md_lines.append("")

    if global_scope.get("unknown_type_families_top"):
        md_lines.extend(["## Top Unknown-Type Authority Families", "", "| family_slug | family_name | row_count | active_years | priority |", "|---|---|---:|---:|---:|"])
        for row in global_scope["unknown_type_families_top"][:10]:
            md_lines.append(
                f"| `{row.get('family_slug', '')}` | `{row.get('family_name', '')}` | {int(row.get('row_count', 0))} | {int(row.get('active_years', 0))} | {int(row.get('priority_type_curation_flag', 0))} |"
            )
        md_lines.append("")

    md_path = diagnostics_dir / f"taxonomy_authority_split_{run_id}.md"
    md_text = "\n".join(md_lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="taxonomy_authority_split.latest.md",
    )

    return md_path, json_path, rendering_csv_path, model_err_csv_path, gap_csv_path


def write_taxonomy_type_authority_reports(
    diagnostics_dir: Path,
    run_id: str,
) -> tuple[Path | None, Path | None]:
    """Emit ``taxonomy_type_authority_review.{md,csv}`` with policy + counts + examples."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    summary = _read_taxonomy_summary(diagnostics_dir, run_id)
    summary_present = bool(summary)

    mismatch_path = oh.resolve_taxonomy_consistency_mismatches_path(diagnostics_dir, run_id)
    if not mismatch_path.is_file():
        mismatch_path = None

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

    pred_path = oh.resolve_prediction_errors_path(diagnostics_dir, run_id)
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
    "write_taxonomy_authority_split_reports",
    "write_taxonomy_type_authority_reports",
]
