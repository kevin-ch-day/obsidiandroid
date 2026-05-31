"""Tests for locked cohort profiles and runtime contract validation."""

from __future__ import annotations

import json
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
    assert contract["sample_id_lock"]["lock_manifest_path"].endswith("cohort_lock_manifest.json")
    assert contract["sample_id_lock"]["cohort_hash"]
    assert contract["sample_id_lock"]["taxonomy_hash"]
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


def test_locked_profile_fails_when_manifest_membership_changes_without_new_lock_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The immutable lock manifest must fail if the member list drifts under the same lock version."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    member_path = baseline_dir / "members.csv"
    member_path.write_text("sample_id\n1\n2\n", encoding="utf-8")
    manifest_path = baseline_dir / "cohort_lock_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "lock_version": "v1",
                "profile_id": "locked_profile",
                "contract_id": "locked_contract",
                "created_at_utc": "2026-05-31T00:00:00Z",
                "member_list_path": "members.csv",
                "sample_count": 3,
                "family_count": 2,
                "type_count": 1,
                "cohort_hash": "wrong",
                "taxonomy_hash": "tax123",
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    profile_path = tmp_path / "locked_profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile_id: locked_profile",
                "paper_locked: true",
                "type_slug_filter: all",
                "cohort_gates: {}",
                "model_list:",
                "  - random_forest",
                "paper_lock:",
                "  contract_id: locked_contract",
                f"  baseline_artifact_root: {baseline_dir.as_posix()}",
                f"  cohort_lock_manifest_file: {manifest_path.as_posix()}",
                "  expected_sample_count: 3",
                "  expected_family_count: 2",
                "  expected_type_count: 1",
                f"  sample_id_lock_file: {member_path.as_posix()}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(profile_manager, "PROFILES_DIR", tmp_path)
    with pytest.raises(ValueError, match="sample_count mismatch|cohort_hash mismatch"):
        profile_manager.load_profile("locked_profile")


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


def test_recovered_historical_lock_degrades_when_live_db_is_missing_locked_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovered sample-id locks should degrade to count-only when live DB drift drops locked members."""
    profile = {
        "profile_id": "paper_lock_demo_locked",
        "paper_locked": True,
        "paper_lock": {
            "contract_id": "demo_contract",
            "expected_sample_count": 3,
            "expected_family_count": 2,
            "expected_type_count": 1,
            "sample_id_lock_status": "recovered_from_historical_artifact",
            "sample_id_lock_file": "artifacts/baselines/20260504T044304Z__8c64e6/malicious_temporal_stability_locked_sample_ids.csv",
        },
    }
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["f1", "f1"],
            "type_slug": ["banker", "banker"],
        }
    )
    samples_df.attrs["snapshot_lock"] = {
        "status": "matched",
        "applied": True,
        "matched_sample_count": 2,
        "lock_sample_count": 3,
        "missing_from_db_count": 1,
    }

    monkey_contract = paper_cohort_contract.build_declared_contract(profile)
    lock_path = Path(monkey_contract["sample_id_lock"]["path"])
    def _fake_reader(path: Path) -> dict[str, object]:
        if path == lock_path:
            return {"lock_sample_count": 3, "lock_sample_id_hash": "abc"}
        raise AssertionError(f"unexpected lock path: {path}")

    monkeypatch.setattr(
        paper_cohort_contract,
        "_read_lock_file_metadata",
        _fake_reader,
    )
    contract = paper_cohort_contract.build_runtime_contract(
        profile=profile,
        manifest_context={"db_query_contract": {"version": "v1"}},
        samples_df=samples_df,
        raise_on_mismatch=False,
    )

    assert contract["validation"]["status"] == "degraded_live_db_drift"
    assert contract["validation"]["severity"] == "warning"
    assert contract["cohort_lock_status"] == "count_only_incomplete_sample_lock"
    assert contract["enforcement_level"] == "partial"
    assert contract["sample_id_lock"]["runtime_db_drift"]["missing_from_db_count"] == 1
    assert "Downgrading to count-only lock semantics" in contract["validation"]["warning"]


def test_matched_sample_lock_degrades_when_only_taxonomy_counts_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Curation can change labels inside a fully matched locked sample set."""
    profile = {
        "profile_id": "paper_lock_taxonomy_drift",
        "paper_locked": True,
        "paper_lock": {
            "contract_id": "demo_contract",
            "expected_sample_count": 3,
            "expected_family_count": 2,
            "expected_type_count": 1,
            "sample_id_lock_status": "recovered_from_historical_artifact",
            "sample_id_lock_file": "artifacts/baselines/20260504T044304Z__8c64e6/malicious_temporal_stability_locked_sample_ids.csv",
        },
    }
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_canonical": ["f1", "f2", "f3"],
            "type_slug": ["banker", "banker", "backdoor"],
        }
    )
    samples_df.attrs["snapshot_lock"] = {
        "status": "matched",
        "applied": True,
        "matched_sample_count": 3,
        "lock_sample_count": 3,
        "missing_from_db_count": 0,
    }

    monkey_contract = paper_cohort_contract.build_declared_contract(profile)
    lock_path = Path(monkey_contract["sample_id_lock"]["path"])
    expected_hash = paper_cohort_contract._sample_id_hash(samples_df)

    def _fake_reader(path: Path) -> dict[str, object]:
        if path == lock_path:
            return {"lock_sample_count": 3, "lock_sample_id_hash": expected_hash}
        raise AssertionError(f"unexpected lock path: {path}")

    monkeypatch.setattr(
        paper_cohort_contract,
        "_read_lock_file_metadata",
        _fake_reader,
    )
    contract = paper_cohort_contract.build_runtime_contract(
        profile=profile,
        manifest_context={"db_query_contract": {"version": "v1"}},
        samples_df=samples_df,
    )

    assert contract["validation"]["status"] == "degraded_taxonomy_label_drift"
    assert contract["validation"]["severity"] == "warning"
    assert contract["cohort_lock_status"] == "membership_locked_taxonomy_drift"


