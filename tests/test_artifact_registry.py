"""Tests for artifact registry write/register behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.pipeline.artifacts.registry import ArtifactRegistry


def test_artifact_registry_write_text_registers_metadata(tmp_path: Path) -> None:
    """Text writes should register non-empty artifact records."""
    registry = ArtifactRegistry()
    target = tmp_path / "out" / "note.txt"
    record = registry.write_text(
        logical_name="note",
        stage_origin="tests",
        path=target,
        text="hello",
    )
    assert record.logical_name == "note"
    assert record.stage_origin == "tests"
    assert record.size_bytes > 0
    assert len(record.sha256) == 64
    assert Path(record.artifact_path).exists()


def test_artifact_registry_write_dataframe_csv_registers_record(tmp_path: Path) -> None:
    """CSV writes should register artifact metadata."""
    registry = ArtifactRegistry()
    target = tmp_path / "out" / "table.csv"
    frame = pd.DataFrame([{"a": 1}, {"a": 2}])
    record = registry.write_dataframe_csv(
        logical_name="table",
        stage_origin="tests",
        path=target,
        dataframe=frame,
        float_format="%.6f",
        lineterminator="\n",
    )
    assert record.logical_name == "table"
    assert record.size_bytes > 0
    assert len(registry.records()) == 1


def test_artifact_registry_register_rejects_empty_file(tmp_path: Path) -> None:
    """Register should fail for empty files."""
    registry = ArtifactRegistry()
    target = tmp_path / "out" / "empty.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        registry.register(
            logical_name="empty",
            stage_origin="tests",
            path=target,
        )
