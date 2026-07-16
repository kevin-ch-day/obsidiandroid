"""Export active-family mappings that reference retired taxonomy types.

The report is read-only. It identifies lifecycle contradictions for curation;
it never changes family mappings or reactivates type records.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.database.db_cohort_readiness import (
    fetch_active_family_inactive_type_gaps,
)


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "taxonomy_active_family_inactive_type_gaps_latest.csv"


def build_report() -> pd.DataFrame:
    """Return the lifecycle review queue in a stable column order."""
    columns = [
        "family_id",
        "family_slug",
        "family_status",
        "primary_type_id",
        "type_slug",
        "authority_sample_count",
        "recommended_action",
    ]
    rows = pd.DataFrame(fetch_active_family_inactive_type_gaps())
    if rows.empty:
        return pd.DataFrame(columns=columns)
    rows["recommended_action"] = (
        "Review taxonomy lifecycle: reactivate the governed type only with "
        "evidence, or remap/deactivate the active family. No automatic change."
    )
    return rows.reindex(columns=columns)


def main() -> int:
    """Write the lifecycle-gap worklist and print a concise operator summary."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    report.to_csv(CSV_OUT, index=False)
    print(f"[EXPORT] Taxonomy type lifecycle gaps: {CSV_OUT.as_posix()}")
    print(f"Rows: {len(report)}")
    if report.empty:
        print("Status: no active family points to a retired type.")
        return 0
    impacted = int(pd.to_numeric(report["authority_sample_count"], errors="coerce").fillna(0).sum())
    print(f"Authority-linked samples affected: {impacted}")
    print("Status: review required; report made no database changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
