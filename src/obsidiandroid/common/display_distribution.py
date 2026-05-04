# Filename: display_distribution.py
# Purpose: Modular, presentation-optimized distribution printer for analysis output

import pandas as pd


def _format_percent_bar(percent: float, scale: int = 50, char: str = "█") -> str:
    bar_length = int((percent / 100.0) * scale)
    return char * bar_length


def _print_distribution_header(title: str) -> None:
    print(f"\n{'=' * 90}")
    print(f"[DISTRIBUTION] {title}")
    print(f"{'=' * 90}")
    print(f"{'Category':<30} {'Count':>8}  {'%':>6}  {'Distribution'}")
    print(f"{'-' * 90}")


def _print_distribution_row(category: str, count: int, percent: float, bar: str) -> None:
    print(f"{category:<30} {count:>8}  {percent:6.2f}%  {bar}")


def _print_distribution_footer(total: int) -> None:
    print(f"{'-' * 90}")
    print(f"{'Total':<30} {total:>8}  {'100.00%':>6}")
    print("→ Insight: Use for class balance, anomaly prevalence, or segmentation strategies.\n")


def print_distribution(
    series: pd.Series,
    label: str = "Category Distribution",
    scale: int = 50,
    bar_char: str = "█",
) -> None:
    if series.empty:
        print("[WARNING] No values provided for distribution analysis.")
        return

    try:
        counts = series.value_counts(dropna=False).sort_index()
        total = counts.sum()
        _print_distribution_header(label)

        for value, count in counts.items():
            category = str(value) if pd.notnull(value) else "(Missing)"
            percent = (count / total) * 100
            bar = _format_percent_bar(percent, scale=scale, char=bar_char)
            _print_distribution_row(category, count, percent, bar)

        _print_distribution_footer(total)

    except Exception as e:
        print(f"[WARNING] [DISTRIBUTION] Failed to compute distribution: {e}")


__all__ = ["print_distribution"]
