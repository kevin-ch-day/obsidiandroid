"""Tests for ``obsidiandroid.cli.ui.menu`` interactive helpers."""

from __future__ import annotations

from obsidiandroid.cli.ui import menu


def test_display_menu_blank_input_selects_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    assert menu.display_menu(["First", "Second"], title="T", default_choice=2) == 2


def test_display_menu_blank_without_default_reprompts(monkeypatch) -> None:
    """Main menu: empty line shows hint then accepts numeric choice."""
    replies = iter(["", "2"])

    def _fake_input(_prompt: str = "") -> str:
        return next(replies)

    monkeypatch.setattr("builtins.input", _fake_input)
    assert menu.display_menu(["First", "Second"], title="T") == 2


def test_display_menu_blank_returns_back_when_exit_label_back(monkeypatch) -> None:
    """Submenus with Back: blank Enter returns 0 without extra prompts."""
    monkeypatch.setattr("builtins.input", lambda _p="": "")
    assert menu.display_menu(["Only"], title="T", exit_label="Back") == 0


def test_display_rich_menu_blank_input_selects_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    opts = {"A": "one", "B": "two"}
    assert menu.display_rich_menu(opts, title="T", default_choice=2) == 2
