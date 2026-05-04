"""Tests for ``utils.ui.menu`` interactive helpers."""

from __future__ import annotations

from utils.ui import menu


def test_display_menu_blank_input_selects_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    assert menu.display_menu(["First", "Second"], title="T", default_choice=2) == 2


def test_display_rich_menu_blank_input_selects_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    opts = {"A": "one", "B": "two"}
    assert menu.display_rich_menu(opts, title="T", default_choice=2) == 2
