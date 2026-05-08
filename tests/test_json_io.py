"""Tests for obsidiandroid.common.json_io."""

from __future__ import annotations

import json
from pathlib import Path


def test_read_json_dict_missing_returns_empty(tmp_path: Path) -> None:
    from obsidiandroid.common.json_io import read_json_dict

    assert read_json_dict(tmp_path / "nope.json") == {}


def test_read_json_dict_object_roundtrip(tmp_path: Path) -> None:
    from obsidiandroid.common.json_io import read_json_dict

    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert read_json_dict(p) == {"a": 1}


def test_read_json_dict_non_object_returns_empty(tmp_path: Path) -> None:
    from obsidiandroid.common.json_io import read_json_dict

    p = tmp_path / "arr.json"
    p.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert read_json_dict(p) == {}
