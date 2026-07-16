"""Tests for permission-trends warehouse backfill helpers."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.maintenance import backfill_permission_trends_warehouse as backfill


def test_artifact_path_from_manifest_resolves_relative_path(tmp_path: Path) -> None:
    """Manifest resolver should map artifact id to existing bundle file."""
    bundle_dir = tmp_path / "permission_trends"
    table_path = bundle_dir / "tables" / "type_permission_prevalence.latest.csv"
    table_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.write_text("a,b\n1,2\n", encoding="utf-8")
    manifest = {
        "artifacts": [
            {
                "artifact_id": "type_permission_prevalence",
                "relative_path": "tables/type_permission_prevalence.latest.csv",
            }
        ]
    }

    resolved = backfill._artifact_path_from_manifest(  # pylint: disable=protected-access
        bundle_dir,
        manifest,
        "type_permission_prevalence",
    )
    assert resolved == table_path.resolve()


def test_artifact_path_from_manifest_uses_exact_id_not_behavior_safe_redirect(tmp_path: Path) -> None:
    """Warehouse backfill should preserve exact artifact ids by default."""
    bundle_dir = tmp_path / "permission_trends"
    tables = bundle_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    mixed_path = tables / "permission_signal_prevalence_by_type.latest.csv"
    safe_path = tables / "permission_signal_prevalence_by_type_behavior_safe.latest.csv"
    mixed_path.write_text("a,b\n1,2\n", encoding="utf-8")
    safe_path.write_text("a,b\n1,2\n", encoding="utf-8")
    manifest = {
        "artifacts": [
            {
                "artifact_id": "permission_signal_prevalence_by_type",
                "relative_path": "tables/permission_signal_prevalence_by_type.latest.csv",
                "preferred_behavior_claim_artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
            },
            {
                "artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
                "relative_path": "tables/permission_signal_prevalence_by_type_behavior_safe.latest.csv",
                "preferred_behavior_claim_artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
            },
        ]
    }

    resolved = backfill._artifact_path_from_manifest(  # pylint: disable=protected-access
        bundle_dir,
        manifest,
        "permission_signal_prevalence_by_type",
    )
    assert resolved == mixed_path.resolve()


def test_resolve_top_family_stem_from_manifest_detects_top_value() -> None:
    """Top-family stem resolver should detect top{N} ids from manifest entries."""
    manifest = {
        "artifacts": [
            {"artifact_id": "family_permission_profiles_top12"},
            {"artifact_id": "family_jsd_matrix_top12"},
        ]
    }
    out = backfill._resolve_top_family_stem_from_manifest(  # pylint: disable=protected-access
        manifest,
        prefix="family_jsd_matrix",
        fallback_stem="family_jsd_matrix_topN",
    )
    assert out == "family_jsd_matrix_top12"


def test_load_bundle_manifest_reads_contract_file(tmp_path: Path) -> None:
    """Loader should read canonical bundle manifest when present."""
    bundle_dir = tmp_path / "permission_trends"
    contracts_dir = bundle_dir / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    payload = {"bundle_contract_version": "v1", "artifacts": []}
    (contracts_dir / "permission_trends_bundle_manifest.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    out = backfill._load_bundle_manifest(bundle_dir)  # pylint: disable=protected-access
    assert out.get("bundle_contract_version") == "v1"
