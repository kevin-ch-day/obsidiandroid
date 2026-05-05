"""Explain why label cohort sample_ids are missing from the ML feature matrix.

Read-only diagnostics: does not change pipeline joins or training behavior.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from obsidiandroid.database.db_config import DB_NAME, PERMISSION_INTEL_DB_NAME

# Tables we probe on the primary DB (optional ones may be absent in some deployments).
OPTIONAL_PRIMARY_TABLES = (
    "virustotal_sample_state",
    "virustotal_sample_androguard_current",
)

_RECOMMENDED_FIX_BY_REASON: dict[str, str] = {
    "not_in_catalog": "Investigate why label sample_id is missing from malware_sample_catalog (stale labels export or wrong run).",
    "no_vendor_verdicts": "Backfill or sync `virustotal_sample_vendor_engine_verdicts` (wide matrix / AV path cannot represent these rows).",
    "no_scan_summary": "Backfill or sync `virustotal_sample_scan_summary` in the primary DB.",
    "no_signal_current": "Backfill or sync `virustotal_sample_signal_current` in the primary DB.",
    "no_androguard_current": "Backfill or sync `virustotal_sample_androguard_current` (if that table is part of your feature contract).",
    "no_pi_permissions": "Ingest permission observations into Permission Intel `android_permission_obs_sample` (inner join drops rows without PI rows).",
    "unknown_feature_builder_drop": "Trace feature_matrix / vendor parser gates: DB rows exist but Python-stage filters or inner joins removed the sample.",
}


def _recommended_next_fix(reason_counts: dict[str, int]) -> str:
    if not reason_counts:
        return "No alignment gap in this export; no DB action required for unmatched labels."
    top_reason = max(reason_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return _RECOMMENDED_FIX_BY_REASON.get(
        top_reason,
        "Inspect per-row flags in alignment_gap_diagnostics.csv and the feature_matrix stage.",
    )


def _primary(table: str) -> str:
    return f"`{DB_NAME}`.`{table}`"


def _permission_intel(table: str) -> str:
    return f"`{PERMISSION_INTEL_DB_NAME}`.`{table}`"


def resolve_diagnostics_dir(run_root: Path) -> Path:
    """Return ``.../diagnostics`` under a pipeline run root."""
    return Path(run_root) / "diagnostics"


def load_unmatched_label_sample_ids(csv_path: Path) -> list[int]:
    """Load integer sample IDs from ``unmatched_label_ids.csv``."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing unmatched label export: {path}")
    df = pd.read_csv(path)
    if df.empty:
        return []
    if "sample_id" not in df.columns:
        raise ValueError(f"Expected column 'sample_id' in {path}")
    return [int(x) for x in df["sample_id"].tolist()]


def _chunked(ids: list[int], size: int) -> Iterable[list[int]]:
    for i in range(0, len(ids), size):
        yield ids[i : i + size]


def list_existing_tables(
    *,
    execute_query: Callable[..., Any],
    schema: str,
    candidates: tuple[str, ...],
) -> set[str]:
    """Return which of ``candidates`` exist in ``schema`` (information_schema)."""
    if not candidates:
        return set()
    placeholders = ", ".join(["%s"] * len(candidates))
    sql = (
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN (" + placeholders + ")"
    )
    params = (schema,) + tuple(candidates)
    cols, rows = execute_query(sql, params=params, fetch=True, return_columns=True)
    if not rows:
        return set()
    idx = cols.index("TABLE_NAME") if "TABLE_NAME" in cols else 0
    return {str(r[idx]) for r in rows}


def _batch_ids_query(
    *,
    execute_query: Callable[..., Any],
    sql_template: str,
    ids: list[int],
    chunk_size: int,
) -> pd.DataFrame:
    """Run ``sql_template`` with ``WHERE sample_id IN ({placeholders})`` per chunk."""
    frames: list[pd.DataFrame] = []
    for chunk in _chunked(ids, chunk_size):
        if not chunk:
            continue
        ph = ", ".join(["%s"] * len(chunk))
        sql = sql_template.format(placeholders=ph)
        cols, rows = execute_query(sql, params=tuple(chunk), fetch=True, return_columns=True)
        if rows:
            frames.append(pd.DataFrame(rows, columns=cols))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def db_execute_query_default(*args: Any, **kwargs: Any):
    from obsidiandroid.database import db_engine

    return db_engine.execute_query(*args, **kwargs)


def db_execute_permission_query_default(*args: Any, **kwargs: Any):
    from obsidiandroid.database import db_engine

    return db_engine.execute_permission_query(*args, **kwargs)


