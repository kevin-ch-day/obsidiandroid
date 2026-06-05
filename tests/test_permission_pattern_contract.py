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
