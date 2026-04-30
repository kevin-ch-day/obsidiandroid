"""High level helpers for presenting data and status messages in the console."""

from __future__ import annotations

import os

import pandas as pd
from tabulate import tabulate

from utils import display_distribution
from utils.ui import console as cc
from utils.ui import menu as mu

print_info = cc.print_info
print_success = cc.print_success
print_warning = cc.print_warning
print_error = cc.print_error
print_debug = cc.print_debug
print_note = cc.print_note
print_label = cc.print_label
apply_color = cc.apply_color
styled_message = cc.format_message
print_banner = cc.print_banner
print_section = cc.print_section
print_rule = cc.print_rule
print_subheader = cc.print_subheader
print_stat = cc.print_stat
display_menu = mu.display_menu
print_distribution = display_distribution.print_distribution


def print_panel(
    title: str,
    rows: list[tuple[str, object]],
    *,
    width: int = cc.DEFAULT_SECTION_WIDTH,
) -> None:
    """Compatibility renderer for legacy panel call sites.

    The operator UI no longer uses boxed panels. This helper preserves older
    imports while rendering a lightweight subheader-plus-stats block instead.
    """
    del width
    print_subheader(title)
    for label, value in rows:
        print_stat(label, value)
    print("")


def clear_console() -> None:
    """Clear the terminal window in a cross-platform manner."""
    os.system("cls" if os.name == "nt" else "clear")


def print_table(
    df: pd.DataFrame | list[dict] | None,
    title: str | None = None,
    columns: list[str] | None = None,
    *,
    show_index: bool = False,
    max_rows: int | None = None,
    max_col_width: int | None = None,
    floatfmt: str = "g",
    tablefmt: str = "github",
) -> None:
    """Render a simple table of selected DataFrame columns or records."""
    if df is None:
        print_info("No data available to display.")
        return

    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception:
            print_error("Unable to tabulate provided data structure.")
            return

    if df.empty:
        print_info("No data available to display.")
        return

    if title:
        print_section(f"[DATAFRAME] {title}")

    if columns:
        missing = [col for col in columns if col not in df.columns]
        if missing:
            print_warning(f"Missing columns: {missing}")
        df = df[[col for col in columns if col in df.columns]]

    if max_rows is not None and len(df) > max_rows:
        print_note(f"Showing first {max_rows} rows")
        df = df.head(max_rows)

    tab_kwargs = {
        "headers": "keys",
        "tablefmt": tablefmt,
        "showindex": show_index,
        "floatfmt": floatfmt,
    }
    if max_col_width is not None:
        tab_kwargs["maxcolwidths"] = max_col_width

    try:
        table_str = tabulate(df.fillna("-"), **tab_kwargs)
        print(table_str)
    except UnicodeEncodeError:
        tab_kwargs["tablefmt"] = "github"
        table_str = tabulate(df.fillna("-"), **tab_kwargs)
        print(table_str.encode("ascii", errors="replace").decode("ascii"))
    print("-" * cc.DEFAULT_SECTION_WIDTH + "\n")


def print_metric_summary(
    metrics: dict,
    title: str = "Metric Summary",
    *,
    precision: int = 4,
    key_width: int = 34,
    normalize_keys: bool = True,
) -> None:
    """Print a dictionary of metric values with alignment and formatting."""
    print_section(f"[SUMMARY] {title}")
    for key, val in metrics.items():
        label = str(key)
        if normalize_keys:
            label = label.replace("_", " ")
        if isinstance(val, float):
            fmt = f"{{val:>{10}.{precision}f}}"
            print(f"{label:<{key_width}}: {fmt.format(val=val)}")
        else:
            print(f"{label:<{key_width}}: {val}")
    print("-" * cc.DEFAULT_SECTION_WIDTH)


def print_statistical_range(name: str, values: list[float]) -> None:
    """Display min/avg/max of a numeric sequence."""
    if not values:
        print_info(f"{name}: No values provided.")
        return
    avg = sum(values) / len(values)
    print_info(f"-> {name} - Min: {min(values):.4f} | Avg: {avg:.4f} | Max: {max(values):.4f}")


