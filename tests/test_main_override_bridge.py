"""Tests for :mod:`obsidiandroid.cli.main_override_bridge`."""

from __future__ import annotations

import sys

from obsidiandroid.cli import main_override_bridge


def test_resolve_main_override_returns_default_when_main_missing(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "main", raising=False)
    assert main_override_bridge.resolve_main_override("anything", 42) == 42


def test_resolve_main_override_prefers_main_attribute(monkeypatch) -> None:
    class _FakeMain:
        marker = "patched"

    monkeypatch.setitem(sys.modules, "main", _FakeMain())
    assert main_override_bridge.resolve_main_override("marker", "default") == "patched"
