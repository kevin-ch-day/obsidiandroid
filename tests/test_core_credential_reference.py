"""Core credential reference loading must stay external, optional, and fail-closed."""

from __future__ import annotations

from pathlib import Path


def test_core_credential_reference_requires_private_file() -> None:
    text = Path("src/obsidiandroid/database/db_config.py").read_text(encoding="utf-8")
    assert "OBSIDIANDROID_CORE_CREDENTIAL_FILE" in text
    assert "mode & 0o077 == 0" in text
    assert "no source credential fallback" in text
