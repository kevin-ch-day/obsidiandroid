"""Tests for offline canonical run validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.common.run_slots import _SLOT_BY_PROFILE
from scripts.dev import validate_canonical_runs as canonical_validate

pytestmark = pytest.mark.contract


def _write_minimal_slot(
    runs_root: Path,
    *,
    profile_id: str,
    run_id: str,
) -> Path:
    run_slot = _SLOT_BY_PROFILE[profile_id]
    slot_root = runs_root / run_slot
    diagnostics_dir = slot_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (slot_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "profile_id": profile_id, "dataset_hash": f"hash_{run_id}"}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"label_contract_{run_id}.json").write_text(
        json.dumps(
            {
                "profile_role": "benchmark surface",
                "target_label_namespace": "malware_family",
                "claim_surface_label": "Support-gated benchmark cohort",
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"permission_pattern_contract_{run_id}.json").write_text(
        json.dumps({"pattern_scale": {"levels": [{"level": i} for i in range(10)]}}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(
            {
                "seed_artifact_refs": {
                    "label_contract": f"label_contract_{run_id}.json",
                    "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
                    "ml_sample_label_fact": f"ml_sample_label_fact_{run_id}.csv",
                    "ml_permission_vocabulary": f"ml_permission_vocabulary_{run_id}.json",
                },
                "optional_seed_artifact_refs": {},
                "sample_label_rows": 1,
                "dataset_hash": f"hash_{run_id}",
                "vocabulary_entry_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json").write_text(
        json.dumps({"entry_count": 1, "entries": [{"alias_from": "a", "alias_to": "b"}]}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv").write_text("sample_id\n1\n", encoding="utf-8")
    (diagnostics_dir / f"dl_handoff_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "dl_seed_status": "ready",
                "dataset_hash": f"hash_{run_id}",
                "vocabulary_entry_count": 1,
                "sample_label_rows": 1,
                "caveats": [],
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "pipeline_status": "PASS",
                "dataset_hash": f"hash_{run_id}",
                "dl_handoff": {
                    "dataset_hash": f"hash_{run_id}",
                    "dl_seed_status": "ready",
                    "ml_run_manifest": str(diagnostics_dir / f"ml_run_manifest_{run_id}.json"),
                    "ml_sample_label_fact": str(diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv"),
                    "ml_permission_vocabulary": str(diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json"),
                    "dl_handoff_summary": str(diagnostics_dir / f"dl_handoff_summary_{run_id}.json"),
                },
            }
        ),
        encoding="utf-8",
    )
    contracts_dir = slot_root / "bundles" / "permission_trends" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / f"permission_alias_map_{run_id}.json").write_text(
        json.dumps(
            {
                "permission_alias_map_version": "perm_alias_v1",
                "alias_map": {"android.permission.install_packages": "android.permission.request_install_packages"},
            }
        ),
        encoding="utf-8",
    )
    return slot_root


def test_verify_only_passes_for_minimal_canonical_slot(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    for idx, profile_id in enumerate(canonical_validate.CANONICAL_PROFILES):
        _write_minimal_slot(
            runs_root,
            profile_id=profile_id,
            run_id=f"20260606T00000{idx}Z__slot{idx}",
        )

    code = canonical_validate.verify_only_cli(runs_root=runs_root)

    assert code == 0


def test_run_profiles_cli_uses_canonical_pipeline_entrypoint(monkeypatch) -> None:
    """The canonical runner must not depend on the repo-root ``main`` compatibility shim."""
    from obsidiandroid.cli import pipeline_entry

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(canonical_validate, "CANONICAL_PROFILES", ("profile_a",))
    monkeypatch.setattr(canonical_validate.app_config, "RUNTIME_RUN_ID", "run_a", raising=False)
    monkeypatch.setattr(
        pipeline_entry,
        "run_pipeline",
        lambda **kwargs: calls.append(kwargs) or 0,
    )
    monkeypatch.setattr(
        canonical_validate,
        "_verify_run",
        lambda profile_id, run_id: {"profile_id": profile_id, "run_id": run_id, "ok": True},
    )

    assert canonical_validate.run_profiles_cli() == 0
    assert calls == [{"profile_ref": "profile_a", "selected_models": ["logistic_regression"]}]


def test_verify_only_reads_vocabulary_from_bundle_contracts_only(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    profile_id = "android_malware_major_families"
    run_id = "20260606T200000Z__bundle_only"
    slot_root = _write_minimal_slot(runs_root, profile_id=profile_id, run_id=run_id)
    (slot_root / "diagnostics" / f"ml_permission_vocabulary_{run_id}.json").unlink()
    contracts_dir = slot_root / "bundles" / "permission_trends" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    (contracts_dir / f"permission_alias_map_{run_id}.json").write_text(
        json.dumps(
            {
                "permission_alias_map_version": "perm_alias_v1",
                "alias_map": {"android.permission.install_packages": "android.permission.request_install_packages"},
            }
        ),
        encoding="utf-8",
    )

    summary = canonical_validate._verify_slot_profile(profile_id=profile_id, runs_root=runs_root)

    assert summary["permission_vocabulary_entries"] == 1
    assert summary["ok"] is True


def test_verify_run_flags_stale_ml_run_manifest_vocabulary_count(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    profile_id = "android_malware_major_families"
    run_id = "20260606T300000Z__stale_manifest"
    slot_root = _write_minimal_slot(runs_root, profile_id=profile_id, run_id=run_id)
    diagnostics_dir = slot_root / "diagnostics"
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(
            {
                "seed_artifact_refs": {
                    "label_contract": f"label_contract_{run_id}.json",
                    "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
                    "ml_sample_label_fact": f"ml_sample_label_fact_{run_id}.csv",
                    "ml_permission_vocabulary": f"ml_permission_vocabulary_{run_id}.json",
                },
                "optional_seed_artifact_refs": {},
                "sample_label_rows": 1,
                "vocabulary_entry_count": 1,
            }
        ),
        encoding="utf-8",
    )
    tables_dir = slot_root / "bundles" / "permission_trends" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text(
        "type_slug,permission,n_samples,permission_positive_count,prevalence_pct\n"
        "banker,android.permission.internet,10,8,80.0\n"
        "banker,android.permission.camera,10,1,10.0\n",
        encoding="utf-8",
    )

    summary = canonical_validate._verify_run(profile_id, run_id, diagnostics_dir=diagnostics_dir, run_root=slot_root)

    assert summary["permission_vocabulary_entries"] > summary["manifest_vocabulary_entries"]
    assert any("vocabulary_entry_count is stale" in item for item in summary["caveats"])
    assert summary["ok"] is True
    strict_summary = canonical_validate._verify_run(
        profile_id,
        run_id,
        diagnostics_dir=diagnostics_dir,
        run_root=slot_root,
        strict=True,
    )
    assert strict_summary["ok"] is False


def test_verify_only_fails_when_required_contract_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    for idx, profile_id in enumerate(canonical_validate.CANONICAL_PROFILES):
        _write_minimal_slot(
            runs_root,
            profile_id=profile_id,
            run_id=f"20260606T10000{idx}Z__slot{idx}",
        )
    slot_root = runs_root / _SLOT_BY_PROFILE["android_malware_all_current"]
    all_current_run_id = "20260606T100003Z__slot3"
    (slot_root / "diagnostics" / f"label_contract_{all_current_run_id}.json").unlink(missing_ok=True)

    code = canonical_validate.verify_only_cli(runs_root=runs_root)

    assert code == 1


def test_verify_only_strict_fails_when_observability_dl_seed_status_not_ready(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    profile_id = "android_malware_major_families"
    run_id = "20260606T100001Z__slot1"
    slot_root = _write_minimal_slot(runs_root, profile_id=profile_id, run_id=run_id)
    obs_path = slot_root / "diagnostics" / "run_observability_summary.json"
    obs_payload = json.loads(obs_path.read_text(encoding="utf-8"))
    obs_payload["dl_handoff"]["dl_seed_status"] = "incomplete"
    obs_path.write_text(json.dumps(obs_payload), encoding="utf-8")

    code = canonical_validate.verify_only_cli(runs_root=runs_root, strict=True)

    assert code == 1


def test_verify_only_strict_fails_when_observability_dl_seed_status_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    profile_id = "android_malware_major_families"
    run_id = "20260606T100001Z__slot1"
    slot_root = _write_minimal_slot(runs_root, profile_id=profile_id, run_id=run_id)
    obs_path = slot_root / "diagnostics" / "run_observability_summary.json"
    obs_payload = json.loads(obs_path.read_text(encoding="utf-8"))
    obs_payload["dl_handoff"].pop("dl_seed_status", None)
    obs_path.write_text(json.dumps(obs_payload), encoding="utf-8")

    code = canonical_validate.verify_only_cli(runs_root=runs_root, strict=True)

    assert code == 1


def test_verify_only_skip_missing_slots_treats_absent_run_manifest_as_skipped(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    _write_minimal_slot(
        runs_root,
        profile_id="android_malware_all_current",
        run_id="20260606T100003Z__slot3",
    )

    code = canonical_validate.verify_only_cli(runs_root=runs_root, skip_missing_slots=True)

    assert code == 0


def test_resolve_reference_path_accepts_repo_relative_and_embedded_artifact_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    artifact = repo_root / "artifacts" / "baselines" / "seed.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")

    assert canonical_validate._resolve_reference_path("artifacts/baselines/seed.json", repo_root=repo_root) == artifact
    assert (
        canonical_validate._resolve_reference_path(
            "/tmp/elsewhere/artifacts/baselines/seed.json",
            repo_root=repo_root,
        )
        == artifact
    )
    assert canonical_validate._resolve_reference_path("missing/seed.json", repo_root=repo_root) is None
