"""Tests for the isolated, explicitly confirmed Phase 2C execution command."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from obsidiandroid.core_migration.mapping import CoreImportError


_SCRIPT = Path("scripts/core_migration/execute_phase2c_import.py")
_SPEC = importlib.util.spec_from_file_location("phase2c_execute_import", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_execution_command_requires_external_private_inputs(tmp_path: Path) -> None:
    private = tmp_path / "reviewed.json"
    private.write_text("{}\n", encoding="utf-8")
    private.chmod(0o600)
    assert _MODULE._private_regular_file(private, label="reviewed input") == private.resolve()

    private.chmod(0o644)
    with pytest.raises(CoreImportError, match="mode 0600"):
        _MODULE._private_regular_file(private, label="reviewed input")


def test_execution_command_refuses_repository_paths() -> None:
    with pytest.raises(CoreImportError, match="outside the repository"):
        _MODULE._outside_repository(Path("scripts/core_migration/execute_phase2c_import.py"), label="plan")


def test_execution_command_requires_exact_authorization_shape() -> None:
    with pytest.raises(CoreImportError, match="missing or unrecognized"):
        _MODULE._authorization_from_payload({"authorization_id": "incomplete"})


def test_execution_command_has_no_source_extract_or_normal_pipeline_import() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "create_phase2c_source_extract" not in text
    assert "run_pipeline" not in text
    assert "OBSIDIAN_DB_" not in text
    assert "EXECUTE_APPROVED_PHASE2C_IMPORT" in text
