"""Terminal color helpers for the CLI.

All printing functions here gracefully degrade when ``colorama`` is not
available or when the ``NO_COLOR`` environment variable is set. Callers can
use the functions without worrying about color support existing on the host
system.
"""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from typing import Optional

USE_COLORS = os.environ.get("NO_COLOR") is None

if USE_COLORS:
    try:
        from colorama import Back, Fore, Style, init as colorama_init

        colorama_init(autoreset=True)
    except Exception:  # pragma: no cover - fallback path
        USE_COLORS = False

if not USE_COLORS:
    class _ColorDummy:
        """Simple object that returns empty values for color attributes."""

        def __getattr__(self, name: str) -> str:
            return ""

    Fore = Back = Style = _ColorDummy()

DEFAULT_BANNER_WIDTH = 80
DEFAULT_SECTION_WIDTH = 80


def get_console_width(default: int = DEFAULT_SECTION_WIDTH) -> int:
    """Return console width clamped to sensible bounds."""
    try:
        width = shutil.get_terminal_size(fallback=(default, 20)).columns
        width = max(width, 40)
        return min(width, default)
    except Exception:
        return default


# Shared theme tuned for terminal legibility on dark Fedora terminals.
THEME_BORDER = Fore.LIGHTBLACK_EX
THEME_TITLE = Fore.WHITE
THEME_ACCENT = Fore.CYAN
THEME_NOTE = Fore.YELLOW
THEME_MUTED = Fore.LIGHTBLACK_EX
THEME_TEXT = Fore.WHITE

STYLE_SUCCESS = (Fore.GREEN, "")
STYLE_INFO = (THEME_ACCENT, "")
STYLE_WARNING = (Fore.YELLOW, "")
STYLE_ERROR = (Fore.LIGHTRED_EX + Style.BRIGHT, "")
STYLE_DEBUG = (THEME_MUTED + Style.DIM, "")
STYLE_NOTE = (Fore.BLUE, "")
STYLE_DEFAULT = (THEME_TEXT, "")


def apply_color(
    text: str,
    fg: str = "",
    bg: str = "",
    bold: bool = False,
    underline: bool = False,
) -> str:
    """Apply optional ANSI color/style wrappers."""
    if not USE_COLORS:
        return text
    style = ""
    if bold:
        style += Style.BRIGHT
    if underline:
        style += "\033[4m"
    return f"{style}{fg}{bg}{text}{Style.RESET_ALL}"


def format_message(
    tag: str,
    msg: str,
    style: tuple[str, str],
    *,
    indent: int = 0,
    bold: bool = False,
    underline: bool = False,
) -> str:
    """Build a consistent tagged message line."""
    fg, bg = style
    tag_text = f"[{tag.upper()}]"
    spacing = " " * max(1, 12 - len(tag_text))
    line = " " * indent + f"{tag_text}{spacing} {msg}"
    if not USE_COLORS:
        return line

    tag_style = Style.BRIGHT + fg + bg
    message_style = THEME_TEXT
    if bold:
        message_style = Style.BRIGHT + message_style
    if underline:
        message_style = "\033[4m" + message_style
    return (
        f"{' ' * indent}{tag_style}{tag_text}{Style.RESET_ALL}"
        f"{spacing} {message_style}{msg}{Style.RESET_ALL}"
    )


def _colorize_status(value: object) -> str:
    """Apply status-aware coloring for common readiness/value tokens."""
    text = str(value).strip()
    if not text:
        return text
    lowered = text.lower()
    if lowered in {"ready", "available", "yes", "complete", "active"}:
        return apply_color(text, fg=Fore.GREEN, bold=True)
    if lowered in {"not ready", "not built", "missing", "pending", "none yet", "no"}:
        return apply_color(text, fg=Fore.YELLOW, bold=False)
    if lowered in {"failed", "error"}:
        return apply_color(text, fg=Fore.LIGHTRED_EX, bold=True)
    if lowered.startswith("202") and "t" in lowered:
        return apply_color(text, fg=Fore.CYAN, bold=True)
    return apply_color(text, fg=THEME_TEXT)


def _safe_print(text: str) -> None:
    """Print text with fallback for narrow console encodings."""
    try:
        print(text)
    except UnicodeEncodeError:
        sanitized = text.encode("ascii", errors="replace").decode("ascii")
        print(sanitized)


def print_success(msg: str, return_str: bool = False):
    out = format_message("SUCCESS", msg, STYLE_SUCCESS)
    if return_str:
        return out
    _safe_print(out)


def print_info(msg: str, return_str: bool = False):
    out = format_message("INFO", msg, STYLE_INFO)
    if return_str:
        return out
    _safe_print(out)


def print_note(msg: str, return_str: bool = False):
    out = format_message("NOTE", msg, STYLE_NOTE)
    if return_str:
        return out
    _safe_print(out)


