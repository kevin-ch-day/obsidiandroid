"""Tests for canonical DL handoff summary exports."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import dl_handoff

pytestmark = pytest.mark.contract


def test_build_dl_handoff_summary_reports_ready_when_seed_chain_complete(tmp_path: Path) -> None:
    run_id = "run_handoff"
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    for filename in (
        f"label_contract_{run_id}.json",
        f"permission_pattern_contract_{run_id}.json",
        f"ml_sample_label_fact_{run_id}.csv",
        f"ml_permission_vocabulary_{run_id}.json",
    ):
        (diagnostics_dir / filename).write_text("{}" if filename.endswith(".json") else "sample_id\n1\n", encoding="utf-8")
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(
            {
                "dataset_hash": "hash123",
                "sample_label_rows": 1,
                "vocabulary_entry_count": 5,
                "seed_artifact_refs": {
                    "label_contract": f"label_contract_{run_id}.json",
                    "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
                    "ml_sample_label_fact": f"ml_sample_label_fact_{run_id}.csv",
                    "ml_permission_vocabulary": f"ml_permission_vocabulary_{run_id}.json",
                },
                "optional_seed_artifact_refs": {},
            }
        ),
        encoding="utf-8",
    )

    payload = dl_handoff.build_dl_handoff_summary_payload(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile={"profile_id": "android_malware_major_families"},
        manifest={"profile_id": "android_malware_major_families", "cohort_size": 1, "dataset_hash": "hash123"},
        manifest_context={"cohort_persistence_source": "runtime_frame"},
    )

    assert payload["dl_seed_status"] == "ready"
    assert payload["caveats"] == []


def test_build_dl_handoff_summary_flags_missing_split_export(tmp_path: Path) -> None:
    run_id = "run_split"
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(
            {
                "dataset_hash": "hash123",
                "sample_label_rows": 1,
                "vocabulary_entry_count": 5,
                "split_hash": "split_abc",
                "seed_artifact_refs": {
                    "label_contract": f"label_contract_{run_id}.json",
                    "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
                    "ml_sample_label_fact": f"ml_sample_label_fact_{run_id}.csv",
                    "ml_permission_vocabulary": f"ml_permission_vocabulary_{run_id}.json",
                },
                "optional_seed_artifact_refs": {},
            }
        ),
        encoding="utf-8",
    )
    for filename in (
        f"label_contract_{run_id}.json",
        f"permission_pattern_contract_{run_id}.json",
        f"ml_sample_label_fact_{run_id}.csv",
        f"ml_permission_vocabulary_{run_id}.json",
    ):
        (diagnostics_dir / filename).write_text("{}" if filename.endswith(".json") else "sample_id\n1\n", encoding="utf-8")

    payload = dl_handoff.build_dl_handoff_summary_payload(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile={"profile_id": "android_malware_type_taxonomy"},
        manifest={
            "profile_id": "android_malware_type_taxonomy",
            "cohort_size": 1,
            "dataset_hash": "hash123",
            "split": {"split_hash": "split_abc"},
        },
        manifest_context={},
    )

    assert payload["dl_seed_status"] == "incomplete"
    assert any("split" in str(item) for item in payload["caveats"])


def test_build_dl_handoff_observability_block_mirrors_summary_fields(tmp_path: Path) -> None:
    run_id = "run_obs_block"
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (diagnostics_dir / f"dl_handoff_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "dl_seed_status": "ready",
                "dataset_hash": "hash_obs",
                "cohort_persistence_source": "diagnostics_export",
                "vocabulary_entry_count": 12,
                "sample_label_rows": 99,
                "split_hash": "split_xyz",
                "split_export_present": True,
            }
        ),
        encoding="utf-8",
    )

    block = dl_handoff.build_dl_handoff_observability_block(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        manifest={"profile_id": "android_malware_major_families", "dataset_hash": "hash_obs"},
        manifest_context={"cohort_persistence_source": "diagnostics_export"},
    )

    assert block["dl_seed_status"] == "ready"
    assert block["dataset_hash"] == "hash_obs"
    assert block["vocabulary_entry_count"] == 12
    assert block["sample_label_rows"] == 99
    assert block["split_export_present"] is True
    assert block["dl_handoff_summary"].endswith(f"dl_handoff_summary_{run_id}.json")


def test_research_validity_bundle_resolves_samples_from_cohort_membership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from obsidiandroid.diagnostics.research_validity import bundle as rv_bundle

    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    (diagnostics_dir / "cohort_membership.csv").write_text(
        "sample_id,family_id,type_slug\n1,10,banker\n",
        encoding="utf-8",
    )
    manifest_context: dict[str, object] = {}
    artifact_list: list[str] = []
    seen: dict[str, object] = {}

    monkeypatch.setattr(rv_bundle, "finalize_cohort_funnel_dict", lambda _ctx: None)
    monkeypatch.setattr(rv_bundle, "write_cohort_funnel_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_signal_decomposition_artifacts", lambda **_kwargs: [])
    def _capture_samples(**_kwargs: object) -> Path:
        seen["samples"] = _kwargs.get("samples_df")
        return tmp_path / "audit.csv"

    monkeypatch.setattr(rv_bundle, "write_permission_feature_audit_csv", _capture_samples)
    monkeypatch.setattr(rv_bundle, "write_permission_intel_audit_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_validity_figures", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_type_permission_figure_bundle", lambda **_kwargs: None)
    monkeypatch.setattr(rv_bundle, "write_paper_claim_audit_md", lambda **_kwargs: tmp_path / "claim.md")
    monkeypatch.setattr(rv_bundle, "write_headline_vs_ablation_contract_reports", lambda **_kwargs: (None, None, {}))
    monkeypatch.setattr(rv_bundle, "write_taxonomy_type_authority_reports", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rv_bundle, "write_hostile_audit_bundle", lambda **_kwargs: [])

    rv_bundle.write_research_validity_bundle(
        run_root=tmp_path,
        diagnostics_dir=diagnostics_dir,
        run_id="run_reload_rv",
        manifest_context=manifest_context,
        manifest={"profile_id": "android_malware_major_families", "cohort_size": 1},
        samples_df=None,
        artifact_list=artifact_list,
        paper_mode=False,
    )

    assert isinstance(seen.get("samples"), pd.DataFrame)
    assert len(seen["samples"]) == 1
