"""Tests for post-run family taxonomy audit provenance and lock context."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import scripts.family_label_taxonomy_audit as audit_script


def _locked_profile(lock_path: Path) -> dict:
    return {
        "profile_id": "malicious_temporal_stability_locked",
        "paper_locked": True,
        "evidence_mode": True,
        "cohort_gates": {"min_samples_per_family": 20},
        "paper_lock": {
            "contract_id": "malicious_temporal_stability_locked_contract",
            "expected_sample_count": 1226,
            "expected_family_count": 39,
            "expected_type_count": 6,
            "sample_id_lock_file": str(lock_path),
        },
    }


def _seed_audit_run(
    write_text_file,
    make_run_diagnostics_layout,
    run_id: str,
) -> tuple[Path, Path]:
    output_root, diagnostics_dir, _ = make_run_diagnostics_layout(run_id)
    run_root = output_root / "runs" / run_id
    write_text_file(
        run_root / "run_manifest.json",
        json.dumps({"run_id": run_id, "profile_params": {"profile_id": "malicious_temporal_stability"}}),
    )
    return output_root, diagnostics_dir


def test_locked_audit_records_target_run_context(
    monkeypatch,
    tmp_path: Path,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    output_root, diagnostics_dir = _seed_audit_run(write_text_file, make_run_diagnostics_layout, run_id)
    lock_path = tmp_path / "lock.csv"
    write_text_file(lock_path, "sample_id\n1\n2\n")

    monkeypatch.setattr(
        audit_script.profile_manager,
        "load_profile",
        lambda _arg: _locked_profile(lock_path),
    )
    monkeypatch.setattr(
        audit_script.paper_cohort_contract,
        "configure_runtime_snapshot_lock",
        lambda profile: {
            "paper_locked": True,
            "contract_id": "malicious_temporal_stability_locked_contract",
            "cohort_lock_status": "membership_locked",
            "expected": {"sample_count": 1226, "family_count": 39, "type_count": 6},
            "sample_id_lock": {"path": str(lock_path), "enforceable": True},
        },
    )
    monkeypatch.setattr(
        audit_script.paper_cohort_contract,
        "build_runtime_contract",
        lambda **_kwargs: {"cohort_lock_status": "membership_locked"},
    )
    monkeypatch.setattr(
        audit_script,
        "load_and_prepare_samples",
        lambda **_kwargs: pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["A", "B"],
                "type_slug": ["banker", "banker"],
            }
        ),
    )

    def _fake_write(*_args, diagnostics_dir: Path, **_kwargs):
        out = Path(diagnostics_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = {
            "family_label_taxonomy_audit_csv": out / "family_label_taxonomy_audit.csv",
            "family_label_taxonomy_audit_md": out / "family_label_taxonomy_audit.md",
            "support_threshold_preview_csv": out / "support_threshold_preview.csv",
            "support_threshold_preview_md": out / "support_threshold_preview.md",
            "run_id": "ignored",
        }
        for key, path in paths.items():
            if key != "run_id":
                path.write_text("x\n", encoding="utf-8")
        return paths

    monkeypatch.setattr(audit_script.fam_audit, "write_family_label_taxonomy_audit", _fake_write)
    monkeypatch.setattr(audit_script.app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(
        audit_script.sys,
        "argv",
        [
            "family_label_taxonomy_audit.py",
            "--profile",
            "malicious_temporal_stability_locked",
            "--diagnostics-dir",
            str(diagnostics_dir),
        ],
    )

    result = audit_script.main()

    assert result == 0
    prov = json.loads((diagnostics_dir / "diagnostic_provenance.json").read_text(encoding="utf-8"))
    entry = prov["entries"][0]
    assert entry["target_run_id"] == run_id
    assert entry["target_run_profile"] == "malicious_temporal_stability"
    assert entry["audit_profile"] == "malicious_temporal_stability_locked"
    assert entry["same_profile_as_target"] is False
    assert entry["cohort_lock_status"] == "membership_locked"
    assert entry["expected_counts"]["sample_count"] == 1226
    assert entry["observed_counts"]["sample_count"] == 2
    assert entry["artifacts"][0]["path"].startswith("diagnostics/post_run_enrichments/")


def test_locked_audit_mismatch_records_failed_provenance(
    monkeypatch,
    tmp_path: Path,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    output_root, diagnostics_dir = _seed_audit_run(write_text_file, make_run_diagnostics_layout, run_id)
    lock_path = tmp_path / "lock.csv"
    write_text_file(lock_path, "sample_id\n1\n2\n3\n")

    monkeypatch.setattr(
        audit_script.profile_manager,
        "load_profile",
        lambda _arg: _locked_profile(lock_path),
    )
    monkeypatch.setattr(
        audit_script.paper_cohort_contract,
        "configure_runtime_snapshot_lock",
        lambda profile: {
            "paper_locked": True,
            "contract_id": "malicious_temporal_stability_locked_contract",
            "cohort_lock_status": "membership_locked",
            "expected": {"sample_count": 1226, "family_count": 39, "type_count": 6},
            "sample_id_lock": {"path": str(lock_path), "enforceable": True},
        },
    )
    monkeypatch.setattr(
        audit_script.paper_cohort_contract,
        "build_runtime_contract",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("locked mismatch")),
    )
    monkeypatch.setattr(
        audit_script,
        "load_and_prepare_samples",
        lambda **_kwargs: pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["A", "B"],
                "type_slug": ["banker", "banker"],
            }
        ),
    )
    monkeypatch.setattr(audit_script.app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(
        audit_script.sys,
        "argv",
        [
            "family_label_taxonomy_audit.py",
            "--profile",
            "malicious_temporal_stability_locked",
            "--diagnostics-dir",
            str(diagnostics_dir),
        ],
    )

    result = audit_script.main()

    assert result == 3
    prov = json.loads((diagnostics_dir / "diagnostic_provenance.json").read_text(encoding="utf-8"))
    entry = prov["entries"][0]
    assert entry["cohort_lock_status"] == "locked_mismatch"
    assert entry["observed_counts"]["sample_count"] == 2
    assert entry["lock_diff"]["missing_locked_ids_count"] == 1
    assert entry["artifact_count"] == 0
