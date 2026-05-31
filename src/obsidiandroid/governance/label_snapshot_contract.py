"""Shared helpers for row-level label snapshot normalization and hashing."""

from __future__ import annotations

from typing import Any

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload


def normalize_label_snapshot_frame(df: pd.DataFrame) -> pd.DataFrame | None:
    """Normalize a row-level label snapshot to the canonical hashing contract."""
    required = {"sample_id", "family_canonical", "type_slug"}
    if not required.issubset(df.columns):
        return None
    work = df.copy()
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="coerce")
    work = work.dropna(subset=["sample_id"])
    work["sample_id"] = work["sample_id"].astype(int)
    if "family_id" not in work.columns:
        work["family_id"] = pd.NA
    if "sha256" not in work.columns:
        work["sha256"] = ""
    keep = ["sample_id", "sha256", "family_id", "family_canonical", "type_slug"]
    return (
        work[keep]
        .drop_duplicates("sample_id")
        .sort_values("sample_id", kind="mergesort")
        .reset_index(drop=True)
    )


def label_snapshot_hash(df: pd.DataFrame) -> str:
    """Compute the stable row-level hash for a paper label snapshot."""
    ordered = normalize_label_snapshot_frame(df)
    if ordered is None:
        return ""
    records: list[dict[str, Any]] = []
    for _, row in ordered.iterrows():
        records.append(
            {
                "sample_id": int(row["sample_id"]),
                "family_id": None if pd.isna(row.get("family_id")) else int(row["family_id"]),
                "family_canonical": str(row.get("family_canonical", "") or "").strip(),
                "type_slug": str(row.get("type_slug", "") or "").strip().lower(),
            }
        )
    return hash_payload(records)
