"""Tests for ``database.settings`` accessors."""

from __future__ import annotations

from database.settings import ObsidianConnectionSettings, load_connection_settings


def test_load_connection_settings_matches_dataclass_fields() -> None:
    s = load_connection_settings()
    assert isinstance(s, ObsidianConnectionSettings)
    assert isinstance(s.host, str)
    assert isinstance(s.port, int)
    assert isinstance(s.database, str)
    assert isinstance(s.permission_intel_database, str)
