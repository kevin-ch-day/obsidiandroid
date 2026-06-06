"""Tests for diagnostics run artifact resolution across bundles and global mirrors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.diagnostics import run_artifact_resolve

pytestmark = pytest.mark.contract


def test_resolve_run_artifact_path_finds_bundle_stamped_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_root = tmp_path / "output" / "runs" / "majorfam_benchmark"
    diagnostics_dir = run_root / "diagnostics"
    tables_dir = run_root / "bundles" / "permission_trends" / "tables"
    tables_dir.mkdir(parents=True)
    run_id = "20260606T100000Z__abc123"
    stamped = tables_dir / f"permission_prevalence_by_type_{run_id}.csv"
    stamped.write_text("type_slug,permission\nbanker,android.permission.internet\n", encoding="utf-8")

    resolved = run_artifact_resolve.resolve_run_artifact_path(
        diagnostics_dir,
        stem="permission_prevalence_by_type",
        run_id=run_id,
        suffix=".csv",
    )

    assert resolved == stamped


def test_resolve_run_artifact_path_falls_back_to_global_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from obsidiandroid.common import output_hygiene as oh

    run_root = tmp_path / "output" / "runs" / "slot"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    global_diag = tmp_path / "output" / "diagnostics"
    global_diag.mkdir(parents=True, exist_ok=True)
    run_id = "run_global"
    global_file = global_diag / "permission_alias_map.latest.json"
    global_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(oh, "global_diagnostics_root", lambda: global_diag)
    monkeypatch.setattr(oh, "resolve_stable_output_root_for_mirrors", lambda: tmp_path / "output")

    resolved = run_artifact_resolve.resolve_run_artifact_path(
        diagnostics_dir,
        stem="permission_alias_map",
        run_id=run_id,
        suffix=".json",
    )

    assert resolved == global_file


def test_resolve_related_artifact_ref_prefers_bundle_relative_path(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "slot"
    diagnostics_dir = run_root / "diagnostics"
    tables_dir = run_root / "bundles" / "permission_trends" / "tables"
    tables_dir.mkdir(parents=True)
    run_id = "run_ref"
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text("a\n", encoding="utf-8")

    ref = run_artifact_resolve.resolve_related_artifact_ref(
        diagnostics_dir,
        run_id=run_id,
        filename=f"permission_prevalence_by_type_{run_id}.csv",
    )

    assert ref.startswith("bundles/permission_trends/tables/")


def test_glob_bundle_match_finds_timestamped_contract(tmp_path: Path) -> None:
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir(parents=True)
    stamped = contracts_dir / "permission_alias_map_20260606T120000Z__deadbeef.json"
    stamped.write_text(json.dumps({"alias_map": {}}), encoding="utf-8")

    resolved = run_artifact_resolve._glob_bundle_match(contracts_dir, "permission_alias_map", ".json")

    assert resolved == stamped