def collect_alignment_gap_detail_frame(
    sample_ids: list[int],
    *,
    execute_query: Callable[..., Any] | None = None,
    execute_permission_query: Callable[..., Any] | None = None,
    chunk_size: int = 400,
) -> pd.DataFrame:
    """Fetch per-sample flags from primary + Permission Intel databases."""
    execute_query = execute_query or db_execute_query_default
    execute_permission_query = execute_permission_query or db_execute_permission_query_default
    if not sample_ids:
        return pd.DataFrame()

    optional_existing = list_existing_tables(
        execute_query=execute_query,
        schema=DB_NAME,
        candidates=OPTIONAL_PRIMARY_TABLES,
    )
    has_state_tbl = "virustotal_sample_state" in optional_existing
    has_andro_tbl = "virustotal_sample_androguard_current" in optional_existing

    # --- malware_sample_catalog ---
    cat_sql = (
        "SELECT sample_id, sha256, family_label, classification_primary, classification_subtype, "
        "android_package_name, android_permission_count "
        f"FROM {_primary('malware_sample_catalog')} WHERE sample_id IN ({{placeholders}})"
    )
    catalog_df = _batch_ids_query(
        execute_query=execute_query, sql_template=cat_sql, ids=sample_ids, chunk_size=chunk_size
    )
    if catalog_df.empty:
        catalog_df = pd.DataFrame(
            {
                "sample_id": sample_ids,
                "sha256": pd.NA,
                "family_label": pd.NA,
                "classification_primary": pd.NA,
                "classification_subtype": pd.NA,
                "android_package_name": pd.NA,
                "android_permission_count": pd.NA,
            }
        )
    catalog_df = catalog_df.drop_duplicates(subset=["sample_id"], keep="first")
    catalog_ids = set(int(x) for x in catalog_df["sample_id"].tolist())
    id_frame = pd.DataFrame({"sample_id": sample_ids})
    merged = id_frame.merge(catalog_df, on="sample_id", how="left")
    merged["in_catalog"] = merged["sample_id"].isin(catalog_ids).astype(int)

    # --- vendor verdict row counts ---
    verdict_sql = (
        f"SELECT sample_id, COUNT(*) AS verdict_row_count "
        f"FROM {_primary('virustotal_sample_vendor_engine_verdicts')} "
        "WHERE sample_id IN ({placeholders}) GROUP BY sample_id"
    )
    verdict_df = _batch_ids_query(
        execute_query=execute_query, sql_template=verdict_sql, ids=sample_ids, chunk_size=chunk_size
    )

    def _presence_batches(table: str, alias: str) -> pd.DataFrame:
        sql = (
            f"SELECT DISTINCT sample_id AS sample_id, 1 AS {alias} "
            f"FROM {_primary(table)} WHERE sample_id IN ({{placeholders}})"
        )
        return _batch_ids_query(
            execute_query=execute_query, sql_template=sql, ids=sample_ids, chunk_size=chunk_size
        )

    scan_df = _presence_batches("virustotal_sample_scan_summary", "has_scan_summary")
    signal_df = _presence_batches("virustotal_sample_signal_current", "has_signal_current")

    state_df = pd.DataFrame()
    if has_state_tbl:
        state_df = _presence_batches("virustotal_sample_state", "has_vt_state")

    andro_df = pd.DataFrame()
    if has_andro_tbl:
        andro_df = _presence_batches("virustotal_sample_androguard_current", "has_androguard_current")

    for df_extra in (verdict_df, scan_df, signal_df, state_df, andro_df):
        if df_extra is not None and not df_extra.empty:
            merged = merged.merge(df_extra, on="sample_id", how="left")

    if "verdict_row_count" not in merged.columns:
        merged["verdict_row_count"] = 0
    merged["verdict_row_count"] = pd.to_numeric(merged["verdict_row_count"], errors="coerce").fillna(0).astype(int)
    merged["has_vendor_verdicts"] = (merged["verdict_row_count"] > 0).astype(int)

    for col in ("has_scan_summary", "has_signal_current", "has_vt_state", "has_androguard_current"):
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)

    # --- Permission Intel: observation counts ---
    pi_sql = (
        "SELECT sample_id, "
        "COUNT(*) AS pi_permission_count, "
        "COUNT(DISTINCT classification) AS pi_classification_count "
        f"FROM {_permission_intel('android_permission_obs_sample')} "
        "WHERE sample_id IN ({placeholders}) GROUP BY sample_id"
    )
    pi_df = _batch_ids_query(
        execute_query=execute_permission_query,
        sql_template=pi_sql,
        ids=sample_ids,
        chunk_size=chunk_size,
    )
    if not pi_df.empty:
        merged = merged.merge(pi_df, on="sample_id", how="left")
    if "pi_permission_count" not in merged.columns:
        merged["pi_permission_count"] = 0
    else:
        merged["pi_permission_count"] = (
            pd.to_numeric(merged["pi_permission_count"], errors="coerce").fillna(0).astype(int)
        )
    if "pi_classification_count" not in merged.columns:
        merged["pi_classification_count"] = 0
    else:
        merged["pi_classification_count"] = (
            pd.to_numeric(merged["pi_classification_count"], errors="coerce").fillna(0).astype(int)
        )
    merged["has_pi_permissions"] = (merged["pi_permission_count"] > 0).astype(int)

    merged["optional_table_vt_state"] = int(has_state_tbl)
    merged["optional_table_androguard_current"] = int(has_andro_tbl)

    merged["likely_missing_reason"] = merged.apply(
        lambda row: infer_likely_missing_reason(row, androguard_table_tracked=has_andro_tbl),
        axis=1,
    )

    preferred_cols = [
        "sample_id",
        "sha256",
        "family_label",
        "classification_primary",
        "classification_subtype",
        "android_package_name",
        "android_permission_count",
        "has_vt_state",
        "has_scan_summary",
        "has_signal_current",
        "has_androguard_current",
        "has_vendor_verdicts",
        "verdict_row_count",
        "has_pi_permissions",
        "pi_permission_count",
        "pi_classification_count",
        "in_catalog",
        "likely_missing_reason",
        "optional_table_vt_state",
        "optional_table_androguard_current",
    ]
    tail = [c for c in merged.columns if c not in preferred_cols]
    merged = merged[[c for c in preferred_cols if c in merged.columns] + tail]
    return merged


