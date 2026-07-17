"""Integration tests for canonical hard-fail export policies."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import ml_seed_exports
from obsidiandroid.pipeline.manifest import stage_manifest_writers as smw

pytestmark = pytest.mark.contract


def _stub_hygiene_bundle_dependencies(monkeypatch: pytest.MonkeyPatch, *, run_root: Path, diagnostics_dir: Path) -> None:
    from obsidiandroid.diagnostics import diagnostic_provenance, output_inventory
    from obsidiandroid.observability.pipeline_observability import finalize as obs_finalize
    from obsidiandroid.observability.pipeline_observability import run_health

    monkeypatch.setattr(smw, "emit_run_authority_coverage_bundle", lambda **_kwargs: {})
    monkeypatch.setattr(output_inventory, "write_virtual_layout", lambda _run_root: _run_root / "virtual_layout.json")
    monkeypatch.setattr(output_inventory, "write_artifact_inventory_bundle", lambda **_kwargs: ([], {}))
    monkeypatch.setattr(
        output_inventory,
        "write_run_evidence_index_md",
        lambda **_kwargs: run_root / "run_evidence_index.md",
    )
    monkeypatch.setattr(
        output_inventory,
        "write_run_science_index_md",
        lambda **_kwargs: diagnostics_dir / "run_science_index.md",
    )
    monkeypatch.setattr(output_inventory, "print_output_hygiene_terminal_summary", lambda **_kwargs: None)
    monkeypatch.setattr(diagnostic_provenance, "record_diagnostic_provenance", lambda **_kwargs: None)
    monkeypatch.setattr(
        obs_finalize,
        "finalize_pipeline_observability",
        lambda **_kwargs: diagnostics_dir / "run_observability_summary.json",
    )
    monkeypatch.setattr(run_health, "print_unified_run_health", lambda **_kwargs: None)


def test_canonical_hygiene_bundle_reraises_ml_seed_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "run_canonical_fail"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"label_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"permission_pattern_contract_{run_id}.json").write_text("{}", encoding="utf-8")

    _stub_hygiene_bundle_dependencies(monkeypatch, run_root=run_root, diagnostics_dir=diagnostics_dir)

    def _raise_seed_export(**_kwargs) -> list[str]:
        raise ml_seed_exports.MlSeedExportError("seed export blocked for test")

    monkeypatch.setattr(ml_seed_exports, "export_ml_seed_artifacts", _raise_seed_export)

    with pytest.raises(ml_seed_exports.MlSeedExportError, match="seed export blocked"):
        smw.finalize_output_hygiene_bundle(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile={"profile_id": "android_malware_major_families"},
            manifest={"cohort_size": 1, "trained_models": []},
            manifest_context={},
            artifact_list=[],
            compliance_report=None,
            paper_mode=False,
            evidence_mode=False,
            result_code=0,
            samples_df=pd.DataFrame({"sample_id": [1], "family_id": [10]}),
        )


def test_non_canonical_hygiene_bundle_swallows_ml_seed_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "run_dev_smoke"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"label_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"permission_pattern_contract_{run_id}.json").write_text("{}", encoding="utf-8")

    _stub_hygiene_bundle_dependencies(monkeypatch, run_root=run_root, diagnostics_dir=diagnostics_dir)

    def _raise_seed_export(**_kwargs) -> list[str]:
        raise ml_seed_exports.MlSeedExportError("seed export blocked for test")

    monkeypatch.setattr(ml_seed_exports, "export_ml_seed_artifacts", _raise_seed_export)

    smw.finalize_output_hygiene_bundle(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile={"profile_id": "dev_smoke"},
        manifest={"cohort_size": 1, "trained_models": []},
        manifest_context={},
        artifact_list=[],
        compliance_report=None,
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        samples_df=pd.DataFrame({"sample_id": [1], "family_id": [10]}),
    )


def test_finalize_output_hygiene_bundle_refreshes_label_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "run_label_refresh"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "dataset_hash": "hash_refresh"}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"permission_pattern_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"label_contract_{run_id}.json").write_text(
        json.dumps({"included_sample_count": 1}),
        encoding="utf-8",
    )

    _stub_hygiene_bundle_dependencies(monkeypatch, run_root=run_root, diagnostics_dir=diagnostics_dir)
    monkeypatch.setattr(
        ml_seed_exports,
        "export_ml_seed_artifacts",
        lambda **_kwargs: [str(diagnostics_dir / f"ml_run_manifest_{run_id}.json")],
    )
    monkeypatch.setattr(
        smw.app_config,
        "RUNTIME_MIN_FAMILY_SUPPORT",
        3,
        raising=False,
    )

    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_id": [10, 10, 11],
            "family_canonical": ["Alpha", "Alpha", "Beta"],
            "type_slug": ["banker", "banker", "rat"],
        }
    )

    smw.finalize_output_hygiene_bundle(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile={"profile_id": "android_malware_major_families"},
        manifest={"cohort_size": 3, "trained_models": [], "dataset_hash": "hash_refresh"},
        manifest_context={"dataset_hash": "hash_refresh", "cohort_persistence_source": "runtime_frame"},
        artifact_list=[],
        compliance_report=None,
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        samples_df=samples_df,
    )

    payload = json.loads((diagnostics_dir / f"label_contract_{run_id}.json").read_text(encoding="utf-8"))
    assert int(payload.get("present_sample_count", 0) or 0) == 3


def test_permission_vocabulary_enriches_from_prevalence_tables(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "allcurrent_diagnostic"
    diagnostics_dir = run_root / "diagnostics"
    contracts_dir = run_root / "bundles" / "permission_trends" / "contracts"
    tables_dir = run_root / "bundles" / "permission_trends" / "tables"
    contracts_dir.mkdir(parents=True)
    tables_dir.mkdir(parents=True)
    run_id = "run_vocab_enriched"
    (contracts_dir / f"permission_alias_map_{run_id}.json").write_text(
        json.dumps(
            {
                "permission_alias_map_version": "perm_alias_v1",
                "alias_map": {
                    "android.permission.install_packages": "android.permission.request_install_packages",
                },
            }
        ),
        encoding="utf-8",
    )
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text(
        "type_slug,permission,n_samples,permission_positive_count,prevalence_pct\n"
        "banker,android.permission.internet,10,8,80.0\n"
        "banker,android.permission.install_packages,10,2,20.0\n"
        "rat,android.permission.camera,5,1,20.0\n",
        encoding="utf-8",
    )
    (tables_dir / f"permission_prevalence_by_family_{run_id}.csv").write_text(
        "family_canonical,permission,n_samples,permission_positive_count,prevalence_pct\n"
        "Alpha,android.permission.internet,4,4,100.0\n"
        "Alpha,android.permission.read_sms,4,1,25.0\n",
        encoding="utf-8",
    )

    vocab = ml_seed_exports._build_permission_vocabulary(diagnostics_dir, run_id)

    assert vocab["vocabulary_version"] == "ml_permission_vocabulary_v2"
    assert vocab["alias_entry_count"] == 1
    assert vocab["permission_entry_count"] == 3
    assert vocab["entry_count"] == 4
    permissions = {
        row["canonical_permission"]
        for row in vocab["entries"]
        if row.get("entry_kind") == "permission"
    }
    assert permissions == {
        "android.permission.internet",
        "android.permission.camera",
        "android.permission.read_sms",
    }
    internet = next(
        row for row in vocab["entries"] if row.get("canonical_permission") == "android.permission.internet"
    )
    assert internet["max_prevalence_pct"] == 100.0
    assert internet["source_scope"] == ["family_level", "type_level"]
