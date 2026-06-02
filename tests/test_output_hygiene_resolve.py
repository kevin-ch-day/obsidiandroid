"""Tests for output path resolution helpers."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common import output_paths


def test_resolve_dataset_time_contract_prefers_run_scoped(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir()
    scoped = diag / "dataset_time_contract_r1.json"
    scoped.write_text("{}", encoding="utf-8")
    legacy = diag / "dataset_time_contract.latest.json"
    legacy.write_text("{}", encoding="utf-8")
    assert oh.resolve_dataset_time_contract_path(diag, "r1") == scoped


def test_resolve_runtime_run_directory_uses_layout_when_no_runtime_root(
    monkeypatch, tmp_path: Path
) -> None:
    """Without RUNTIME_RUN_ROOT, resolve under output_root/runs/<run_id>."""
    out = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", "", raising=False)
    rid = "run123"
    expected = out / "runs" / rid
    assert output_paths.resolve_runtime_run_directory(rid) == expected.resolve()


def test_resolve_runtime_run_directory_prefers_runtime_run_root(
    monkeypatch, tmp_path: Path
) -> None:
    """Runtime run roots may be slot-based and should be returned as-is."""
    rid = "run123"
    run_root = tmp_path / "output" / "runs" / "majorfam_benchmark"
    run_root.mkdir(parents=True)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(run_root), raising=False)
    assert output_paths.resolve_runtime_run_directory(rid) == run_root.resolve()


def test_read_json_dict_missing_returns_empty(tmp_path: Path) -> None:
    from obsidiandroid.common.json_io import read_json_dict

    assert read_json_dict(tmp_path / "nope.json") == {}


def test_read_json_dict_object_roundtrip(tmp_path: Path) -> None:
    from obsidiandroid.common.json_io import read_json_dict

    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert read_json_dict(p) == {"a": 1}


def test_read_json_dict_non_object_returns_empty(tmp_path: Path) -> None:
    from obsidiandroid.common.json_io import read_json_dict

    p = tmp_path / "arr.json"
    p.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert read_json_dict(p) == {}


def test_resolve_analysis_snapshot_prefers_run_scoped(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir()
    scoped = diag / "analysis_snapshot_r2.csv"
    scoped.write_text("a,b\n1,2\n", encoding="utf-8")
    assert oh.resolve_analysis_snapshot_csv_path(diag, "r2") == scoped


def test_resolve_run_or_global_artifact_path_falls_back_to_global_latest(
    make_run_diagnostics_layout,
) -> None:
    _output_root, diag, gdiag = make_run_diagnostics_layout("rid")
    global_latest = gdiag / "artifact.latest.json"
    global_latest.write_text("{}", encoding="utf-8")

    got = oh.resolve_run_or_global_artifact_path(
        diag,
        run_filename="artifact_rid.json",
        global_latest_name="artifact.latest.json",
    )
    assert got.resolve() == global_latest.resolve()


def test_resolve_taxonomy_consistency_summary_path_prefers_run_scoped(make_run_diagnostics_layout) -> None:
    _output_root, diag, _gdiag = make_run_diagnostics_layout("rid")
    scoped = diag / "taxonomy_consistency_summary_rid.json"
    scoped.write_text("{}", encoding="utf-8")
    assert oh.resolve_taxonomy_consistency_summary_path(diag, "rid") == scoped


def test_resolve_feature_column_survival_path_prefers_global_latest_when_local_latest_is_pruned(
    make_run_diagnostics_layout,
) -> None:
    _output_root, diag, gdiag = make_run_diagnostics_layout("rid")
    global_latest = gdiag / "feature_column_survival.latest.csv"
    global_latest.write_text("feature_name\nx\n", encoding="utf-8")
    assert oh.resolve_feature_column_survival_path(diag, "rid").resolve() == global_latest.resolve()


def test_diagnostics_mirror_write_policy_prefers_global_latest_for_run_scoped(
    make_run_diagnostics_layout,
) -> None:
    _output_root, diag, _gdiag = make_run_diagnostics_layout("rid")
    assert oh.diagnostics_mirror_write_policy(diag) == oh.RUN_SCOPED_PLUS_GLOBAL_LATEST_MIRROR


def test_diagnostics_mirror_write_policy_keeps_local_latest_for_non_run_scoped(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir()
    assert oh.diagnostics_mirror_write_policy(diag) == oh.RUN_SCOPED_PLUS_LOCAL_LATEST_DUPLICATE


def test_resolve_feature_build_artifacts_prefers_global_latest_when_local_latest_is_pruned(
    make_run_diagnostics_layout,
) -> None:
    _output_root, diag, gdiag = make_run_diagnostics_layout("rid")
    fixtures = {
        "ablation_summary.latest.csv": oh.resolve_ablation_summary_path,
        "analysis_snapshot_label_conflicts.latest.csv": oh.resolve_analysis_snapshot_label_conflicts_path,
        "analysis_snapshot_filter_summary.latest.csv": oh.resolve_analysis_snapshot_filter_summary_path,
        "cohort_filter_contract.latest.json": oh.resolve_cohort_filter_contract_path,
        "cohort_gate_counts.latest.csv": oh.resolve_cohort_gate_counts_path,
        "engine_lifecycle.latest.csv": oh.resolve_engine_lifecycle_path,
        "feature_build_coverage.latest.json": oh.resolve_feature_build_coverage_path,
        "cohort_missing_from_feature_matrix.latest.csv": oh.resolve_cohort_missing_from_feature_matrix_path,
        "feature_set_ablation_summary.latest.csv": oh.resolve_feature_set_ablation_summary_path,
        "feature_contract.latest.json": oh.resolve_feature_contract_path,
        "feature_matrix_lineage_gate.latest.json": oh.resolve_feature_matrix_lineage_gate_path,
        "feature_modality_coverage_audit.latest.csv": oh.resolve_feature_modality_coverage_audit_path,
        "feature_modality_coverage_summary.latest.json": oh.resolve_feature_modality_coverage_summary_path,
        "headline_vs_ablation_contract_comparison.latest.md": oh.resolve_headline_vs_ablation_contract_comparison_path,
        "label_name_map.latest.json": oh.resolve_label_name_map_path,
        "leakage_assessment.latest.txt": oh.resolve_leakage_assessment_path,
        "modality_method_contract.latest.json": oh.resolve_modality_method_contract_path,
        "model_comparison_summary.latest.csv": oh.resolve_model_comparison_summary_path,
        "parser_quality.latest.csv": oh.resolve_parser_quality_path,
        "parser_quality_final.latest.csv": oh.resolve_parser_quality_final_path,
        "prediction_errors.latest.csv": oh.resolve_prediction_errors_path,
        "sample_stage_lineage.latest.csv": oh.resolve_sample_stage_lineage_path,
        "taxonomy_consistency_mismatches.latest.csv": oh.resolve_taxonomy_consistency_mismatches_path,
        "vendor_gate_debug.latest.csv": oh.resolve_vendor_gate_debug_path,
        "vendor_gate_top10_pre_gate.latest.csv": oh.resolve_vendor_gate_top10_pre_gate_path,
        "taxonomy_type_authority_review.latest.md": oh.resolve_taxonomy_type_authority_review_path,
        "vendor_parser_coverage.latest.csv": oh.resolve_vendor_parser_coverage_path,
        "vendor_parser_coverage_candidates.latest.csv": oh.resolve_vendor_parser_coverage_candidates_path,
        "vendor_parser_strengths_weaknesses.latest.csv": oh.resolve_vendor_parser_strengths_weaknesses_path,
        "vendor_parser_stress_test.latest.csv": oh.resolve_vendor_parser_stress_test_path,
    }
    for name, resolver in fixtures.items():
        global_latest = gdiag / name
        global_latest.write_text("{}\n", encoding="utf-8")
        assert resolver(diag, "rid").resolve() == global_latest.resolve()


def test_resolve_ablation_summary_path_can_fall_back_to_partial_run_scoped_file(
    make_run_diagnostics_layout,
) -> None:
    _output_root, diag, _gdiag = make_run_diagnostics_layout("rid")
    partial = diag / "ablation_summary_partial_rid.csv"
    partial.write_text("x\n1\n", encoding="utf-8")
    assert oh.resolve_ablation_summary_path(diag, "rid", allow_partial=True) == partial


def test_mirror_csv_writes_primary_and_secondary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    diag = tmp_path / "output" / "runs" / "rid" / "diagnostics"
    diag.mkdir(parents=True)
    paths = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diag,
        run_filename="foo_rid.csv",
        csv_text="x\n1\n",
        global_latest_name="foo.latest.csv",
    )
    assert len(paths) == 2
    assert paths[0].name == "foo_rid.csv"
    assert paths[0].exists()
    assert not (diag / "foo.latest.csv").exists()
    expected_global = tmp_path / "output" / "diagnostics" / "foo.latest.csv"
    assert paths[1].resolve() == expected_global.resolve()


def test_mirror_json_suppress_skips_local_latest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    diag = tmp_path / "output" / "runs" / "ridj" / "diagnostics"
    diag.mkdir(parents=True)
    paths = oh.mirror_json_text_run_then_global(
        diagnostics_dir=diag,
        run_filename="cfg_ridj.json",
        payload={"run_id": "ridj", "k": 1},
        global_latest_name="cfg.latest.json",
    )
    assert len(paths) == 2
    assert not (diag / "cfg.latest.json").exists()
    assert (tmp_path / "output" / "diagnostics" / "cfg.latest.json").is_file()


def test_methodology_resolvers_prefer_run_scoped_compat_files(
    make_run_diagnostics_layout,
) -> None:
    _output_root, diag, _gdiag = make_run_diagnostics_layout("rid")
    feature_contract = diag / "feature_contract.json"
    modality_contract = diag / "modality_method_contract.json"
    leakage_assessment = diag / "leakage_assessment.txt"
    feature_contract.write_text("{}", encoding="utf-8")
    modality_contract.write_text("{}", encoding="utf-8")
    leakage_assessment.write_text("ok\n", encoding="utf-8")

    assert oh.resolve_feature_contract_path(diag, "rid") == feature_contract
    assert oh.resolve_modality_method_contract_path(diag, "rid") == modality_contract
    assert oh.resolve_leakage_assessment_path(diag, "rid") == leakage_assessment


def test_suppress_mode_leaves_no_latest_named_files_in_run_diagnostics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    diag = tmp_path / "output" / "runs" / "r99" / "diagnostics"
    diag.mkdir(parents=True)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diag,
        run_filename="a_r99.csv",
        csv_text="x\n",
        global_latest_name="a.latest.csv",
    )
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diag,
        run_filename="b_r99.json",
        payload={"x": 1},
        global_latest_name="b.latest.json",
    )
    assert not list(diag.glob("*.latest*"))


def test_mirror_utf8_text_suppress_skips_local_latest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    diag = tmp_path / "output" / "runs" / "ridt" / "diagnostics"
    diag.mkdir(parents=True)
    paths = oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diag,
        run_filename="note_ridt.txt",
        text="hello\n",
        global_latest_name="note.latest.txt",
    )
    assert len(paths) == 2
    assert not (diag / "note.latest.txt").exists()
    assert (tmp_path / "output" / "diagnostics" / "note.latest.txt").read_text(encoding="utf-8") == "hello\n"


def test_mirror_csv_rejects_literal_none_directory() -> None:
    try:
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=Path("None"),
            run_filename="bad.csv",
            csv_text="x\n1\n",
            global_latest_name="bad.latest.csv",
        )
    except ValueError as exc:
        assert "literal 'None' path" in str(exc)
    else:
        raise AssertionError("expected literal None diagnostics path to be rejected")
