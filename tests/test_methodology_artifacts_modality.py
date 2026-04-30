"""Tests for modality method contract export artifact."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.orchestration import methodology_artifacts


def test_export_modality_method_contract_writes_expected_fields(tmp_path: Path) -> None:
    """Exporter should emit run-scoped modality contract with dimensions/hashes."""
    permission_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "perm__internet": [1, 1],
            "perm__read_sms": [0, 1],
            "perm__dangerous_count": [0, 1],
        }
    )
    fusion_df = pd.DataFrame(
        {
            "parsed_family_vendor_a": [1, 2],
            "threat_class_vendor_a": [0, 1],
            "malware_type_vendor_a": [0, 1],
            "perm__internet": [1, 1],
            "perm__read_sms": [0, 1],
            "meta__vt_tag_count": [3, 5],
        },
        index=[1, 2],
    )

    out = methodology_artifacts.export_modality_method_contract(
        permission_df=permission_df,
        fusion_feature_df=fusion_df,
        run_id="run_modality",
        output_dir=str(tmp_path / "diagnostics"),
    )
    out_path = Path(out)
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_modality"
    assert payload["permission_modality"]["feature_count_raw"] == 3
    assert payload["av_modality"]["feature_count_in_fusion"] == 3
    assert payload["fusion_modality"]["feature_count_total"] == 6
    assert payload["fusion_modality"]["feature_count_permission"] == 2
    assert payload["fusion_modality"]["feature_count_other"] == 1
