"""Print and export malware family distribution stats before training."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Tuple

import pandas as pd
from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
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
        samples_df: DataFrame that includes a canonical family column.
    """
    du.print_subheader("Initial Family Distribution")

    family_column = (
        "family_canonical"
        if "family_canonical" in samples_df.columns
        else ("family_name" if "family_name" in samples_df.columns else None)
    )
    if family_column is None:
        du.print_warning("Missing family column in dataset (expected family_canonical or family_name).")
        return

    family_series = samples_df[family_column].fillna("").astype(str).str.strip()
    family_series = family_series.replace("", "unknown")
    fam_counts = Counter(family_series)
    if not fam_counts:
        du.print_warning(f"No values found in '{family_column}' column.")
        return

    min_support = _resolve_min_family_support(samples_df)
    attrs = getattr(samples_df, "attrs", {}) if isinstance(getattr(samples_df, "attrs", None), dict) else {}
    support_floor_mode = str(attrs.get("support_floor_mode", "") or "").strip().lower()
    benchmark_mode = support_floor_mode == "benchmark_eligibility"
    if family_column != "family_name":
        du.print_info(f"[DISTRIBUTION] Using `{family_column}` as the family surface for pre-training reporting.")
    _display_family_distribution_console(
        fam_counts,
        min_support=min_support,
        benchmark_mode=benchmark_mode,
    )
    _export_family_distribution_report(fam_counts, min_support=min_support)
    du.print_success("Family distribution analysis complete.")


def _display_family_distribution_console(
    fam_counts: Counter,
    *,
    min_support: int,
    benchmark_mode: bool = False,
) -> None:
    low_support, sufficient_support = _split_families_by_support(fam_counts, min_support=min_support)
    max_rows = max(
        1,
        safe_int_config_value(
            getattr(app_config, "FAMILY_DISTRIBUTION_MAX_CONSOLE_ROWS", 20), default=20
        ),
    )
    if ml_console.is_compact():
        max_rows = min(max_rows, 10)

    du.print_info(f"Detected {len(fam_counts)} unique families.")
    if low_support:
        if benchmark_mode:
            du.print_warning(
                f"{len(low_support)} families have <{min_support} samples and will be excluded from supervised family benchmarking."
            )
        else:
            du.print_warning(
                f"{len(low_support)} families have <{min_support} samples. These may affect classifier reliability."
            )

    if ml_console.is_compact():
        preview_rows = min(max_rows, 8)
        sorted_sufficient = sorted(
            sufficient_support.items(),
            key=lambda item: (-item[1], str(item[0]).lower()),
        )
        leaders = " | ".join(
            f"{fam}={count:,}"
            for fam, count in sorted_sufficient[:preview_rows]
        )
        if leaders:
            du.print_stat("Family Leaders", leaders)
        if low_support:
            low_preview = sorted(low_support.items(), key=lambda item: (item[1], str(item[0]).lower()))[:5]
            du.print_stat(
                "Benchmark-excluded" if benchmark_mode else "Low-Support Families",
                " | ".join(f"{fam}={count}" for fam, count in low_preview),
            )
            if len(low_support) > len(low_preview):
                du.print_info(
                    f"... {len(low_support) - len(low_preview)} additional low-support families omitted from terminal output."
                )
        if len(sufficient_support) > preview_rows:
            du.print_info(
                f"... {len(sufficient_support) - preview_rows} additional families omitted from terminal output."
            )
        return

    du.print_info("-- Low-Support Families --")
    _display_family_group(low_support, highlight=True, sort_by_support=False)

    du.print_info("-- Benchmark-Eligible Families --" if benchmark_mode else "-- Sufficient-Support Families --")
    sorted_sufficient = dict(
        sorted(sufficient_support.items(), key=lambda item: (-item[1], str(item[0]).lower()))[:max_rows]
    )
    _display_family_group(sorted_sufficient, sort_by_support=True)
    if len(sufficient_support) > max_rows:
        du.print_info(
            f"... {len(sufficient_support) - max_rows} additional families omitted from terminal output."
        )


def _display_family_group(group: dict, highlight: bool = False, *, sort_by_support: bool = False) -> None:
    keys = (
        sorted(group, key=lambda value: (-int(group[value]), str(value).lower()))
        if sort_by_support
        else sorted(group, key=lambda value: (int(group[value]), str(value).lower()))
    )
    for fam in keys:
        count = group[fam]
        suffix = "  * LOW" if highlight else ""
        label = f"{count} sample{'s' if count != 1 else ''}{suffix}"
        du.print_stat(fam, label)


def _export_family_distribution_report(fam_counts: Counter, *, min_support: int) -> None:
    try:
        report_path = _report_output_path()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        content = _generate_family_report_text(fam_counts, min_support=min_support)
        _write_report_to_disk(report_path, content)
        du.print_info(f"[EXPORT] Family report:{du.format_console_path(report_path)}")
    except Exception as e:
        du.print_error(f"[EXPORT FAIL] Failed to export family report: {e}")


def _write_report_to_disk(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _generate_family_report_text(fam_counts: Counter, *, min_support: int) -> str:
    low_support, sufficient_support = _split_families_by_support(fam_counts, min_support=min_support)

    lines: list[str] = []
    lines.append("# FAMILY DISTRIBUTION REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Total Unique Families               : {len(fam_counts)}")
    lines.append(f"Configured Min Family Support       : {min_support}")
    lines.append(f"Low-Sample Families (<{min_support})          : {len(low_support)}")
    lines.append(f"Sufficient-Sample Families (>={min_support})  : {len(sufficient_support)}")
    lines.append("")

    lines.append("-- LOW-SUPPORT FAMILIES --")
    for fam in sorted(low_support, key=lambda value: str(value).lower()):
        count = low_support[fam]
        lines.append(f"{fam:<25} {count} sample{'s' if count != 1 else ''}  * LOW")

    lines.append("")
    lines.append("-- SUFFICIENT-SUPPORT FAMILIES --")
    for fam in sorted(sufficient_support, key=lambda value: str(value).lower()):
        count = sufficient_support[fam]
        lines.append(f"{fam:<25} {count} sample{'s' if count != 1 else ''}")

    return "\n".join(lines)


def _split_families_by_support(fam_counts: Counter, *, min_support: int) -> Tuple[dict, dict]:
    threshold = max(1, int(min_support))
    low_support = {fam: cnt for fam, cnt in fam_counts.items() if cnt < threshold}
    sufficient_support = {fam: cnt for fam, cnt in fam_counts.items() if cnt >= threshold}
    return low_support, sufficient_support


def _resolve_min_family_support(samples_df: pd.DataFrame) -> int:
    attrs = getattr(samples_df, "attrs", {}) if isinstance(getattr(samples_df, "attrs", None), dict) else {}
    raw = attrs.get(
        "configured_min_samples_per_family",
        getattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", getattr(app_config, "MIN_FAMILY_SUPPORT", 3)),
    )
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 3