def print_tier_distribution(
    tier_series: pd.Series,
    label: str = "Detection Tier Distribution",
) -> None:
    """Print a breakdown of AV engine detection tiers with percentages."""
    if tier_series.empty:
        print_warning("No tier data available.")
        return
    print_section(f"[TIERS] {label}")
    counts = tier_series.value_counts(dropna=False).sort_index()
    total = counts.sum()
    for tier, count in counts.items():
        percent = (count / total) * 100
        print(f"  - {tier:<30}: {count:>3} ({percent:5.1f}%)")
    print("  -> Use for segmentation, tier-based filtering, or ML weighting.\n")


def print_key_values(
    data: dict,
    title: str = "Key-Value Summary",
    indent: int = 0,
    *,
    sort_keys: bool = False,
    list_preview: int = 5,
) -> None:
    """Pretty-print a nested dictionary or mapping."""
    pad = " " * indent
    if indent == 0:
        print_section(f"{title}")
    else:
        print(f"{pad}{title}")

    items = sorted(data.items()) if sort_keys else data.items()
    for key, value in items:
        label = f"{pad}{key:<30}:"
        if isinstance(value, dict):
            print(f"{label}")
            for sub_key, sub_value in value.items():
                sub_label = f"{pad}  +- {sub_key:<25}:"
                print(f"{sub_label} {sub_value}")
        elif isinstance(value, list):
            try:
                preview = ", ".join(map(str, value[:list_preview]))
                if len(value) > list_preview:
                    preview += "..."
                print(f"{label} [{len(value)} items] {preview}")
            except Exception:
                print(f"{label} [list of {len(value)} items]")
        elif isinstance(value, float):
            print(f"{label} {value:.4f}")
        elif isinstance(value, int):
            print(f"{label} {value}")
        elif value is None:
            print(f"{label} (None)")
        else:
            print(f"{label} {str(value)}")
    print("-" * cc.DEFAULT_SECTION_WIDTH)


def display_dataframe(
    df: pd.DataFrame,
    title: str = "DataFrame Preview",
    max_rows: int = 10,
    max_cols: int = 8,
) -> None:
    """Show a small portion of a DataFrame for interactive sessions."""
    print_section(title)
    if not isinstance(df, pd.DataFrame):
        print_error("Input is not a DataFrame.")
        return
    if df.empty:
        print_warning("The DataFrame has no rows.")
        return

    rows, cols = df.shape
    print_info(f"[DATAFRAME] Shape: {rows} rows x {cols} columns")
    display_rows = min(max_rows, rows) if max_rows > 0 else rows
    display_cols = min(max_cols, cols) if max_cols > 0 else cols

    if rows > display_rows:
        print_note(f"Showing first {display_rows} rows")
    if cols > display_cols:
        print_note(f"Truncated to first {display_cols} columns")

    preview_df = df.iloc[:display_rows, :display_cols]
    with pd.option_context("display.max_columns", display_cols, "display.width", None):
        print(preview_df.to_string(index=False))

    if cols > display_cols:
        print_note(f"Total columns: {cols}. Use export or inspection menu to see full structure.")


def print_header(text: str, width: int = cc.DEFAULT_SECTION_WIDTH) -> None:
    """Print a simple header with cyan highlighting."""
    width = cc.get_console_width(width)
    border = "-" * width
    centered = f" {text} ".center(width, "-")
    print()
    print(border)
    print(apply_color(centered, fg=cc.Fore.LIGHTCYAN_EX))
    print(border + "\n")


def print_breakpoint(text: str = "", width: int = cc.DEFAULT_SECTION_WIDTH) -> None:
    """Print a neutral visual breakpoint line."""
    width = cc.get_console_width(width)
    line = "-" * width
    if text:
        print(f"{line}\n{text}\n{line}")
    else:
        print(line)


__all__ = [
    "print_info",
    "print_success",
    "print_warning",
    "print_error",
    "print_debug",
    "print_note",
    "print_label",
    "apply_color",
    "styled_message",
    "print_banner",
    "print_section",
    "print_rule",
    "print_panel",
    "print_subheader",
    "print_stat",
    "clear_console",
    "display_menu",
    "print_distribution",
    "print_table",
    "print_metric_summary",
    "print_statistical_range",
    "print_tier_distribution",
    "print_key_values",
    "display_dataframe",
    "print_header",
    "print_breakpoint",
]
