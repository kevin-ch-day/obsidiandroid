"""Prompt helpers for ObsidianDroid CLI menus."""

from __future__ import annotations

from obsidiandroid.cli.ui import console as cc

print_warning = cc.print_warning


def prompt_yes_no(message: str, default: str = "y") -> bool:
    """Prompt for yes/no; ``default`` is ``\"y\"`` or ``\"n\"`` (lowercase)."""
    default = default.lower()
    options = "[Y/n]" if default == "y" else "[y/N]"
    while True:
        response = input(f"{message} {options}: ").strip().lower()
        if not response:
            return default == "y"
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print_warning("Invalid input. Please enter yes or no.")


__all__ = ["print_warning", "prompt_yes_no"]
