"""Tests for feature lineage reporting (no pipeline run required)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.diagnostics import feature_lineage_report as flr


def test_classify_permission_and_metadata() -> None:
    p = flr.classify_column_lineage("perm__read_sms")
    assert p["lineage_group"] == "permission_intel_binary"
    assert p["source_system"] == "permission_intel_db"

    c = flr.classify_column_lineage("perm__total_count")
    assert c["lineage_group"] == "permission_intel_counts"

    m = flr.classify_column_lineage("meta__vt_malicious_count")
    assert m["lineage_group"] == "catalog_metadata_vt_summary"
    assert m["source_system"] == "primary_db_sample_catalog_join"


def test_classify_vendor_parsed_prefixes() -> None:
    for col in ("parsed_family_drweb", "threat_class_tencent", "malware_type_k7gw"):
        d = flr.classify_column_lineage(col)
        assert d["lineage_group"] == "vendor_parsed_av_strings"
        assert "ground-truth" in d["notes"]


def test_classify_enriched_scores() -> None:
    d = flr.classify_column_lineage("risk_score")
    assert d["lineage_group"] == "av_derived_scores"


def test_build_report_from_fixture_contracts(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    modality = {
        "fusion_modality": {
            "feature_count_total": 10,
            "feature_count_permission": 4,
            "feature_count_av": 3,
            "feature_count_other": 3,
            "matrix_shape": {"rows": 100, "columns": 10},
        },
        "permission_modality": {"feature_count_raw": 4},
        "av_modality": {},
    }
    contract = {
        "feature_columns": [
            "parsed_family_a",
            "perm__x",
            "meta__vt_tag_count",
            "risk_score",
            "drweb",
        ],
        "selected_vendors": ["a"],
        "selected_vendor_count": 1,
    }
    (diag / "modality_method_contract.json").write_text(json.dumps(modality), encoding="utf-8")
    (diag / "feature_contract.json").write_text(json.dumps(contract), encoding="utf-8")

    built = flr.build_feature_lineage_report(diag)
    assert built["summary"]["training_stage_counts"]["feature_columns_after_pruning"] == 5
    groups = built["summary"]["lineage_group_counts_training"]
    assert groups.get("vendor_parsed_av_strings") == 1
    assert groups.get("permission_intel_binary") == 1


def test_write_artifacts(tmp_path: Path) -> None:
    diag = tmp_path / "d"
    diag.mkdir(parents=True)
    (diag / "modality_method_contract.json").write_text(
        json.dumps({"fusion_modality": {"feature_count_total": 2}}),
        encoding="utf-8",
    )
    (diag / "feature_contract.json").write_text(
        json.dumps({"feature_columns": ["perm__a", "meta__b"], "selected_vendors": []}),
        encoding="utf-8",
    )
    jp, cp = flr.write_feature_lineage_artifacts(diag)
    assert jp.is_file() and cp.is_file()
    payload = json.loads(jp.read_text(encoding="utf-8"))
    assert "column_lineage" in payload
    assert len(payload["column_lineage"]) == 2
