"""Tests for shared operator display-mode resolution."""

from __future__ import annotations

from config import app_config

from obsidiandroid.cli.menu import display_mode


def test_resolve_display_mode_defaults_to_compact(monkeypatch) -> None:
    monkeypatch.delenv("OBSIDIANDROID_DISPLAY_MODE", raising=False)
    monkeypatch.setattr(app_config, "DEBUG_MODE", False, raising=False)
    assert display_mode.resolve_display_mode() == "compact"


def test_resolve_display_mode_uses_env_override(monkeypatch) -> None:
    monkeypatch.setenv("OBSIDIANDROID_DISPLAY_MODE", "detailed")
    monkeypatch.setattr(app_config, "DEBUG_MODE", False, raising=False)
    assert display_mode.resolve_display_mode() == "detailed"


def test_mode_max_rows_respects_debug_mode(monkeypatch) -> None:
    monkeypatch.setenv("OBSIDIANDROID_DISPLAY_MODE", "debug")
    assert display_mode.mode_max_rows(compact=3, detailed=8, debug=12) == 12
