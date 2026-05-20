"""Export parser-enriched vendor label evidence for label-authority rollout.

This is a read-only helper:
- reads wide rows from `virustotal_sample_vendor_engine_verdicts`
- applies current vendor parsers
- emits long-form evidence rows suitable for review or bulk-load into
  `malware_family_label_evidence`

It does not modify the database.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import sys
from typing import Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.database import db_engine
from obsidiandroid.database.verdict_semantics import NON_DETECTION_TOKENS, VERDICT_METADATA_COLUMNS
from obsidiandroid.vendors.parsing.vendor_parser_map import (
    get_vendor_parser_map,
    resolve_vendor_column_name,
)


DEFAULT_OUTPUT = Path("output") / "diagnostics" / "label_authority_vendor_evidence_seed_latest.csv"
CSV_COLUMNS = [
    "sample_id",
    "vendor_key",
    "raw_vendor_label",
    "parsed_family_token",
    "parsed_type_token",
    "parsed_class_token",
    "generic_token_flag",
    "parser_name",
    "parser_version",
    "parser_confidence_score",
    "source_report_date_utc",
    "is_active",
    "notes",
]


def _normalize(value: object) -> str:
    return str(value).strip().lower() if value is not None else ""


def _fetch_vendor_columns() -> list[str]:
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'virustotal_sample_vendor_engine_verdicts'
        ORDER BY ordinal_position
    """
    df = db_engine.execute_query(query, fetch=True, as_dataframe=True)
    if df is None or df.empty:
        return []
    return df["column_name"].astype(str).tolist()


def _select_vendor_columns(available_columns: list[str], requested_vendors: list[str] | None) -> list[tuple[str, str, object]]:
    parser_map = get_vendor_parser_map()
    candidates = requested_vendors or sorted(parser_map.keys())
    selected: list[tuple[str, str, object]] = []
    for vendor in candidates:
        entry = parser_map.get(vendor)
        if not isinstance(entry, dict):
            continue
        column_name = resolve_vendor_column_name(vendor, available_columns)
        if not column_name:
            continue
        selected.append((vendor, column_name, entry["func"]))
    return selected


def _fetch_verdict_frame(vendor_columns: Iterable[str], limit: int | None) -> pd.DataFrame:
    cols = ["sample_id", "updated_at", *vendor_columns]
    select_cols = ", ".join(f"`{col}`" for col in cols)
    query = f"SELECT {select_cols} FROM virustotal_sample_vendor_engine_verdicts"
    if limit and limit > 0:
        query += f" LIMIT {int(limit)}"
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def _is_non_detection(label: object) -> bool:
    return _normalize(label) in NON_DETECTION_TOKENS


def _generic_flag(parsed: dict, raw_label: str) -> int:
    generic_family = _normalize(parsed.get("family")) in {"", "unknown", "generic", "agent", "malware"}
    generic_type = _normalize(parsed.get("malware_type")) in {"", "unknown", "trojan", "malware"}
    generic_threat = _normalize(parsed.get("threat_class")) in {"", "unknown", "generic"}
    raw = _normalize(raw_label)
    raw_generic = any(tok in raw for tok in ("generic", "unknown", "heur", "agent", "malware"))
    return int(generic_family or (generic_type and generic_threat) or raw_generic)


def build_evidence_export(df: pd.DataFrame, vendor_specs: list[tuple[str, str, object]]) -> pd.DataFrame:
    if df is None or df.empty or not vendor_specs:
        return pd.DataFrame(columns=CSV_COLUMNS)

    rows: list[dict] = []
    for vendor_key, column_name, parser_func in vendor_specs:
        if column_name not in df.columns:
            continue
        series = df[column_name]
        nonempty_mask = series.notna() & series.astype(str).str.strip().ne("")
        for _, row in df.loc[nonempty_mask, ["sample_id", "updated_at", column_name]].iterrows():
            raw_label = str(row[column_name]).strip()
            if not raw_label or _is_non_detection(raw_label):
                continue
            parsed_obj = parser_func(raw_label)
            parsed = parsed_obj.to_dict() if hasattr(parsed_obj, "to_dict") else dict(parsed_obj or {})
            rows.append(
                {
                    "sample_id": int(row["sample_id"]),
                    "vendor_key": _normalize(vendor_key),
                    "raw_vendor_label": raw_label,
                    "parsed_family_token": _normalize(parsed.get("family")) or None,
                    "parsed_type_token": _normalize(parsed.get("malware_type")) or None,
                    "parsed_class_token": _normalize(parsed.get("threat_class")) or None,
                    "generic_token_flag": _generic_flag(parsed, raw_label),
                    "parser_name": f"vendor_parser::{_normalize(vendor_key)}",
                    "parser_version": "current_repo",
                    "parser_confidence_score": float(parsed.get("confidence", 0.0) or 0.0),
                    "source_report_date_utc": row["updated_at"],
                    "is_active": 1,
                    "notes": f"parser-enriched export from wide verdict column {column_name}",
                }
            )

    if not rows:
        return pd.DataFrame(columns=CSV_COLUMNS)

    out_df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    out_df = out_df.drop_duplicates(
        subset=["sample_id", "vendor_key", "raw_vendor_label", "parser_name"],
        keep="first",
    ).reset_index(drop=True)
    return out_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vendors",
        nargs="*",
        default=None,
        help="Optional vendor parser keys to export (default: all available parsers with matching columns).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional row limit from the wide verdict table for a smaller seed export.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="CSV output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    available_columns = _fetch_vendor_columns()
    vendor_specs = _select_vendor_columns(available_columns, args.vendors)
    if not vendor_specs:
        print("[WARN] No matching vendor columns and parser mappings found.")
        return 1

    vendor_columns = [column_name for _, column_name, _ in vendor_specs if column_name not in VERDICT_METADATA_COLUMNS]
    verdict_df = _fetch_verdict_frame(vendor_columns, args.limit if args.limit > 0 else None)
    export_df = build_evidence_export(verdict_df, vendor_specs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_csv(args.output, index=False)

    print(f"[OK] Exported parser-enriched vendor evidence: {args.output}")
    print(f"[INFO] Rows: {len(export_df)}")
    if not export_df.empty:
        counts = (
            export_df.groupby("vendor_key")["sample_id"]
            .count()
            .sort_values(ascending=False)
        )
        for vendor_key, count in counts.items():
            print(f"  - {vendor_key}: {int(count)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
