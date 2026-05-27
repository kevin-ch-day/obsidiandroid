"""Android authority drift diagnostics grouped by family, type, and source batch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config


_GENERIC_FAMILY_TOKENS = {"", "unknown", "generic", "unclassified", "unlabeled"}
_GENERIC_CANONICAL_TOKENS = {"", "unknown", "other", "unmapped", "none", "null"}
_WEAK_LABEL_KINDS = {"filename", "hash_like", "opaque_string", "unclassified"}


def _norm_series(frame: pd.DataFrame, column: str, *, lower: bool = False) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    series = frame[column].fillna("").astype(str).str.strip()
    if lower:
        series = series.str.lower()
    return series


def _build_issue_frame(samples_df: pd.DataFrame) -> pd.DataFrame:
    frame = samples_df.copy()
    lane = _norm_series(frame, "analysis_lane", lower=True)
    target = _norm_series(frame, "payload_target_platform", lower=True)
    label_kind = _norm_series(frame, "sample_label_kind", lower=True)
    vt_token = _norm_series(frame, "vt_family_token")
    family_raw = _norm_series(frame, "family_label_raw", lower=True)
    family_canonical = _norm_series(frame, "family_canonical", lower=True)

    frame["issue_non_android_lane"] = lane != "android_artifact"
    frame["issue_non_android_target"] = (target != "") & (target != "android")
    frame["issue_weak_label"] = label_kind.isin(_WEAK_LABEL_KINDS) & ~family_canonical.isin(
        _GENERIC_CANONICAL_TOKENS
    )
    frame["issue_blank_family_with_token"] = (vt_token != "") & family_raw.isin(
        _GENERIC_FAMILY_TOKENS
    )
    frame["issue_family_conflict"] = (
        ~family_raw.isin(_GENERIC_FAMILY_TOKENS)
        & ~family_canonical.isin(_GENERIC_CANONICAL_TOKENS)
        & (family_raw != family_canonical)
    )
    issue_cols = [
        "issue_non_android_lane",
        "issue_non_android_target",
        "issue_weak_label",
        "issue_blank_family_with_token",
        "issue_family_conflict",
    ]
    frame["issue_rows"] = frame[issue_cols].any(axis=1)
    return frame


def _group_issue_frame(
    issue_frame: pd.DataFrame,
    *,
    scope: str,
    key_column: str,
    top_n: int = 25,
) -> pd.DataFrame:
    if issue_frame.empty or key_column not in issue_frame.columns:
        return pd.DataFrame()

    scoped = issue_frame[issue_frame["issue_rows"]].copy()
    if scoped.empty:
        return pd.DataFrame()

    scoped[key_column] = scoped[key_column].fillna("").astype(str).str.strip().replace("", "<blank>")
    grouped = (
        scoped.groupby(key_column, dropna=False)
        .agg(
            rows=("issue_rows", "size"),
            non_android_lane_rows=("issue_non_android_lane", "sum"),
            non_android_payload_target_rows=("issue_non_android_target", "sum"),
            weak_label_rows=("issue_weak_label", "sum"),
            blank_family_raw_with_vt_token_rows=("issue_blank_family_with_token", "sum"),
            raw_family_vs_canonical_conflict_rows=("issue_family_conflict", "sum"),
        )
        .reset_index()
    )
    grouped["issue_events"] = (
        grouped["non_android_lane_rows"]
        + grouped["non_android_payload_target_rows"]
        + grouped["weak_label_rows"]
        + grouped["blank_family_raw_with_vt_token_rows"]
        + grouped["raw_family_vs_canonical_conflict_rows"]
    )
    grouped["scope"] = scope
    grouped = grouped.rename(columns={key_column: "group_value"})
    grouped = grouped.sort_values(
        by=["issue_events", "rows", "group_value"],
        ascending=[False, False, True],
        kind="stable",
    )
    return grouped.head(top_n)


def build_android_authority_drift_payload(
    samples_df: pd.DataFrame,
    *,
    top_n: int = 25,
) -> dict[str, Any]:
    """Build grouped Android authority drift summaries from the prepared cohort."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return {
            "total_rows": 0,
            "issue_rows": 0,
            "grouped_rows": [],
        }

    issue_frame = _build_issue_frame(samples_df)
    grouped_frames = [
        _group_issue_frame(issue_frame, scope="family_canonical", key_column="family_canonical", top_n=top_n),
        _group_issue_frame(issue_frame, scope="type_slug", key_column="type_slug", top_n=top_n),
        _group_issue_frame(issue_frame, scope="source_batch_label", key_column="source_batch_label", top_n=top_n),
    ]
    non_empty_grouped_frames = [frame for frame in grouped_frames if not frame.empty]
    if non_empty_grouped_frames:
        grouped = pd.concat(non_empty_grouped_frames, ignore_index=True)
    else:
        grouped = pd.DataFrame()
    return {
        "total_rows": int(len(samples_df)),
        "issue_rows": int(issue_frame["issue_rows"].sum()),
        "grouped_rows": grouped.to_dict(orient="records") if not grouped.empty else [],
    }


def export_android_authority_drift_reports(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame,
) -> list[str]:
    """Write grouped Android authority drift diagnostics under ``diagnostics_dir``."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_android_authority_drift_payload(samples_df)

    json_path = diagnostics_dir / f"android_authority_drift_{run_id}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    grouped = pd.DataFrame(payload.get("grouped_rows") or [])
    csv_path = diagnostics_dir / f"android_authority_drift_groups_{run_id}.csv"
    verbose = bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True))
    if not grouped.empty or verbose:
        grouped.to_csv(csv_path, index=False)
    elif csv_path.exists():
        csv_path.unlink()

    md_lines = [
        "# Android Authority Drift",
        "",
        f"- run_id: `{run_id}`",
        f"- total_rows: {int(payload.get('total_rows', 0))}",
        f"- issue_rows: {int(payload.get('issue_rows', 0))}",
        "",
    ]
    if grouped.empty:
        md_lines.extend(["No authority drift groups detected.", ""])
    else:
        for scope in ("family_canonical", "type_slug", "source_batch_label"):
            scoped = grouped[grouped["scope"] == scope].copy()
            if scoped.empty:
                continue
            md_lines.extend([f"## {scope}", ""])
            for _, row in scoped.iterrows():
                md_lines.append(
                    f"- `{row['group_value']}`: rows={int(row['rows'])}, "
                    f"issue_events={int(row['issue_events'])}, "
                    f"weak_label_rows={int(row['weak_label_rows'])}, "
                    f"family_conflicts={int(row['raw_family_vs_canonical_conflict_rows'])}"
                )
            md_lines.append("")

    md_path = diagnostics_dir / f"android_authority_drift_{run_id}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    outputs = [str(json_path), str(md_path)]
    if csv_path.exists():
        outputs.insert(1, str(csv_path))
    return outputs
