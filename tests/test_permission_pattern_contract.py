from __future__ import annotations

from pathlib import Path

import pytest

from obsidiandroid.diagnostics import permission_pattern_contract
from obsidiandroid.pipeline.permission_trends.pattern_framework import (
    PATTERN_SCALE_NAME,
    build_pattern_scale_contract,
    pattern_label_for_level,
)

pytestmark = pytest.mark.contract


def test_build_pattern_scale_contract_uses_v3_structural_ladder() -> None:
    payload = build_pattern_scale_contract()
    assert payload["scale_name"] == PATTERN_SCALE_NAME
    assert payload["level_min"] == 0
    assert payload["level_max"] == 9
    assert pattern_label_for_level(0) == "Null / Absent Pattern"
    assert pattern_label_for_level(9) == "Certain Pattern"
    assert len(payload["levels"]) == 10


def test_export_permission_pattern_contract_writes_json_and_md(tmp_path: Path) -> None:
    paths = permission_pattern_contract.export_permission_pattern_contract(
        diagnostics_dir=tmp_path,
        run_id="run_contract",
        profile_id="android_malware_major_families",
    )
    assert len(paths) == 2
    md_text = (tmp_path / "permission_pattern_contract_run_contract.md").read_text(encoding="utf-8")
    assert "V3 Permission Pattern Contract" in md_text
    assert "Null / Absent Pattern" in md_text
    assert "family_vs_global" in md_text
    assert "permission_alone_proves_malware" in md_text


def test_build_permission_pattern_contract_detects_bundle_table_scopes(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "majorfam_benchmark"
    diagnostics_dir = run_root / "diagnostics"
    tables_dir = run_root / "bundles" / "permission_trends" / "tables"
    tables_dir.mkdir(parents=True)
    run_id = "run_bundle_scopes"
    (tables_dir / f"permission_type_enrichment_{run_id}.csv").write_text(
        "permission,pattern_score\nandroid.permission.internet,6\n",
        encoding="utf-8",
    )
    (tables_dir / f"permission_family_enrichment_{run_id}.csv").write_text(
        "permission,pattern_score\nandroid.permission.internet,5\n",
        encoding="utf-8",
    )
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text(
        "type_slug,permission\nbanker,android.permission.internet\n",
        encoding="utf-8",
    )

    payload = permission_pattern_contract.build_permission_pattern_contract_payload(
        run_id=run_id,
        profile_id="android_malware_major_families",
        diagnostics_dir=diagnostics_dir,
    )

    scopes = payload["available_comparison_scopes"]
    assert scopes["type_vs_global"] is True
    assert scopes["family_vs_global"] is True
    assert payload["related_artifacts"]["permission_prevalence_by_type"].startswith(
        "bundles/permission_trends/tables/"
    )
