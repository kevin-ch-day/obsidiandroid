from pathlib import Path


def test_core_results_grant_script_is_migration_gated_and_source_free() -> None:
    text = Path("scripts/core_migration/apply_core_results_grants.py").read_text(encoding="utf-8")
    assert 'REQUIRED = {"0003", "0004", "0005"}' in text
    assert "Core-results grants require applied migrations" in text
    assert "erebus_threat_intel_prod" not in text
    assert "android_permission_intel" not in text
    assert "OBSIDIANDROID_CORE_PERSISTENCE_ENABLED" not in text
