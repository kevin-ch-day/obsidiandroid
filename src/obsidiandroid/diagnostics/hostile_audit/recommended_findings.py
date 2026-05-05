"""Synthesize hostile-audit artifacts into cautious, defensible headline findings."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


def _read_csv_tail(path: Path, max_rows: int = 12) -> str:
    if not path.exists():
        return "_missing_"
    try:
        df = pd.read_csv(path)
    except Exception:
        return "_unreadable_"
    if df.empty:
        return "_empty_"
    return df.tail(max_rows).to_markdown(index=False)


def write_recommended_findings(*, diagnostics_dir: Path, run_id: str) -> Path:
    """Write ``recommended_findings.md`` after other hostile audit CSV/MD exist."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    out = diagnostics_dir / "recommended_findings.md"

    cohort = diagnostics_dir / "cohort_population_audit.csv"
    baseline = diagnostics_dir / "baseline_comparison.csv"
    target = diagnostics_dir / "target_validity_audit.csv"
    vendor = diagnostics_dir / "vendor_label_leakage_audit.csv"
    perm = diagnostics_dir / "permission_signal_quality.csv"
    temporal = diagnostics_dir / "temporal_validity_audit.md"
    taxonomy = diagnostics_dir / "taxonomy_label_quality_audit.md"

    lines: list[str] = [
        "# Recommended findings (artifact-bound)",
        "",
        "These bullets are **only** as strong as the CSV/JSON inputs in this diagnostics directory. ",
        "They are intended to replace informal paper language with population-scoped statements.",
        "",
        "## Cross-cutting themes",
        "",
        "1. **Name the population stage** whenever reporting N, F1, or prevalence — governed cohort ≠ aligned supervised ≠ train/test.",
        "2. **Vendor semantics vs behavior:** when `vendor_full` ≫ `permissions_raw` on `family_canonical_default`, fine-grained family ",
        "classification may be largely **taxonomy alignment / AV naming**, not permission-defined behavior.",
        "3. **Permission features:** expect stronger utility for **type / capability profiling** than for **39-way family** targets unless ",
        "within-type labels are used — consult `target_validity_audit.csv`.",
        "4. **Random splits** do not establish temporal generalization — see `temporal_validity_audit.md` and request explicit year holdouts.",
        "5. **Taxonomy pipeline health** gates any claim about “ground truth” type/family — see `taxonomy_label_quality_audit.md`.",
        "",
        "## Evidence snapshots (last rows)",
        "",
        "### `cohort_population_audit.csv`",
        "",
        _read_csv_tail(cohort),
        "",
        "### `baseline_comparison.csv`",
        "",
        _read_csv_tail(baseline),
        "",
        "### `target_validity_audit.csv`",
        "",
        _read_csv_tail(target),
        "",
        "### `vendor_label_leakage_audit.csv`",
        "",
        _read_csv_tail(vendor),
        "",
        "### `permission_signal_quality.csv` (sparse preview)",
        "",
    ]

    if perm.exists():
        try:
            with perm.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                snippet = []
                for i, row in enumerate(reader):
                    if i >= 15:
                        break
                    snippet.append(row)
                if snippet:
                    lines.append(pd.DataFrame(snippet).to_markdown(index=False))
                else:
                    lines.append("_empty CSV_")
        except Exception:
            lines.append("_could not preview_")
    else:
        lines.append("_missing_")

    lines.extend(["", "---", "", "### Temporal audit", ""])
    if temporal.exists():
        text = temporal.read_text(encoding="utf-8", errors="replace")
        lines.append(text[:4000] + ("\n\n_…truncated…_" if len(text) > 4000 else ""))
    else:
        lines.append("_missing temporal_validity_audit.md_")

    lines.extend(["", "### Taxonomy audit", ""])
    if taxonomy.exists():
        text = taxonomy.read_text(encoding="utf-8", errors="replace")
        lines.append(text[:4000] + ("\n\n_…truncated…_" if len(text) > 4000 else ""))
    else:
        lines.append("_missing taxonomy_label_quality_audit.md_")

    lines.extend(
        [
            "",
            "## Example replacement sentences (use exact numbers from tables above)",
            "",
            "- Instead of: “We evaluate 1,226 samples across 39 families.”",
            "- Use: “After alignment and low-support filtering, **N_train / N_test** from `cohort_population_audit.csv` cover **K** active family labels.”",
            "",
            "- Instead of: “Permissions strongly predict family.”",
            "- Use: “On `family_canonical_default`, `permissions_raw` Macro-F1 in `ablation_summary_*.csv` is **X**, vs **Y** for `vendor_full`; delta vs baselines in `baseline_comparison.csv`.”",
            "",
        ]
    )

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


__all__ = ["write_recommended_findings"]
