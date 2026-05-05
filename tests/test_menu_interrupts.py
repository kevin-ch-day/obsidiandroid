"""Tests for Ctrl+C handling in interactive menus."""

from __future__ import annotations

import obsidiandroid.cli.startup_menu as startup_menu
from obsidiandroid.cli.ui import menu


def test_display_menu_returns_zero_on_keyboard_interrupt(monkeypatch) -> None:
    """Ctrl+C in menu input should return Exit code path (0)."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": (_ for _ in ()).throw(KeyboardInterrupt))
    result = menu.display_menu(["Option A", "Option B"], title="Test Menu")
    assert result == 0


def test_startup_menu_main_returns_130_on_keyboard_interrupt(monkeypatch) -> None:
    """Top-level startup menu should convert Ctrl+C to exit code 130."""
    monkeypatch.setattr(startup_menu, "launch_startup_menu", lambda: (_ for _ in ()).throw(KeyboardInterrupt))
    assert startup_menu.main() == 130

