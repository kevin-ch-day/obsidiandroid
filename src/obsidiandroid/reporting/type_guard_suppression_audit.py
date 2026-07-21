"""Audit type-guard family suppressions from prediction_errors artifacts.

Read-only. Distinguishes post-model governance demotions from holdout
confusion-matrix errors. Does not query production databases.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

AUDIT_VERSION = "1.0.0"
TYPE_GUARD_TAG = "type_guard_family_suppressed"


def _norm_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def load_type_guard_rows(prediction_errors: pd.DataFrame) -> pd.DataFrame:
    """Return rows demoted by the type-consistent family guard."""
    if prediction_errors.empty or "override_tag" not in prediction_errors.columns:
        return pd.DataFrame()
    frame = prediction_errors.copy()
    mask = frame["override_tag"].fillna("").astype(str).str.strip().eq(TYPE_GUARD_TAG)
    return frame.loc[mask].copy()


def summarize_type_guard_suppressions(guard_rows: pd.DataFrame) -> dict[str, Any]:
    """Build aggregate audit facts for type-guard demotions."""
    if guard_rows.empty:
        return {
            "type_guard_suppressed_count": 0,
            "raw_model_already_incorrect_count": 0,
            "raw_model_would_have_matched_family_count": 0,
            "all_demotions_were_already_incorrect": True,
            "by_expected_type": {},
            "top_expected_to_raw_pairs": [],
            "top_expected_to_postguard_pairs": [],
        }

    work = guard_rows.copy()
    expected = work.get("family_canonical_expected", pd.Series(dtype=str)).fillna("").astype(str)
    raw = work.get("raw_model_predicted_family", pd.Series(dtype=str))
    if raw.isna().all() and "raw_predicted_family" in work.columns:
        raw = work["raw_predicted_family"]
    raw = raw.fillna("").astype(str)
    post = work.get("predicted_family", pd.Series(dtype=str)).fillna("").astype(str)
    type_slug = work.get("type_slug_expected", pd.Series(dtype=str)).fillna("").astype(str)

    raw_match = [_norm_family(a) == _norm_family(b) and _norm_family(a) != "" for a, b in zip(expected, raw)]
    raw_correct = int(sum(raw_match))
    raw_incorrect = int(len(work) - raw_correct)

    by_type = type_slug.value_counts().to_dict()
    pair_raw = (
        pd.DataFrame({"expected": expected, "raw": raw})
        .value_counts()
        .reset_index(name="count")
        .head(15)
    )
    pair_post = (
        pd.DataFrame({"expected": expected, "post_guard": post})
        .value_counts()
        .reset_index(name="count")
        .head(15)
    )
    return {
        "type_guard_suppressed_count": int(len(work)),
        "raw_model_already_incorrect_count": raw_incorrect,
        "raw_model_would_have_matched_family_count": raw_correct,
        "all_demotions_were_already_incorrect": raw_correct == 0,
        "by_expected_type": {str(k): int(v) for k, v in by_type.items()},
        "top_expected_to_raw_pairs": [
            {
                "expected_family": str(row.expected),
                "raw_model_predicted_family": str(row.raw),
                "count": int(row.count),
            }
            for row in pair_raw.itertuples(index=False)
        ],
        "top_expected_to_postguard_pairs": [
            {
                "expected_family": str(row.expected),
                "post_guard_predicted_family": str(row.post_guard),
                "count": int(row.count),
            }
            for row in pair_post.itertuples(index=False)
        ],
    }


def compose_type_guard_suppression_audit(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Write type-guard suppression audit tables + markdown."""
    run_root = Path(run_root)
    diagnostics = run_root / "diagnostics"
    errors_path = diagnostics / f"prediction_errors_{run_id}.csv"
    if not errors_path.is_file():
        raise FileNotFoundError(f"prediction_errors missing: {errors_path}")
    errors = pd.read_csv(errors_path)
    guard_rows = load_type_guard_rows(errors)
    summary = summarize_type_guard_suppressions(guard_rows)
    run_status = detect_source_run_status(run_root)

    out_dir = Path(output_dir) if output_dir else diagnostics / "type_guard_suppression_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    detail_path = out_dir / f"type_guard_suppressions_{run_id}.csv"
    guard_rows.to_csv(detail_path, index=False)
    guard_rows.to_csv(out_dir / "type_guard_suppressions.latest.csv", index=False)

    summary_path = out_dir / f"type_guard_suppression_summary_{run_id}.json"
    payload = {
        "audit_version": AUDIT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": resolve_git_commit(repo_root),
        "run_id": run_id,
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
        "source_prediction_errors": str(errors_path),
        "source_prediction_errors_sha256": sha256_file(errors_path),
        "interpretation": {
            "type_guard_is_post_model_governance": True,
            "holdout_metrics_use_raw_model_predictions": True,
            "guard_must_not_be_counted_as_accuracy_gain": True,
            "raw_model_already_incorrect_on_all_demotions": bool(
                summary["all_demotions_were_already_incorrect"]
            ),
        },
        **summary,
    }
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_lines = [
        f"# Type-guard suppression audit (`{run_id}`)",
        "",
        f"- Report status: **{run_status['report_status']}**",
        f"- Suppressions (`{TYPE_GUARD_TAG}`): **{summary['type_guard_suppressed_count']}**",
        f"- Raw model already incorrect: **{summary['raw_model_already_incorrect_count']}**",
        f"- Raw model would have matched expected family: **{summary['raw_model_would_have_matched_family_count']}**",
        "",
        "The type guard is a **post-model governance** rule. Held-out family metrics must "
        "remain on raw model predictions. These demotions must not be presented as accuracy gains.",
        "",
        "## By expected type",
        "",
    ]
    if summary["by_expected_type"]:
        md_lines.extend(["| type_slug | count |", "|---|---:|"])
        for type_slug, count in sorted(
            summary["by_expected_type"].items(), key=lambda item: (-item[1], item[0])
        ):
            md_lines.append(f"| {type_slug} | {count} |")
    else:
        md_lines.append("No type-guard suppressions in this run.")
    md_lines.extend(["", "## Top expected → raw-model pairs", ""])
    if summary["top_expected_to_raw_pairs"]:
        md_lines.extend(["| expected | raw model | n |", "|---|---|---:|"])
        for row in summary["top_expected_to_raw_pairs"][:12]:
            md_lines.append(
                f"| {row['expected_family']} | {row['raw_model_predicted_family']} | {row['count']} |"
            )
    md_lines.extend(["", "## Top expected → post-guard pairs", ""])
    if summary["top_expected_to_postguard_pairs"]:
        md_lines.extend(["| expected | post-guard | n |", "|---|---|---:|"])
        for row in summary["top_expected_to_postguard_pairs"][:12]:
            md_lines.append(
                f"| {row['expected_family']} | {row['post_guard_predicted_family']} | {row['count']} |"
            )
    md_lines.append("")
    report_path = out_dir / f"type_guard_suppression_audit_{run_id}.md"
    report_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    (out_dir / "type_guard_suppression_audit.latest.md").write_text(
        "\n".join(md_lines) + "\n", encoding="utf-8"
    )

    payload["detail_csv"] = str(detail_path)
    payload["report_markdown"] = str(report_path)
    payload["output_dir"] = str(out_dir)
    payload["detail_sha256"] = sha256_file(detail_path)
    manifest_path = out_dir / f"type_guard_suppression_audit_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


__all__ = [
    "AUDIT_VERSION",
    "TYPE_GUARD_TAG",
    "compose_type_guard_suppression_audit",
    "load_type_guard_rows",
    "summarize_type_guard_suppressions",
]
