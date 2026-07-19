"""Tests for the read-only legacy canonical-artifact planner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BASELINE_JSON = Path("artifacts/baselines/canonical_db_import_dry_run_fixture_slots.json")

from obsidiandroid.common.run_slots import _SLOT_BY_PROFILE
from scripts import import_canonical_runs_to_db as importer

pytestmark = pytest.mark.contract

FIXTURES_ROOT = Path("artifacts/baselines/canonical_slots")


def _write_minimal_slot(
    runs_root: Path,
    *,
    profile_id: str,
    run_id: str,
    pipeline_status: str = "PASS",
) -> Path:
    run_slot = _SLOT_BY_PROFILE[profile_id]
    slot_root = runs_root / run_slot
    diagnostics_dir = slot_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (slot_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "profile_id": profile_id, "dataset_hash": f"hash_{run_id}"}),
        encoding="utf-8",
    )
    for stem in ("label_contract", "permission_pattern_contract"):
        (diagnostics_dir / f"{stem}_{run_id}.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": profile_id,
                "sample_label_rows": 1,
                "dataset_hash": f"hash_{run_id}",
                "seed_artifact_refs": {
                    "label_contract": f"label_contract_{run_id}.json",
                    "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
                    "ml_sample_label_fact": f"ml_sample_label_fact_{run_id}.csv",
                    "ml_permission_vocabulary": f"ml_permission_vocabulary_{run_id}.json",
                },
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv").write_text(
        "sample_id,supervised_label,supervised_label_namespace\n1,alpha,malware_family\n",
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json").write_text(
        json.dumps({"entry_count": 1, "entries": [{"entry_kind": "permission", "permission": "p"}]}),
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps({"pipeline_status": pipeline_status, "research_validity_status": "PASS"}),
        encoding="utf-8",
    )
    return slot_root


@pytest.mark.parametrize(
    "slot_name",
    [
        "majorfam_benchmark",
        "typelevel_benchmark",
        "expandedfam_exploratory",
        "allcurrent_diagnostic",
    ],
)
def test_fixture_slots_produce_unblocked_dry_run_plan(slot_name: str) -> None:
    slot_root = FIXTURES_ROOT / slot_name
    if not (slot_root / "run_manifest.json").is_file():
        pytest.skip(f"missing fixture slot {slot_root}")

    plan = importer.build_import_plan(slot_root, release_tag="v2.2.0")

    assert plan.run_id
    assert plan.profile_id
    assert not plan.blocked
    assert plan.planned_rows["runs"] == 1
    assert plan.planned_rows["profiles"] == 1
    assert plan.planned_rows["release_manifests"] == 1
    assert plan.planned_rows["sample_label_facts"] >= 1
    assert len(plan.sample_ids) >= 1


def test_dry_run_blocks_on_missing_required_artifacts(tmp_path: Path) -> None:
    slot_root = _write_minimal_slot(
        tmp_path,
        profile_id="android_malware_major_families",
        run_id="20260606T500000Z__minimal",
    )
    (slot_root / "diagnostics" / "ml_run_manifest_20260606T500000Z__minimal.json").unlink()

    plan = importer.build_import_plan(slot_root, strict=True)

    assert plan.blocked
    assert any("missing required artifacts" in item for item in plan.blocking_errors)


def test_dry_run_blocks_on_non_tag_ready_pipeline_status(tmp_path: Path) -> None:
    slot_root = _write_minimal_slot(
        tmp_path,
        profile_id="android_malware_major_families",
        run_id="20260606T500001Z__fail",
        pipeline_status="FAIL",
    )

    plan = importer.build_import_plan(slot_root, strict=True)

    assert plan.blocked
    assert any("pipeline_status" in item for item in plan.blocking_errors)


def test_allow_mixed_permits_non_tag_ready_pipeline_status(tmp_path: Path) -> None:
    slot_root = _write_minimal_slot(
        tmp_path,
        profile_id="android_malware_major_families",
        run_id="20260606T500002Z__mixed",
        pipeline_status="FAIL",
    )

    plan = importer.build_import_plan(slot_root, strict=True, allow_mixed=True)

    assert not plan.blocked


def test_duplicate_sample_id_is_blocking(tmp_path: Path) -> None:
    slot_root = _write_minimal_slot(
        tmp_path,
        profile_id="android_malware_major_families",
        run_id="20260606T500003Z__dup",
    )
    label_path = slot_root / "diagnostics" / "ml_sample_label_fact_20260606T500003Z__dup.csv"
    label_path.write_text(
        "sample_id,supervised_label,supervised_label_namespace\n1,a,malware_family\n1,b,malware_family\n",
        encoding="utf-8",
    )

    plan = importer.build_import_plan(slot_root)

    assert plan.blocked
    assert any("duplicate sample_id" in item for item in plan.blocking_errors)


def test_dry_run_all_slots_cli_reports_ready_for_minimal_tree(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    for idx, profile_id in enumerate(importer.CANONICAL_PROFILES):
        _write_minimal_slot(
            runs_root,
            profile_id=profile_id,
            run_id=f"20260606T60000{idx}Z__slot{idx}",
        )

    code = importer.dry_run_all_slots_cli(runs_root=runs_root, release_tag="v2.2.0")

    assert code == 0


def test_fixture_baseline_json_matches_live_dry_run() -> None:
    if not BASELINE_JSON.is_file():
        pytest.skip("missing frozen dry-run baseline artifact")
    expected = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    runs_root = Path(expected["runs_root"])
    if not runs_root.is_file() and not runs_root.is_dir():
        runs_root = Path(importer.REPO_ROOT) / expected["runs_root"]
    if not runs_root.is_dir():
        pytest.skip("baseline runs_root missing")

    live_payload = {
        "plan_scope": importer.PLAN_SCOPE,
        "runs_root": importer._display_path(runs_root),
        "release_tag": expected.get("release_tag", ""),
        "profiles": [],
    }
    for profile_id, plan in importer.dry_run_all_slots(
        runs_root=runs_root,
        release_tag=str(expected.get("release_tag", "") or ""),
    ):
        entry: dict[str, object] = {"profile_id": profile_id}
        if plan is None:
            entry["status"] = "skipped"
        else:
            entry["status"] = "blocked" if plan.blocked else "ready"
            entry.update(importer.import_plan_to_dict(plan, release_tag=str(expected.get("release_tag", "") or "")))
        live_payload["profiles"].append(entry)

    assert live_payload["plan_scope"] == expected["plan_scope"]
    assert len(live_payload["profiles"]) == len(expected["profiles"])
    for live_entry, expected_entry in zip(live_payload["profiles"], expected["profiles"]):
        assert live_entry["profile_id"] == expected_entry["profile_id"]
        assert live_entry["status"] == expected_entry["status"]
        assert live_entry.get("run_id") == expected_entry.get("run_id")
        assert live_entry.get("planned_rows") == expected_entry.get("planned_rows")
        assert live_entry.get("blocked") is expected_entry.get("blocked")


def test_dry_run_counts_sample_permission_facts_when_export_present(tmp_path: Path) -> None:
    slot_root = _write_minimal_slot(
        tmp_path,
        profile_id="android_malware_major_families",
        run_id="20260606T700000Z__perm",
    )
    diagnostics_dir = slot_root / "diagnostics"
    permission_path = diagnostics_dir / "ml_sample_permission_feature_20260606T700000Z__perm.csv"
    permission_path.write_text(
        "run_id,profile_id,sample_id,sha256,permission_name,permission_present,"
        "permission_authority_bucket,permission_risk_tier,permission_source\n"
        "20260606T700000Z__perm,android_malware_major_families,1,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,"
        "android.permission.internet,1,unknown,unknown,aligned_features\n"
        "20260606T700000Z__perm,android_malware_major_families,1,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,"
        "android.permission.read_sms,1,unknown,unknown,aligned_features\n",
        encoding="utf-8",
    )

    plan = importer.build_import_plan(slot_root)

    assert not plan.blocked
    assert plan.planned_rows["sample_permission_facts"] == 2
    assert "ml_sample_permission_feature" in plan.artifacts_optional_present


def test_missing_permission_export_stays_warning_not_blocker(tmp_path: Path) -> None:
    slot_root = _write_minimal_slot(
        tmp_path,
        profile_id="android_malware_major_families",
        run_id="20260606T700001Z__legacy",
    )

    plan = importer.build_import_plan(slot_root)

    assert not plan.blocked
    assert plan.planned_rows["sample_permission_facts"] == 0
    assert any("ml_sample_permission_feature missing" in item for item in plan.warnings)


def test_import_plan_to_dict_round_trip_fields(tmp_path: Path) -> None:
    slot_root = _write_minimal_slot(
        tmp_path,
        profile_id="android_malware_type_taxonomy",
        run_id="20260606T500004Z__dict",
    )
    plan = importer.build_import_plan(slot_root, release_tag="v2.2.0")
    payload = importer.import_plan_to_dict(plan, release_tag="v2.2.0")

    assert payload["plan_scope"] == importer.PLAN_SCOPE
    assert payload["run_id"] == "20260606T500004Z__dict"
    assert payload["blocked"] is False
    assert payload["planned_rows"]["samples"] == 1
