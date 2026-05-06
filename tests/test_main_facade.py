"""Tests for :mod:`obsidiandroid.pipeline.main_facade` (CLI monkeypatch bridge)."""

from __future__ import annotations

import sys

from obsidiandroid.pipeline import main_facade


def test_from_main_or_returns_default_when_main_missing(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "main", raising=False)
    assert main_facade.from_main_or("anything", 42) == 42


def test_from_main_or_prefers_main_attribute(monkeypatch) -> None:
    class _FakeMain:
        marker = "patched"

    monkeypatch.setitem(sys.modules, "main", _FakeMain())
    assert main_facade.from_main_or("marker", "default") == "patched"
