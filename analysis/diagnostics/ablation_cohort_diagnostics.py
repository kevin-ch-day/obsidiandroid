"""Write ablation cohort gap / integrity artifacts (read-only from run data)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_ablation_cohort_gap_artifacts(
    *,
    diagnostics_dir: Path,
    run_id: str,
    gap_table_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    missing_ids_long: pd.DataFrame | None = None,
) -> tuple[Path, Path, Path | None]:
    """Persist JSON/MD/CSV gap diagnostics under ``diagnostics_dir``."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    payload = dict(summary)
    payload["run_id"] = str(run_id)
    payload["feature_set_rows"] = gap_table_rows

    json_path = diagnostics_dir / "ablation_cohort_gap_summary.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_lines = [
        "# Ablation cohort gap summary",
        "",
        f"**Run:** `{run_id}`",
        "",
        "## Configuration",
        "",
        "```text",
        json.dumps(
            {k: summary[k] for k in sorted(summary) if k not in ("feature_set_rows",)},
            indent=2,
        ),
        "```",
        "",
        "## Per feature set",
        "",
        "```text",
        json.dumps(gap_table_rows, indent=2),
        "```",
        "",
    ]
    if missing_ids_long is not None and not missing_ids_long.empty:
        md_lines.extend(
            [
                "## Missing sample_ids (long)",
                "",
                "```text",
                missing_ids_long.head(500).to_string(index=False),
                "```",
                "",
            ]
        )
    md_path = diagnostics_dir / "ablation_cohort_gap_summary.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    csv_path: Path | None = None
    if missing_ids_long is not None and not missing_ids_long.empty:
        csv_path = diagnostics_dir / "ablation_missing_sample_ids_by_feature_set.csv"
        missing_ids_long.to_csv(csv_path, index=False)

    return json_path, md_path, csv_path


__all__ = ["write_ablation_cohort_gap_artifacts"]