def test_immutable_lock_first_materialization_keeps_mismatch_hard_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The manuscript-facing immutable lock must not downgrade into warning-style drift semantics."""
    profile = {
        "profile_id": "paper_lock_demo_locked",
        "paper_locked": True,
        "paper_lock": {
            "contract_id": "demo_contract",
            "expected_sample_count": 3,
            "expected_family_count": 2,
            "expected_type_count": 1,
            "sample_id_lock_status": "recovered_from_historical_artifact",
            "sample_id_lock_file": "artifacts/baselines/20260504T044304Z__8c64e6/malicious_temporal_stability_locked_sample_ids.csv",
        },
    }
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["f1", "f1"],
            "type_slug": ["banker", "banker"],
        }
    )
    samples_df.attrs["snapshot_lock"] = {
        "status": "matched",
        "applied": True,
        "matched_sample_count": 2,
        "lock_sample_count": 3,
        "missing_from_db_count": 1,
    }
    samples_df.attrs["paper_locked_materialization"] = {
        "mode": "immutable_lock_first_broad_catalog_fetch",
        "lock_file_count": 3,
        "materialized_count": 2,
    }

    def _fake_reader(path: Path) -> dict[str, object]:
        if str(path).endswith("malicious_temporal_stability_locked_sample_ids.csv"):
            return {"lock_sample_count": 3, "lock_sample_id_hash": "abc"}
        raise AssertionError(f"unexpected lock path: {path}")

    monkeypatch.setattr(
        paper_cohort_contract,
        "_read_lock_file_metadata",
        _fake_reader,
    )
    contract = paper_cohort_contract.build_runtime_contract(
        profile=profile,
        manifest_context={"db_query_contract": {"version": "v1"}},
        samples_df=samples_df,
        raise_on_mismatch=False,
    )

    assert contract["validation"]["status"] == "mismatch"
    assert contract["validation"]["severity"] == "error"
    assert "sample_count observed=2 expected=3" in contract["validation"]["mismatches"]
    assert "runtime_db_drift" not in contract["sample_id_lock"]


def test_locked_paper_contract_requires_archived_label_snapshot(
    tmp_path: Path,
) -> None:
    """Locked paper runs should fail explicitly when archived labels are unavailable."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    member_path = baseline_dir / "members.csv"
    member_path.write_text("sample_id\n1\n2\n3\n", encoding="utf-8")
    manifest_path = baseline_dir / "cohort_lock_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "lock_version": "v1",
                "profile_id": "locked_profile",
                "contract_id": "locked_contract",
                "canonical_historical_run_id": "",
                "created_at_utc": "2026-05-31T00:00:00Z",
                "member_list_path": "members.csv",
                "sample_count": 3,
                "family_count": 2,
                "type_count": 2,
                "cohort_hash": paper_cohort_contract.hash_payload([1, 2, 3]),
                "taxonomy_hash": "taxhash123",
                "sql_profile_version": "test",
                "profile_version": "test",
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
                "source_artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    profile = {
        "profile_id": "locked_profile",
        "paper_locked": True,
        "paper_lock": {
            "contract_id": "locked_contract",
            "baseline_artifact_root": str(baseline_dir),
            "cohort_lock_manifest_file": str(manifest_path),
            "expected_sample_count": 3,
            "expected_family_count": 2,
            "expected_type_count": 2,
            "expected_type_slugs": ["banker", "spyware"],
            "sample_id_lock_file": str(member_path),
            "sample_id_lock_status": "recovered_from_historical_artifact",
        },
    }
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_canonical": ["f1", "f1", "f2"],
            "type_slug": ["banker", "spyware", "banker"],
        }
    )
    samples_df.attrs["snapshot_lock"] = {
        "status": "matched",
        "applied": True,
        "matched_sample_count": 3,
        "lock_sample_count": 3,
        "missing_from_db_count": 0,
    }
    samples_df.attrs["paper_locked_label_snapshot"] = {
        "status": "archived_label_snapshot_unavailable",
        "available": False,
        "path": "",
        "label_snapshot_hash": "",
    }

    contract = paper_cohort_contract.build_runtime_contract(
        profile=profile,
        manifest_context={"db_query_contract": {"version": "v1"}},
        samples_df=samples_df,
        raise_on_mismatch=False,
    )

    assert contract["validation"]["status"] == "mismatch"
    assert "archived_label_snapshot unavailable" in contract["validation"]["mismatches"]


