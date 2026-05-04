"""Interactive CLI menu helpers."""

from __future__ import annotations

from utils import prompt_utils as pu
from . import console as cc


def _print_breadcrumb(text: str) -> None:
    """Print a muted navigation hint (e.g. where you are in the console)."""
    crumb = str(text).strip()
    if not crumb:
        return
    line = f"  {crumb}"
    try:
        print(cc.apply_color(line, fg=cc.THEME_MUTED))
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"))


def _print_menu_title(title: str, *, subtitle: str | None = None, breadcrumb: str | None = None) -> None:
    """Print menu title and optional breadcrumb / subtitle."""
    if breadcrumb:
        _print_breadcrumb(breadcrumb)
    cc.print_subheader(title.upper())
    if subtitle:
        cc.print_info(str(subtitle).strip())


def _print_menu_options(options: list[str], *, exit_label: str = "Exit") -> None:
    """Print numbered menu options with consistent accent styling."""
    for idx, opt in enumerate(options, 1):
        marker = cc.apply_color(f"[{idx}]", fg=cc.Fore.YELLOW, bold=True)
        label = cc.apply_color(str(opt), fg=cc.Fore.WHITE, bold=True)
        print(f"  {marker} {label}")
    exit_marker = cc.apply_color("[0]", fg=cc.Fore.YELLOW, bold=True)
    exit_text = cc.apply_color(str(exit_label).strip() or "Exit", fg=cc.Fore.WHITE, bold=True)
    print(f"  {exit_marker} {exit_text}\n")


def _format_action_hint(*, default_choice: int | None) -> str:
    parts = ["0 = back", "Ctrl+C = cancel"]
    if default_choice is not None:
        parts.insert(1, f"Enter = default [{int(default_choice)}]")
    return " · ".join(parts)


def _print_menu_footer(hint: str | None) -> None:
    if hint:
        try:
            print(cc.apply_color(f"  ({hint})", fg=cc.THEME_MUTED))
        except UnicodeEncodeError:
            print(f"  ({hint})")
        print("")


def _selection_prompt(max_choice: int) -> str:
    """Build a consistent numeric selection prompt."""
    return cc.apply_color(
        f"Enter your selection [0-{max_choice}]: ",
        fg=cc.Fore.CYAN,
        bold=True,
    )


def display_menu(
    options: list[str],
    title: str = "Select an Option",
    *,
    exit_label: str = "Exit",
    subtitle: str | None = None,
    breadcrumb: str | None = None,
    default_choice: int | None = None,
    action_hint: str | None = None,
) -> int:
    """Render a numbered menu and return selected index (0 = exit/back).

    Args:
        options: Visible choices, numbered 1..N.
        title: Short heading (shown uppercased as a subheader).
        exit_label: Label for the zero option.
        subtitle: Optional single line of context under the title.
        breadcrumb: Optional muted line above the title (e.g. ``Main › Tools``).
        default_choice: If set (1..len(options)), blank input selects that row.
        action_hint: Footer hint; defaults to a standard key legend + default note.
    """
    _print_menu_title(title, subtitle=subtitle, breadcrumb=breadcrumb)
    cc.print_rule(width=cc.DEFAULT_SECTION_WIDTH)
    _print_menu_options(options, exit_label=exit_label)
    footer = action_hint if action_hint is not None else (
        "Type a row number. " + _format_action_hint(default_choice=default_choice)
    )
    _print_menu_footer(footer)
    if default_choice is not None and 1 <= int(default_choice) <= len(options):
        prompt = cc.apply_color(
            f"Enter your selection [default={int(default_choice)}, 0-{len(options)}]: ",
            fg=cc.Fore.CYAN,
            bold=True,
        )
    else:
        prompt = _selection_prompt(len(options))

    while True:
        try:
            raw = input(prompt).strip()
            if default_choice is not None and raw == "":
                choice = int(default_choice)
            else:
                choice = int(raw)
            if 0 <= choice <= len(options):
                return choice
            cc.print_warning("Selection out of range. Please choose a valid number.")
        except ValueError:
            cc.print_warning("Invalid input. Please enter a numeric value (or blank for default).")
        except KeyboardInterrupt:
            cc.print_warning("Selection cancelled by user (Ctrl+C).")
            return 0


def confirm_prompt(message: str = "Are you sure? [y/N]") -> bool:
    """Prompt the user for a yes/no confirmation."""
    return pu.prompt_yes_no(message, default="n")


def select_from_list(items: list[str], prompt: str = "Select an item") -> str | None:
    """Present a list for selection and return selected item or ``None``."""
    if not items:
        cc.print_warning("No items available for selection.")
        return None

    choice = display_menu(items, title=prompt)
    if choice == 0:
        return None
    return items[choice - 1]


def pause(message: str = "Press Enter to continue...") -> None:
    """Pause execution until Enter is pressed."""
    try:
        input(f"\n{message}")
    except KeyboardInterrupt:
        cc.print_warning("Pause interrupted by user (Ctrl+C).")


def display_rich_menu(
    options: dict[str, str],
    title: str = "Available Commands",
    *,
    exit_label: str = "Exit",
    breadcrumb: str | None = None,
    default_choice: int | None = None,
    action_hint: str | None = None,
) -> int:
    """Show a compact numbered menu using **labels only** (dict values are ignored).

    Kept for call sites that still pass an ordered ``dict[str, str]``; per-row description
    lines were removed to reduce vertical space in the operator console.
    """
    return display_menu(
        list(options.keys()),
        title=title,
        exit_label=exit_label,
        subtitle=None,
        breadcrumb=breadcrumb,
        default_choice=default_choice,
        action_hint=action_hint,
    )


__all__ = [
    "display_menu",
    "confirm_prompt",
    "select_from_list",
    "pause",
    "display_rich_menu",
]