def print_warning(msg: str, return_str: bool = False):
    out = format_message("WARNING", msg, STYLE_WARNING)
    if return_str:
        return out
    _safe_print(out)


def print_error(msg: str, return_str: bool = False):
    out = format_message("ERROR", msg, STYLE_ERROR)
    if return_str:
        return out
    _safe_print("\n" + out + "\n")


def print_debug(msg: str, return_str: bool = False):
    out = format_message("DEBUG", msg, STYLE_DEBUG)
    if return_str:
        return out

    debug_enabled = False
    try:
        from config import app_config

        debug_enabled = bool(getattr(app_config, "DEBUG_MODE", False))
    except Exception:
        debug_enabled = False

    if debug_enabled:
        _safe_print(out)


def print_banner(title: str, *, width: int = DEFAULT_BANNER_WIDTH):
    """Print a centered banner heading."""
    width = get_console_width(width)
    line = "=" * width
    _safe_print("\n" + line)
    _safe_print(apply_color(title.upper().center(width), fg=THEME_TITLE, bold=True))
    _safe_print(line + "\n")


def print_section(title: str, *, width: int = DEFAULT_SECTION_WIDTH):
    """Print a formatted section header."""
    width = get_console_width(width)
    line = "=" * width
    _safe_print("")
    _safe_print(apply_color(line, fg=THEME_BORDER))
    _safe_print(apply_color(title.center(width), fg=THEME_TITLE, bold=True))
    _safe_print(apply_color(line, fg=THEME_BORDER))
    _safe_print("")


def print_rule(
    label: str | None = None,
    *,
    width: int = DEFAULT_SECTION_WIDTH,
    color: str = "",
) -> None:
    """Print a horizontal rule with an optional centered label."""
    width = get_console_width(width)
    if label:
        token = f" {str(label).strip()} "
        available = max(0, width - len(token))
        left = "-" * (available // 2)
        right = "-" * (available - len(left))
        line = f"{left}{token}{right}"
    else:
        line = "-" * width
    _safe_print(apply_color(line, fg=color or THEME_MUTED))


def print_subheader(label: str):
    """Print a yellow subheader with underline."""
    label = label.strip().upper()
    underline = "-" * len(label)
    _safe_print("")
    _safe_print(apply_color(label, fg=THEME_NOTE, bold=True))
    _safe_print(apply_color(underline, fg=THEME_MUTED))


def print_label(
    label: str,
    msg: str,
    fg: Optional[str] = Fore.WHITE,
    bg: Optional[str] = "",
    return_str: bool = False,
):
    """Print tagged custom message with optional colors."""
    out = apply_color(f"[{label.upper():<9}] {msg}", fg, bg)
    if return_str:
        return out
    _safe_print(out)


def print_stat(
    label: str,
    value,
    unit: str = "",
    color: Optional[str] = None,
    *,
    width: int = 32,
    precision: int = 2,
    bold: bool = False,
    dim: bool = False,
    return_str: bool = False,
):
    """Print a key/value statistic line with optional styling."""
    if isinstance(value, (int, float)):
        value_str = f"{value:,.{precision}f}" if isinstance(value, float) else f"{value:,d}"
    else:
        value_str = str(value)

    if unit:
        value_str = f"{value_str} {unit}"

    label_text = f"{str(label).strip():<{width}}"
    if not USE_COLORS:
        out = f"{label_text}: {value_str}"
        if return_str:
            return out
        _safe_print(out)
        return

    label_rendered = apply_color(label_text, fg=color or THEME_MUTED)
    separator = apply_color(":", fg=THEME_MUTED)

    if dim:
        value_rendered = apply_color(value_str, fg=THEME_MUTED)
    else:
        value_rendered = _colorize_status(value_str)
        if value_rendered == value_str:
            value_rendered = apply_color(
                value_str,
                fg=color or THEME_TEXT,
                bold=bold,
            )

    out = f"{label_rendered}{separator} {value_rendered}"
    if return_str:
        return out
    _safe_print(out)


def set_colors(enabled: bool) -> None:
    """Globally enable or disable colored output."""
    global USE_COLORS
    USE_COLORS = bool(enabled)


def clear_screen() -> None:
    """Clear the current terminal screen."""
    command = "cls" if os.name == "nt" else "clear"
    os.system(command)


@contextmanager
def temporary_colors(enabled: bool):
    """Temporarily override color output within a context."""
    global USE_COLORS
    previous = USE_COLORS
    USE_COLORS = bool(enabled)
    try:
        yield
    finally:
        USE_COLORS = previous


__all__ = [
    "apply_color",
    "format_message",
    "print_success",
    "print_info",
    "print_note",
    "print_warning",
    "print_error",
    "print_debug",
    "print_banner",
    "print_section",
    "print_rule",
    "get_console_width",
    "set_colors",
    "temporary_colors",
    "print_subheader",
    "print_label",
    "print_stat",
    "clear_screen",
    "Fore",
    "Back",
    "Style",
]