def infer_likely_missing_reason(row: pd.Series, *, androguard_table_tracked: bool) -> str:
    """Pick a single human-readable reason using a fixed priority chain."""
    if int(row.get("in_catalog", 0)) == 0:
        return "not_in_catalog"
    if int(row.get("has_vendor_verdicts", 0)) == 0:
        return "no_vendor_verdicts"
    if int(row.get("has_scan_summary", 0)) == 0:
        return "no_scan_summary"
    if int(row.get("has_signal_current", 0)) == 0:
        return "no_signal_current"
    if androguard_table_tracked and int(row.get("has_androguard_current", 0)) == 0:
        return "no_androguard_current"
    if int(row.get("has_pi_permissions", 0)) == 0:
        return "no_pi_permissions"
    return "unknown_feature_builder_drop"


def build_alignment_gap_summary(detail_df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate counts, optional table metadata, and top family/type slices."""
    total = int(len(detail_df))
    if total == 0:
        return {
            "total_unmatched_labels": 0,
            "missing_vendor_verdicts": 0,
            "missing_scan_summary": 0,
            "missing_signal_current": 0,
            "missing_androguard_current": 0,
            "missing_pi_permissions": 0,
            "missing_any_vt_current": 0,
            "reason_counts": {},
            "recommended_next_fix": _recommended_next_fix({}),
            "top_families_affected": [],
            "top_types_affected": [],
            "optional_tables": {},
        }

    reasons = detail_df["likely_missing_reason"].tolist()
    reason_counts = dict(Counter(reasons))

    missing_verdicts = int((detail_df["has_vendor_verdicts"] == 0).sum())
    missing_scan = int((detail_df["has_scan_summary"] == 0).sum())
    missing_signal = int((detail_df["has_signal_current"] == 0).sum())
    andro_tracked = False
    if "optional_table_androguard_current" in detail_df.columns and len(detail_df) > 0:
        andro_tracked = bool(int(detail_df["optional_table_androguard_current"].iloc[0]))
    if andro_tracked and "has_androguard_current" in detail_df.columns:
        missing_andro = int((detail_df["has_androguard_current"] == 0).sum())
    else:
        missing_andro = 0
    missing_pi = int((detail_df["has_pi_permissions"] == 0).sum())
    missing_any_vt_current = int(
        ((detail_df["has_scan_summary"] == 0) | (detail_df["has_signal_current"] == 0)).sum()
    )

    fam_col = detail_df["family_label"].fillna("").astype(str).str.strip()
    fam_counts = fam_col[fam_col != ""].value_counts().head(15)
    top_families = [{"family": str(k), "count": int(v)} for k, v in fam_counts.items()]

    type_col = detail_df["classification_primary"].fillna("").astype(str).str.strip()
    type_counts = type_col[type_col != ""].value_counts().head(15)
    top_types = [{"classification_primary": str(k), "count": int(v)} for k, v in type_counts.items()]

    optional_tables = {}
    if "optional_table_vt_state" in detail_df.columns:
        optional_tables["virustotal_sample_state_deployed"] = bool(
            int(detail_df["optional_table_vt_state"].iloc[0])
        )
    if "optional_table_androguard_current" in detail_df.columns:
        optional_tables["virustotal_sample_androguard_current_deployed"] = bool(
            int(detail_df["optional_table_androguard_current"].iloc[0])
        )

    return {
        "total_unmatched_labels": total,
        "missing_vendor_verdicts": missing_verdicts,
        "missing_scan_summary": missing_scan,
        "missing_signal_current": missing_signal,
        "missing_androguard_current": missing_andro,
        "missing_pi_permissions": missing_pi,
        "missing_any_vt_current": missing_any_vt_current,
        "reason_counts": reason_counts,
        "recommended_next_fix": _recommended_next_fix(reason_counts),
        "top_families_affected": top_families,
        "top_types_affected": top_types,
        "optional_tables": optional_tables,
    }


def write_alignment_gap_artifacts(
    diagnostics_dir: Path,
    detail_df: pd.DataFrame,
    summary: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """Write CSV, JSON, and Markdown summaries."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    csv_path = diagnostics_dir / "alignment_gap_diagnostics.csv"
    json_path = diagnostics_dir / "alignment_gap_summary.json"
    md_path = diagnostics_dir / "alignment_gap_summary.md"

    detail_df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown_summary(summary), encoding="utf-8")
    return csv_path, json_path, md_path


