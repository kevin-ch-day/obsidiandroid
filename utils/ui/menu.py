"""Interactive CLI menu helpers."""

from __future__ import annotations

from utils import prompt_utils as pu
from utils.ui import console as cc


def _print_menu_title(title: str) -> None:
    """Print menu title."""
    cc.print_subheader(title.upper())


def _print_menu_options(options: list[str], *, exit_label: str = "Exit") -> None:
    """Print numbered menu options."""
    for idx, opt in enumerate(options, 1):
        print(f"  [{idx}] {opt}")
    print(f"  [0] {str(exit_label).strip() or 'Exit'}\n")


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
) -> int:
    """Render a numbered menu and return selected index."""
    _print_menu_title(title)
    cc.print_info("Choose a number and press Enter.")
    cc.print_rule(width=cc.DEFAULT_SECTION_WIDTH)
    _print_menu_options(options, exit_label=exit_label)
    prompt = _selection_prompt(len(options))

    while True:
        try:
            choice = int(input(prompt).strip())
            if 0 <= choice <= len(options):
                return choice
            cc.print_warning("Selection out of range. Please choose a valid number.")
        except ValueError:
            cc.print_warning("Invalid input. Please enter a numeric value.")
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
) -> int:
    """Display a menu with descriptions."""
    cc.print_section(title.upper())
    cc.print_info("Choose a number and press Enter.")
    cc.print_rule(width=cc.DEFAULT_SECTION_WIDTH, color=cc.Fore.LIGHTBLACK_EX)
    numbered = list(options.items())
    for idx, (label, desc) in enumerate(numbered, 1):
        marker = cc.apply_color(f"[{idx}]", fg=cc.Fore.YELLOW, bold=True)
        title_text = cc.apply_color(str(label), fg=cc.Fore.WHITE, bold=True)
        desc_text = cc.apply_color(str(desc), fg=cc.Fore.LIGHTWHITE_EX)
        print(f"  {marker} {title_text}")
        print(f"      {desc_text}\n")
    cc.print_rule(width=cc.DEFAULT_SECTION_WIDTH, color=cc.Fore.LIGHTBLACK_EX)
    exit_marker = cc.apply_color("[0]", fg=cc.Fore.YELLOW, bold=True)
    exit_text = cc.apply_color(str(exit_label).strip() or "Exit", fg=cc.Fore.WHITE, bold=True)
    print(f"  {exit_marker} {exit_text}\n")
    prompt = _selection_prompt(len(numbered))

    while True:
        try:
            choice = int(input(prompt).strip())
            if 0 <= choice <= len(numbered):
                return choice
            cc.print_warning("Selection out of range. Try again.")
        except ValueError:
            cc.print_warning("Invalid input. Please enter a numeric selection.")
        except KeyboardInterrupt:
            cc.print_warning("Selection cancelled by user (Ctrl+C).")
            return 0


__all__ = [
    "display_menu",
    "confirm_prompt",
    "select_from_list",
    "pause",
    "display_rich_menu",
]