def test_locked_paper_contract_accepts_matching_archived_label_snapshot(
    tmp_path: Path,
) -> None:
    """Locked paper validation should pass when archived label snapshot and hashes match."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    member_path = baseline_dir / "members.csv"
    member_path.write_text("sample_id\n1\n2\n3\n", encoding="utf-8")
    label_hash = paper_cohort_contract.hash_payload(
        [
            {"sample_id": 1, "family_id": 10, "family_canonical": "f1", "type_slug": "banker"},
            {"sample_id": 2, "family_id": 11, "family_canonical": "f1", "type_slug": "spyware"},
            {"sample_id": 3, "family_id": 12, "family_canonical": "f2", "type_slug": "banker"},
        ]
    )
    manifest_path = baseline_dir / "cohort_lock_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "lock_version": "v1",
                "profile_id": "locked_profile",
                "contract_id": "locked_contract",
                "canonical_historical_run_id": "",
                "created_at_utc": "2026-05-31T00:00:00Z",
                "member_list_path": "members.csv",
                "sample_count": 3,
                "family_count": 2,
                "type_count": 2,
                "cohort_hash": paper_cohort_contract.hash_payload([1, 2, 3]),
                "taxonomy_hash": label_hash,
                "sql_profile_version": "test",
                "profile_version": "test",
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
                "source_artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    profile = {
        "profile_id": "locked_profile",
        "paper_locked": True,
        "paper_lock": {
            "contract_id": "locked_contract",
            "baseline_artifact_root": str(baseline_dir),
            "cohort_lock_manifest_file": str(manifest_path),
            "expected_sample_count": 3,
            "expected_family_count": 2,
            "expected_type_count": 2,
            "expected_type_slugs": ["banker", "spyware"],
            "sample_id_lock_file": str(member_path),
            "sample_id_lock_status": "recovered_from_historical_artifact",
        },
    }
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_id": [10, 11, 12],
            "family_canonical": ["f1", "f1", "f2"],
            "type_slug": ["banker", "spyware", "banker"],
        }
    )
    samples_df.attrs["snapshot_lock"] = {
        "status": "matched",
        "applied": True,
        "matched_sample_count": 3,
        "lock_sample_count": 3,
        "missing_from_db_count": 0,
    }
    samples_df.attrs["paper_locked_label_snapshot"] = {
        "status": "baseline_artifact_label_snapshot",
        "available": True,
        "path": str(baseline_dir / "labels.csv"),
        "label_snapshot_hash": label_hash,
    }

    contract = paper_cohort_contract.build_runtime_contract(
        profile=profile,
        manifest_context={"db_query_contract": {"version": "v1"}},
        samples_df=samples_df,
    )

    assert contract["validation"]["status"] == "match"
    assert contract["enforcement_level"] == "full"
    assert contract["observed"]["sample_count"] == 3
    assert contract["observed"]["family_count"] == 2
    assert contract["observed"]["type_count"] == 2
    assert contract["observed"]["type_slugs"] == ("banker", "spyware")


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
    """Current research profiles should remain clearly outside the locked-cohort contract path."""
    profile = profile_manager.load_profile("malicious_temporal_stability")
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


def test_removed_legacy_locked_profile_alias_fails_to_load() -> None:
    """Removed legacy locked alias ids should no longer resolve."""
    with pytest.raises(FileNotFoundError):
        profile_manager.load_profile("paper2_primary_locked")
