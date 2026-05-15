"""Tests for locked cohort profiles and runtime contract validation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import obsidiandroid.cli.profile_manager as profile_manager
from obsidiandroid.governance import paper_cohort_contract
from obsidiandroid.pipeline.manifest import runtime_support


def test_load_locked_temporal_profile_exposes_contract() -> None:
    """The locked temporal profile should resolve to a real baseline-backed lock file."""
    profile = profile_manager.load_profile("malicious_temporal_stability_locked")
    contract = paper_cohort_contract.build_declared_contract(profile)

    assert profile["paper_locked"] is True
    assert contract["expected"]["sample_count"] == 1226
    assert contract["expected"]["family_count"] == 39
    assert contract["expected"]["type_count"] == 6
    assert contract["contract_id"] == "malicious_temporal_stability_locked_contract"
    assert contract["sample_id_lock"]["path"].endswith("malicious_temporal_stability_locked_sample_ids.csv")
    assert Path(contract["sample_id_lock"]["path"]).exists()


def test_locked_profile_requires_marker_when_paper_lock_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profiles cannot silently carry locked-cohort metadata without the paper_locked marker."""
    profile_path = tmp_path / "broken_profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile_id: broken_profile",
                "evidence_mode: false",
                "type_slug_filter: banker",
                "cohort_gates: {}",
                "model_list:",
                "  - random_forest",
                "paper_lock:",
                "  contract_id: c1",
                "  expected_sample_count: 1",
                "  expected_family_count: 1",
                "  expected_type_count: 1",
                "  sample_id_lock_status: unavailable",
                "  sample_id_lock_todo: pending",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(profile_manager, "PROFILES_DIR", tmp_path)

    with pytest.raises(ValueError, match="paper_lock metadata but is not marked paper_locked"):
        profile_manager.load_profile("broken_profile")


def test_locked_cohort_mismatch_raises_failure() -> None:
    """Observed cohort counts must match the locked cohort contract."""
    profile = {
        "profile_id": "paper_lock_demo",
        "paper_locked": True,
        "paper_lock": {
            "contract_id": "demo_contract",
            "expected_sample_count": 3,
            "expected_family_count": 2,
            "expected_type_count": 1,
            "sample_id_lock_status": "unavailable",
            "sample_id_lock_todo": "pending",
        },
    }
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["f1", "f2"],
            "type_slug": ["banker", "banker"],
        }
    )

    with pytest.raises(ValueError, match="sample_count observed=2 expected=3"):
        paper_cohort_contract.build_runtime_contract(
            profile=profile,
            manifest_context={"db_query_contract": {"version": "v1"}},
            samples_df=samples_df,
        )


def test_manifest_payload_records_expected_cohort_contract_metadata() -> None:
    """Run manifests should carry the declared locked cohort contract metadata."""
    manifest = runtime_support.build_manifest_payload(
        manifest_context={
            "timestamp_utc": "2026-05-14T00:00:00Z",
            "paper_mode": {"resolved_value": False},
            "paper_cohort_contract": {
                "paper_locked": True,
                "contract_id": "malicious_temporal_stability_locked_contract",
                "expected": {"sample_count": 1226, "family_count": 39, "type_count": 6},
                "validation": {"checked": True, "status": "match", "mismatches": []},
            },
            "db_query_contract": {"version": "v1"},
        },
        profile={"profile_id": "malicious_temporal_stability_locked"},
        samples_df=pd.DataFrame({"sample_id": [1, 2], "family_id": [10, 11]}),
        run_id="r1",
        paper_mode=False,
        evidence_mode=False,
        dataset_hash="dh",
        engine_names=[],
        parser_list=[],
        included_engines=0,
        excluded_engines=0,
    )

    assert manifest["paper_cohort_contract"]["paper_locked"] is True
    assert manifest["cohort_contract"]["contract_id"] == "malicious_temporal_stability_locked_contract"
    assert manifest["paper_cohort_contract"]["expected"]["sample_count"] == 1226
    assert manifest["paper_cohort_contract"]["validation"]["status"] == "match"


def test_exploratory_profile_is_not_mistaken_for_paper_locked() -> None:
    """Exploratory profiles should remain clearly outside the locked-cohort contract path."""
    profile = profile_manager.load_profile("research_all_malicious")
    contract = paper_cohort_contract.build_declared_contract(profile)

    assert profile["paper_locked"] is False
    assert contract["paper_locked"] is False
    assert contract["validation"]["status"] == "not_paper_locked"


def test_banker_locked_profile_is_honestly_marked_count_only() -> None:
    """The 2025 banker contract must remain explicitly partial until sample IDs are recovered."""
    profile = profile_manager.load_profile("banker_locked")
    contract = paper_cohort_contract.build_declared_contract(profile)

    assert contract["paper_locked"] is True
    assert contract["contract_status"] == "count_only_incomplete_sample_lock"
    assert contract["enforcement_level"] == "partial"
    assert contract["sample_id_lock"]["present"] is False
    assert contract["contract_id"] == "banker_locked_contract"
    assert "Recover banker cohort sample IDs" in contract["sample_id_lock"]["todo"]


def test_legacy_paper_profile_alias_resolves_to_generic_locked_profile() -> None:
    """Deprecated paper-number profile ids should resolve to the generic locked profile."""
    profile = profile_manager.load_profile("paper2_primary_locked")
    assert profile["profile_id"] == "malicious_temporal_stability_locked"
