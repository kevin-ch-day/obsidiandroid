"""Tests for output artifact classification and inventory helpers."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config
from obsidiandroid.diagnostics import output_artifact_policy
from obsidiandroid.diagnostics import output_inventory


def test_classify_run_manifest_is_evidence_required() -> None:
    meta = output_artifact_policy.classify_relative_path("run_manifest.json")
    assert meta["artifact_bucket"] == "evidence_required"


def test_classify_unknown_defaults_optional() -> None:
    meta = output_artifact_policy.classify_relative_path("diagnostics/foo_bar_unknown.xyz")
    assert meta["artifact_bucket"] == "diagnostics_optional"


def test_build_inventory_rows_counts_files(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r1"
    (run_root / "diagnostics").mkdir(parents=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "diagnostics" / "note.txt").write_text("x", encoding="utf-8")
    rows = output_inventory.build_inventory_rows(run_root)
    assert len(rows) == 2
    kinds = {r["path"]: r["artifact_type"] for r in rows}
    assert kinds["run_manifest.json"] == "evidence_required"


def test_write_artifact_inventory_bundle_separates_legacy_latest_compatibility(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "output" / "runs" / "r_inv"
    diagnostics_dir = run_root / "diagnostics"
    figures_dir = run_root / "bundles" / "permission_trends" / "figures"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (figures_dir / "type_permission_heatmap.latest.png").write_text("x", encoding="utf-8")

    _paths, summary = output_inventory.write_artifact_inventory_bundle(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_inv",
        manifest_paths=[],
        extra_summary=None,
    )

    assert summary["duplicate_latest_inside_run"] == 1
    assert summary["duplicate_latest_inside_run_legacy_compatibility"] == 1
    assert summary["duplicate_latest_inside_run_policy_drift"] == 0


def test_write_run_evidence_index_prefers_canonical_feature_build_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_cov"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / f"feature_build_coverage_{run_id}.json").write_text(
        json.dumps({"missing_from_feature_matrix_count": 7}),
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        paper_mode=False,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        paper_safe_status="NOT_APPLICABLE",
        paper_safe_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Missing-from-feature-matrix count (coverage export):** 7" in text


def test_write_run_evidence_index_includes_authority_coverage_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_auth"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / f"family_type_authority_coverage_{run_id}.md").write_text(
        "# Family/Type Authority Coverage Report\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="paper_locked",
        paper_mode=True,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        paper_safe_status="PASS",
        paper_safe_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Authority coverage diagnostic:" in text
    assert f"family_type_authority_coverage_{run_id}.md" in text


def test_write_run_evidence_index_includes_taxonomy_authority_split_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_taxsplit"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / f"taxonomy_authority_split_{run_id}.md").write_text(
        "# Taxonomy Authority Split\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="paper_locked",
        paper_mode=True,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        paper_safe_status="PASS",
        paper_safe_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Taxonomy authority split:" in text
    assert f"taxonomy_authority_split_{run_id}.md" in text


def test_paper_safe_status_not_applicable_when_paper_mode_off() -> None:
    status, reasons = output_inventory.evaluate_paper_safe_status(
        paper_mode=False,
        manifest={},
        compliance_report=None,
    )
    assert status == "NOT_APPLICABLE"
    assert reasons == []


def test_paper_safe_status_pass_when_compliance_passes() -> None:
    status, reasons = output_inventory.evaluate_paper_safe_status(
        paper_mode=True,
        manifest={},
        compliance_report={"overall_status": "pass"},
    )
    assert status == "PASS"
    assert reasons == []


def test_paper_safe_status_fail_when_compliance_fails() -> None:
    status, reasons = output_inventory.evaluate_paper_safe_status(
        paper_mode=True,
        manifest={},
        compliance_report={"overall_status": "fail"},
    )
    assert status == "FAIL"
    assert "paper_compliance_not_pass" in reasons


def test_output_hygiene_terminal_summary_omits_open_first(capsys, tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r_out"
    run_root.mkdir(parents=True, exist_ok=True)

    output_inventory.print_output_hygiene_terminal_summary(
        run_root=run_root,
        summary={
            "total_artifacts": 10,
            "bucket_counts": {
                "evidence_required": 1,
                "diagnostics_required": 2,
                "diagnostics_optional": 3,
                "debug_only": 0,
            },
            "duplicate_latest_inside_run_policy_drift": 0,
            "duplicate_latest_inside_run_legacy_compatibility": 2,
        },
        evidence_index_path=run_root / "run_evidence_index.md",
        paper_safe_status="PASS",
    )

    out = capsys.readouterr().out
    assert "Output Summary" in out
    assert "Open first" not in out
    assert "Legacy .latest compatibility copies" in out
