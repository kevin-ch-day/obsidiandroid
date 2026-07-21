"""Guard the Core-results grant script contract."""

from __future__ import annotations

from pathlib import Path


def test_core_results_grant_script_is_fail_closed() -> None:
    text = Path("scripts/core_migration/apply_core_results_grants.py").read_text(encoding="utf-8")
    assert "Dry-run by default" in text or "dry-run" in text.lower()
    assert "Refusing to overwrite an existing Core-results grant receipt" in text
    assert "rollback_claimed" in text
    assert "MIGRATION_CHECKSUMS" in text
    assert "post_grant_audit_sha256" in text
