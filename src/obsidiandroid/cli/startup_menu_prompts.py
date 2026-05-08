"""Small interactive prompts shared by startup menu actions."""

from __future__ import annotations

from .ui import display as du


def prompt_run_id(default_run_id: str | None = None) -> str | None:
    """Prompt user for run_id with optional default."""
    hint = default_run_id or ""
    prompt = f"Enter run_id [{hint}]: " if hint else "Enter run_id: "
    try:
        entered = input(prompt).strip()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Run ID prompt interrupted.")
        return None
    if entered:
        return entered
    return default_run_id
