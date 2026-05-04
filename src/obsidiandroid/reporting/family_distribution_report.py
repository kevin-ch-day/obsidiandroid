"""Print and export malware family distribution stats before training."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Tuple

import pandas as pd
from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_paths

__all__ = ["print_family_distribution_stats"]


def _report_output_path() -> Path:
    """Resolve run-scoped family report path when available."""
    runtime_diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_diag:
        return Path(runtime_diag) / "family_distribution_report.txt"
    return output_paths.reports_root() / "family_distribution_report.txt"


def print_family_distribution_stats(samples_df: pd.DataFrame) -> None:
    """
    Main controller for analyzing and exporting family distribution.

    Args:
        samples_df: DataFrame that includes a 'family_name' column.
    """
    du.print_subheader("Initial Family Distribution")

    if "family_name" not in samples_df.columns:
        du.print_warning("Missing 'family_name' column in dataset.")
        return

    fam_counts = Counter(samples_df["family_name"])
    if not fam_counts:
        du.print_warning("No values found in 'family_name' column.")
        return

    _display_family_distribution_console(fam_counts)
    _export_family_distribution_report(fam_counts)
    du.print_success("Family distribution analysis complete.")


def _display_family_distribution_console(fam_counts: Counter) -> None:
    low_support, sufficient_support = _split_families_by_support(fam_counts)
    max_rows = max(1, int(getattr(app_config, "FAMILY_DISTRIBUTION_MAX_CONSOLE_ROWS", 20)))

    du.print_info(f"Detected {len(fam_counts)} unique families.")
    if low_support:
        du.print_warning(
            f"{len(low_support)} families have <=3 samples. These may affect classifier reliability."
        )

    du.print_info("-- Low-Support Families --")
    _display_family_group(low_support, highlight=True)

    du.print_info("-- Sufficient-Support Families --")
    sorted_sufficient = dict(
        sorted(sufficient_support.items(), key=lambda item: (-item[1], item[0]))[:max_rows]
    )
    _display_family_group(sorted_sufficient)
    if len(sufficient_support) > max_rows:
        du.print_info(
            f"... {len(sufficient_support) - max_rows} additional families omitted from terminal output "
            f"(see full report at {_report_output_path()})."
        )


def _display_family_group(group: dict, highlight: bool = False) -> None:
    for fam in sorted(group):
        count = group[fam]
        suffix = "  * LOW" if highlight else ""
        label = f"{count} sample{'s' if count != 1 else ''}{suffix}"
        du.print_stat(fam, label)


def _export_family_distribution_report(fam_counts: Counter) -> None:
    try:
        report_path = _report_output_path()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        content = _generate_family_report_text(fam_counts)
        _write_report_to_disk(report_path, content)
        du.print_info(f"[EXPORT] Family report saved: {report_path.resolve()}")
    except Exception as e:
        du.print_error(f"[EXPORT FAIL] Failed to export family report: {e}")


def _write_report_to_disk(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _generate_family_report_text(fam_counts: Counter) -> str:
    low_support, sufficient_support = _split_families_by_support(fam_counts)

    lines: list[str] = []
    lines.append("# FAMILY DISTRIBUTION REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Total Unique Families               : {len(fam_counts)}")
    lines.append(f"Low-Sample Families (<=3)            : {len(low_support)}")
    lines.append(f"Sufficient-Sample Families (>3)     : {len(sufficient_support)}")
    lines.append("")

    lines.append("-- LOW-SUPPORT FAMILIES --")
    for fam in sorted(low_support):
        count = low_support[fam]
        lines.append(f"{fam:<25} {count} sample{'s' if count != 1 else ''}  * LOW")

    lines.append("")
    lines.append("-- SUFFICIENT-SUPPORT FAMILIES --")
    for fam in sorted(sufficient_support):
        count = sufficient_support[fam]
        lines.append(f"{fam:<25} {count} sample{'s' if count != 1 else ''}")

    return "\n".join(lines)


def _split_families_by_support(fam_counts: Counter) -> Tuple[dict, dict]:
    low_support = {fam: cnt for fam, cnt in fam_counts.items() if cnt <= 3}
    sufficient_support = {fam: cnt for fam, cnt in fam_counts.items() if cnt > 3}
    return low_support, sufficient_support
