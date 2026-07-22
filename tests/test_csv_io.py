"""Tests for shared CSV I/O helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.common.csv_io import optional_csv, require_csv, write_csv


def test_optional_csv_handles_missing_and_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert optional_csv(missing).empty
    assert optional_csv(empty).empty


def test_require_csv_rejects_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        require_csv(empty)


def test_write_csv_avoids_newline_only_stub(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    write_csv(path, pd.DataFrame())
    assert path.read_bytes() == b""
    assert optional_csv(path).empty


def test_write_csv_emits_header_for_empty_frame(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    write_csv(path, pd.DataFrame(), empty_columns=("a", "b"))
    loaded = optional_csv(path)
    assert list(loaded.columns) == ["a", "b"]
    assert loaded.empty


def test_optional_csv_handles_newline_only_file(tmp_path: Path) -> None:
    path = tmp_path / "newline.csv"
    path.write_text("\n", encoding="utf-8")
    assert optional_csv(path).empty
