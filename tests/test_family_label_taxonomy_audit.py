"""Unit tests for family label taxonomy audit (no DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.hostile_audit.taxonomy_label_quality_audit import (
    write_taxonomy_label_quality_audit,
)
from obsidiandroid.diagnostics import family_label_taxonomy_audit as fla
from obsidiandroid.diagnostics import family_label_confidence_audit
import scripts.family_label_taxonomy_audit as audit_script


def test_support_threshold_preview_counts() -> None:
    df = pd.DataFrame(
        {
            "family_id": [1, 1, 1, 2, 2, 2, 3, 3, 3],
            "family_canonical": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
            "type_slug": ["banker"] * 9,
        }
    )
    fam, th, summary = fla.build_family_taxonomy_audit_frames(df, training_min_support=20)
    assert summary["governed_samples"] == 9
    assert summary["governed_distinct_families"] == 3
    row20 = th[th["min_support_threshold"] == 20].iloc[0]
    assert int(row20["retained_families"]) == 0
    assert int(row20["retained_samples"]) == 0
    row3 = th[th["min_support_threshold"] == 3].iloc[0]
    assert int(row3["retained_families"]) == 3


def test_classify_label_quality() -> None:
    assert fla.classify_label_quality("Irata", sample_count=50, is_alias_duplicate=False) == "canonical_named_family"
    assert fla.classify_label_quality("trojan/android.generic.foo", sample_count=50, is_alias_duplicate=False) == "generic_av_label"
    assert fla.classify_label_quality("", sample_count=5, is_alias_duplicate=False) == "unknown_or_unresolved"
    assert fla.classify_label_quality("Irata", sample_count=50, is_alias_duplicate=True) == "alias_candidate"


def test_write_family_label_taxonomy_audit_artifacts(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "family_id": [1, 1, 2, 2],
            "family_canonical": ["Irata", "Irata", "y", "y"],
            "type_slug": ["banker", "banker", "adware", "adware"],
        }
    )
    lines: list[str] = []

    fla.write_family_label_taxonomy_audit(
        df,
        diagnostics_dir=tmp_path,
        profile_id="test_profile",
        training_min_support=2,
        run_id="test_run",
        print_fn=lambda s: lines.append(s),
    )
    assert (tmp_path / "family_label_taxonomy_audit.csv").is_file()
    assert (tmp_path / "support_threshold_preview.csv").is_file()
    assert any("FAMILY LABEL SPACE AUDIT" in x for x in lines)


def test_write_family_label_taxonomy_audit_artifacts_supports_prefixed_outputs(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "family_id": [1, 1, 2, 2],
            "family_canonical": ["Irata", "Irata", "y", "y"],
            "type_slug": ["banker", "banker", "adware", "adware"],
        }
    )

    fla.write_family_label_taxonomy_audit(
        df,
        diagnostics_dir=tmp_path,
        profile_id="test_profile",
        training_min_support=2,
        run_id="test_run",
        artifact_prefix="sql_governed_",
        print_fn=None,
    )
    assert (tmp_path / "sql_governed_family_label_taxonomy_audit.csv").is_file()
    assert (tmp_path / "sql_governed_support_threshold_preview.csv").is_file()


def test_taxonomy_label_quality_audit_uses_global_latest_summary_when_run_local_latest_is_pruned(
    make_run_diagnostics_layout,
) -> None:
    """Audit markdown should resolve the global latest taxonomy summary mirror."""
    _, diagnostics_dir, global_diag = make_run_diagnostics_layout("run_tax")

    (global_diag / "taxonomy_consistency_summary.latest.json").write_text(
        json.dumps(
            {
                "rows_evaluated": 10,
                "type_rows_evaluated": 8,
                "family_rows_evaluated": 10,
                "type_missing_label_count": 1,
                "type_noncanonical_count": 0,
                "type_mismatch_count": 2,
                "family_label_mismatch_count": 0,
                "taxonomy_mismatch_count": 3,
                "prediction_error_count": 1,
            }
        ),
        encoding="utf-8",
    )

    out = write_taxonomy_label_quality_audit(diagnostics_dir=diagnostics_dir, run_id="run_tax")

    text = out.read_text(encoding="utf-8")
    assert "taxonomy_consistency_summary.latest.json" in text
    assert "| taxonomy_mismatch_count | 3 |" in text


def test_build_family_label_confidence_payload_ranks_conflicts_and_type_mismatches() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_canonical": ["Gigabud", "Gigabud", "SpyNote", "DoNot"],
            "family_label_raw": ["Gigabud", "WrongFam", "SpyNote", ""],
            "type_slug": ["banker", "banker", "rat", "spyware"],
            "category_primary": ["trojan", "trojan", "rat", "trojan"],
            "category_subtype": ["banker", "spyware", "rat", ""],
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "opaque_string",
                "family_or_common_name",
            ],
            "vt_family_token": ["gigabud", "gigabud", "", "donot"],
        }
    )

    payload = family_label_confidence_audit.build_family_label_confidence_payload(
        df,
        min_support=2,
    )

    assert payload["row_count"] == 4
    assert payload["family_count"] == 3
    assert payload["sample_rows"]
    worst = payload["sample_rows"][0]
    assert worst["sample_id"] == 2
    assert "family_conflict" in worst["reasons"]
    assert "raw_type_mismatch" in worst["reasons"]

    families = {row["family_canonical"]: row for row in payload["family_rows"]}
    assert families["gigabud"]["family_conflict_rows"] == 1
    assert families["gigabud"]["type_mismatch_rows"] == 1
    assert families["spynote"]["weak_label_rows"] == 1


def test_build_family_label_confidence_payload_downgrades_publicly_corroborated_weak_labels() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["SpyNote", "SpyNote"],
            "family_label_raw": ["SpyNote", "SpyNote"],
            "type_slug": ["rat", "rat"],
            "category_primary": ["rat", "rat"],
            "category_subtype": ["rat", "rat"],
            "sample_label_kind": ["opaque_string", "opaque_string"],
            "vt_family_token": ["", ""],
            "package_name": ["yps.eton.application", "com.unknown.example"],
            "android_package_name": ["yps.eton.application", "com.unknown.example"],
        }
    )

    payload = family_label_confidence_audit.build_family_label_confidence_payload(df, min_support=2)
    families = {row["family_canonical"]: row for row in payload["family_rows"]}
    assert families["spynote"]["weak_label_rows"] == 1
    assert families["spynote"]["weak_label_corroborated_rows"] == 1


def test_textual_null_family_tokens_remain_unresolved_not_phantom_families() -> None:
    """CSV-style textual nulls must not create a named family in curation reports."""
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "family_canonical": ["nan"],
            "family_label_raw": ["n/a"],
            "type_slug": ["banker"],
            "category_primary": ["trojan"],
            "category_subtype": ["banker"],
            "sample_label_kind": ["family_or_common_name"],
            "vt_family_token": ["possiblefamily"],
        }
    )

    payload = family_label_confidence_audit.build_family_label_confidence_payload(df, min_support=2)

    assert payload["family_count"] == 0
    assert payload["sample_rows"][0]["family_canonical"] == "<blank>"
    assert "blank_family_with_vt_token" in payload["sample_rows"][0]["reasons"]
    assert "family_conflict" not in payload["sample_rows"][0]["reasons"]


def test_export_family_label_confidence_reports_writes_expected_files(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["A", "B"],
            "family_label_raw": ["A", "B"],
            "type_slug": ["banker", "rat"],
            "category_primary": ["trojan", "rat"],
            "category_subtype": ["banker", "rat"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
            "vt_family_token": ["a", "b"],
        }
    )
    paths = family_label_confidence_audit.export_family_label_confidence_reports(
        diagnostics_dir=tmp_path,
        run_id="runx",
        samples_df=df,
        min_support=2,
    )
    assert len(paths) == 6
    for path in paths:
        assert tmp_path.joinpath(path.split("/")[-1]).is_file()


def test_build_family_label_drift_remediation_rows_exports_expected_actions() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103, 104],
            "sha256": ["a" * 64, "b" * 64, "c" * 64, "d" * 64],
            "family_canonical": ["SpyNote", "SpyLoan", "Octo", "Octo"],
            "family_label_raw": ["", "BlackLoan", "ExobotCompact.D/Octo", "WrongFam"],
            "type_slug": ["rat", "banker", "banker", "banker"],
            "category_primary": ["rat", "trojan", "trojan", "trojan"],
            "category_subtype": ["rat", "banker", "banker", "banker"],
            "sample_label_kind": [
                "opaque_string",
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
            ],
            "vt_family_token": ["spynote", "spyloan", "octo", "octo"],
            "source_batch_label": ["", "", "campaign_alpha", "campaign_beta"],
            "package_name": ["pkg.spy.note", "pkg.spy.loan", "pkg.octo", "pkg.octo.bad"],
            "android_package_name": ["pkg.spy.note", "pkg.spy.loan", "pkg.octo", "pkg.octo.bad"],
        }
    )

    out = family_label_confidence_audit.build_family_label_drift_remediation_rows(df)

    assert list(out["family_canonical"]) == ["Octo", "SpyNote"]
    assert "SpyLoan" not in set(out["family_canonical"])

    octo = out[out["family_canonical"] == "Octo"].iloc[0]
    assert octo["issue_kind"] == "family_conflict"
    assert octo["proposed_action"] == "repair_alias_mapping"
    assert octo["source_batch_label"] == "campaign_beta"

    spynote = out[out["family_canonical"] == "SpyNote"].iloc[0]
    assert spynote["issue_kind"] == "weak_label_corroborated"
    assert spynote["proposed_action"] == "accept_public_campaign_corroboration"
    assert spynote["sample_label_kind"] == "opaque_string"


def test_build_family_label_drift_remediation_rows_marks_publicly_corroborated_weak_labels() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "sha256": ["a" * 64],
            "family_canonical": ["SpyNote"],
            "family_label_raw": ["SpyNote"],
            "type_slug": ["rat"],
            "category_primary": ["rat"],
            "category_subtype": ["rat"],
            "sample_label_kind": ["opaque_string"],
            "vt_family_token": [""],
            "source_batch_label": [""],
            "package_name": ["yps.eton.application"],
            "android_package_name": ["yps.eton.application"],
        }
    )
    out = family_label_confidence_audit.build_family_label_drift_remediation_rows(df)
    row = out.iloc[0]
    assert row["issue_kind"] == "weak_label_corroborated"
    assert row["proposed_action"] == "accept_public_campaign_corroboration"


def test_build_family_label_confidence_payload_downgrades_public_ioc_hash_corroborated_weak_labels() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "sha256": ["46a3badfa5682d2d862618933155fa04cc64690d5588ea06089670e222ba36b4"],
            "family_canonical": ["SpyNote"],
            "family_label_raw": ["SpyNote"],
            "type_slug": ["rat"],
            "category_primary": ["rat"],
            "category_subtype": ["rat"],
            "sample_label_kind": ["opaque_string"],
            "vt_family_token": [""],
            "package_name": ["com.unrelated.example"],
            "android_package_name": ["com.unrelated.example"],
        }
    )

    payload = family_label_confidence_audit.build_family_label_confidence_payload(df, min_support=2)
    family = payload["family_rows"][0]
    assert family["weak_label_rows"] == 0
    assert family["weak_label_corroborated_rows"] == 1


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


def test_locked_audit_records_taxonomy_drift_without_failing(
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
        lambda **_kwargs: {
            "cohort_lock_status": "membership_locked_taxonomy_drift",
            "sample_id_lock": {
                "taxonomy_label_drift": {
                    "drift_class": "taxonomy_expansion",
                    "family_delta": 5,
                    "type_delta": 1,
                }
            },
            "validation": {
                "status": "degraded_taxonomy_label_drift",
                "warning": "sample-id membership still matches but taxonomy labels drifted",
            },
        },
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
            "family_label_taxonomy_audit_csv": Path(diagnostics_dir) / "family_label_taxonomy_audit.csv",
            "family_label_taxonomy_audit_md": Path(diagnostics_dir) / "family_label_taxonomy_audit.md",
            "support_threshold_preview_csv": Path(diagnostics_dir) / "support_threshold_preview.csv",
            "support_threshold_preview_md": Path(diagnostics_dir) / "support_threshold_preview.md",
            "run_id": "ignored",
        }
        for key, path in paths.items():
            if key != "run_id":
                path.write_text("x\n", encoding="utf-8")
        return paths

    monkeypatch.setattr(audit_script.fam_audit, "write_family_label_taxonomy_audit", _fake_write)
    captured_warnings: list[str] = []
    monkeypatch.setattr(audit_script.du, "print_warning", captured_warnings.append)
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
    assert any("taxonomy labels drifted" in warning for warning in captured_warnings)
    prov = json.loads((diagnostics_dir / "diagnostic_provenance.json").read_text(encoding="utf-8"))
    entry = prov["entries"][0]
    assert entry["cohort_lock_status"] == "membership_locked_taxonomy_drift"
    assert entry["taxonomy_label_drift"]["drift_class"] == "taxonomy_expansion"
    assert entry["taxonomy_label_drift"]["family_delta"] == 5
    assert entry["observed_counts"]["sample_count"] == 2


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
        lambda **_kwargs: {
            "cohort_lock_status": "membership_mismatch",
            "sample_id_lock": {
                "observed_sample_count": 2,
                "expected_sample_count": 3,
                "missing_sample_ids": [3],
            },
            "validation": {"status": "fail", "warning": "missing locked members"},
        },
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
    assert entry["cohort_lock_status"] == "membership_mismatch"
    assert entry["lock_diff"]["missing_locked_ids_preview"] == [3]
    assert entry["lock_diff"]["missing_locked_ids_count"] == 1