def _render_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Alignment gap diagnostics",
        "",
        "Explains label sample_ids that did not appear in the feature matrix row set "
        "(read-only; pipeline joins unchanged).",
        "",
        "## Totals",
        "",
        f"- **Unmatched label rows diagnosed:** {summary.get('total_unmatched_labels', 0)}",
        f"- **Missing vendor verdict rows:** {summary.get('missing_vendor_verdicts', 0)}",
        f"- **Missing VT scan summary:** {summary.get('missing_scan_summary', 0)}",
        f"- **Missing VT signal_current:** {summary.get('missing_signal_current', 0)}",
        f"- **Missing VT androguard_current** (if table deployed): {summary.get('missing_androguard_current', 0)}",
        f"- **Missing Permission Intel observations:** {summary.get('missing_pi_permissions', 0)}",
        f"- **Missing any VT current slice (scan or signal):** {summary.get('missing_any_vt_current', 0)}",
        "",
        "## `likely_missing_reason` counts",
        "",
    ]
    for reason, count in sorted(summary.get("reason_counts", {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{reason}`: **{count}**")
    lines.extend(["", "## Top families (from catalog)", ""])
    for row in summary.get("top_families_affected", [])[:10]:
        lines.append(f"- {row.get('family')}: {row.get('count')}")
    lines.extend(["", "## Top classification_primary (catalog)", ""])
    for row in summary.get("top_types_affected", [])[:10]:
        lines.append(f"- {row.get('classification_primary')}: {row.get('count')}")
    opt = summary.get("optional_tables") or {}
    if opt:
        lines.extend(["", "## Optional primary tables", ""])
        for k, v in opt.items():
            lines.append(f"- `{k}`: {v}")
    rec = summary.get("recommended_next_fix")
    if rec:
        lines.extend(["", "## Recommended next fix", "", str(rec), ""])
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- **`no_vendor_verdicts`**: no rows in `virustotal_sample_vendor_engine_verdicts` "
            "(AV / binary matrix cannot represent the sample).",
            "- **`no_pi_permissions`**: no rows in Permission Intel `android_permission_obs_sample` "
            "(permission feature join drops the sample).",
            "- **`unknown_feature_builder_drop`**: raw DB slices look present; loss is likely from "
            "Python-stage gates (parser/top‑k/vendor filters) or inner joins inside feature builders.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run_alignment_gap_diagnosis(
    run_root: Path,
    *,
    execute_query: Callable[..., Any] | None = None,
    execute_permission_query: Callable[..., Any] | None = None,
    chunk_size: int = 400,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load unmatched IDs for ``run_root`` and write diagnostic artifacts."""
    run_root = Path(run_root)
    diag = resolve_diagnostics_dir(run_root)
    unmatched_path = diag / "unmatched_label_ids.csv"
    ids = load_unmatched_label_sample_ids(unmatched_path)
    eq = execute_query or db_execute_query_default
    ep = execute_permission_query or db_execute_permission_query_default
    detail = collect_alignment_gap_detail_frame(
        ids, execute_query=eq, execute_permission_query=ep, chunk_size=chunk_size
    )
    summary = build_alignment_gap_summary(detail)
    write_alignment_gap_artifacts(diag, detail, summary)
    return detail, summary


__all__ = [
    "build_alignment_gap_summary",
    "collect_alignment_gap_detail_frame",
    "infer_likely_missing_reason",
    "load_unmatched_label_sample_ids",
    "resolve_diagnostics_dir",
    "run_alignment_gap_diagnosis",
    "write_alignment_gap_artifacts",
]
