# Filename: utils/prompt_utils.py
# Purpose  : Prompt utilities for ObsidianDroid CLI

from utils.ui import console as cc

print_warning = cc.print_warning

# === Prompt Helpers ===
def prompt_yes_no(message: str, default: str = "y") -> bool:
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


__all__ = ["prompt_yes_no"]
