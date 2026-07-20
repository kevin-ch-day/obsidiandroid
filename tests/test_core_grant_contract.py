"""Keep the documented Phase 2B grant separation intentionally narrow."""

from __future__ import annotations

from pathlib import Path


def test_normal_core_writer_is_insert_oriented_without_delete() -> None:
    text = Path("docs/core_migration/phase2b_core_contract.md").read_text(encoding="utf-8")
    writer_lines = [line for line in text.splitlines() if "obsidiandroid_core_writer" in line]
    assert writer_lines
    assert all("DELETE" not in line for line in writer_lines)
    assert all("UPDATE" not in line for line in writer_lines)
    assert any("core_artifact" in line and "INSERT" in line for line in writer_lines)
    assert any("core_quality_finding" in line and "INSERT" in line for line in writer_lines)


def test_source_reader_has_no_write_grants_and_migrator_is_separate() -> None:
    text = Path("docs/core_migration/phase2b_core_contract.md").read_text(encoding="utf-8")
    source_lines = [line for line in text.splitlines() if "obsidiandroid_erebus_reader" in line]
    assert source_lines and all("GRANT SELECT" in line for line in source_lines)
    assert "obsidiandroid_core_migrator" in text
    assert "No account receives `CREATE USER`, `GRANT OPTION`, global" in text
