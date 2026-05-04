# Filename: cohort_sample_id_audit.py
# Purpose  : Detect duplicate ``sample_id`` rows in the prepared cohort (len vs nunique drift).

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from utils import display_utils as du


def audit_cohort_sample_id_uniqueness(
    samples_df: pd.DataFrame,
    *,
    diagnostics_dir: Path | None,
    run_id: str,
    artifact_list: list[str] | None = None,
) -> dict[str, int]:
    """Record prepared-row vs distinct-``sample_id`` counts; export drill-down when duplicates exist.

    Returns:
        Dict with ``cohort_prepared_rows``, ``cohort_distinct_sample_id``,
        ``cohort_duplicate_surplus_rows`` (``len - nunique``, clamped at 0).
    """
    out: dict[str, int] = {
        "cohort_prepared_rows": 0,
        "cohort_distinct_sample_id": 0,
        "cohort_duplicate_surplus_rows": 0,
    }
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return out
    if "sample_id" not in samples_df.columns:
        return out

    n = int(len(samples_df))
    dist = int(samples_df["sample_id"].nunique())
    surplus = max(0, n - dist)
    out["cohort_prepared_rows"] = n
    out["cohort_distinct_sample_id"] = dist
    out["cohort_duplicate_surplus_rows"] = surplus

    if surplus <= 0 or diagnostics_dir is None:
        return out

    du.print_warning(
        "[COHORT] Duplicate sample_id rows in prepared cohort: "
        f"prepared_rows={n} distinct_sample_id={dist} duplicate_surplus_rows={surplus}. "
        f"See duplicate_sample_id_cohort_{run_id}.csv"
    )
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    vc = samples_df["sample_id"].value_counts()
    dup_ids = vc[vc > 1].index.tolist()
    rows: list[dict[str, Any]] = []
    for sid in dup_ids:
        sub = samples_df[samples_df["sample_id"] == sid]
        rows.append(
            {
                "sample_id": sid,
                "duplicate_row_count": int(len(sub)),
            }
        )
    rep = pd.DataFrame(rows)
    path = diagnostics_dir / f"duplicate_sample_id_cohort_{run_id}.csv"
    latest = diagnostics_dir / "duplicate_sample_id_cohort.latest.csv"
    rep.to_csv(path, index=False)
    rep.to_csv(latest, index=False)
    if artifact_list is not None and str(path) not in artifact_list:
        artifact_list.append(str(path))
    return out


def merge_sample_id_audit_into_manifest(
    manifest_context: dict[str, Any],
    audit: dict[str, int],
) -> None:
    """Mirror audit integers onto manifest for observability / preflight."""
    manifest_context["cohort_distinct_sample_id"] = audit.get("cohort_distinct_sample_id", 0)
    manifest_context["cohort_duplicate_surplus_rows"] = audit.get("cohort_duplicate_surplus_rows", 0)
