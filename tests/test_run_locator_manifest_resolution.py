"""Tests for run_locator manifest resolution with alternate output roots."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.cli.menu import run_locator


def test_resolve_latest_manifest_payload_respects_output_base_full_payload(tmp_path: Path) -> None:
    out = tmp_path / "output"
    diag = out / "diagnostics"
    diag.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": "rid1", "profile_params": {"profile_id": "p1"}, "artifact_list": []}
    (diag / "run_manifest.latest.json").write_text(json.dumps(payload), encoding="utf-8")

    man, rid, path = run_locator.resolve_latest_manifest_payload(output_base=out)
    assert rid == "rid1"
    assert path == diag / "run_manifest.latest.json"
    assert man.get("profile_id") is None and (man.get("profile_params") or {}).get("profile_id") == "p1"


def test_resolve_latest_manifest_payload_follows_pointer_under_output_base(tmp_path: Path) -> None:
    out = tmp_path / "output"
    diag = out / "diagnostics"
    runs = out / "runs" / "rid2"
    diag.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    pointer = {"run_id": "rid2"}
    (diag / "run_manifest.latest.json").write_text(json.dumps(pointer), encoding="utf-8")
    canonical = {"run_id": "rid2", "profile_params": {"profile_id": "frozen"}}
    (runs / "run_manifest.json").write_text(json.dumps(canonical), encoding="utf-8")

    man, rid, path = run_locator.resolve_latest_manifest_payload(output_base=out)
    assert rid == "rid2"
    assert path == runs / "run_manifest.json"
    assert (man.get("profile_params") or {}).get("profile_id") == "frozen"
