from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import cleanup_output_artifacts as coa


def _make_run(output_dir: Path, run_id: str) -> Path:
    run_dir = output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def test_collect_targets_prunes_legacy_run_subdirs_for_older_runs(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    old_run = _make_run(output_dir, "20260519T010101Z__aaaaaa")
    keep_run = _make_run(output_dir, "20260519T020202Z__bbbbbb")

    for name in ("latest", "promoted", "runs", "paper2_pack", "evidence_bundle"):
        (old_run / name).mkdir(parents=True, exist_ok=True)
    for name in ("latest", "promoted", "runs", "paper2_pack", "evidence_bundle"):
        (keep_run / name).mkdir(parents=True, exist_ok=True)

    targets = coa._collect_targets(  # pylint: disable=protected-access
        output_dir,
        keep_run_ids={"20260519T020202Z__bbbbbb"},
        keep_runtime_logs=0,
    )

    target_set = {path.relative_to(output_dir).as_posix() for path in targets}
    assert "runs/20260519T010101Z__aaaaaa/latest" in target_set
    assert "runs/20260519T010101Z__aaaaaa/promoted" in target_set
    assert "runs/20260519T010101Z__aaaaaa/runs" in target_set
    assert "runs/20260519T010101Z__aaaaaa/paper2_pack" in target_set
    assert "runs/20260519T020202Z__bbbbbb/latest" not in target_set
    assert "runs/20260519T020202Z__bbbbbb/paper2_pack" not in target_set


def test_collect_targets_can_prune_legacy_subdirs_for_preserved_latest_run(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    keep_run = _make_run(output_dir, "20260519T020202Z__bbbbbb")
    for name in ("latest", "promoted", "runs", "paper2_pack", "evidence_bundle"):
        (keep_run / name).mkdir(parents=True, exist_ok=True)

    targets = coa._collect_targets(  # pylint: disable=protected-access
        output_dir,
        keep_run_ids={"20260519T020202Z__bbbbbb"},
        keep_runtime_logs=0,
        prune_preserved_legacy=True,
    )

    target_set = {path.relative_to(output_dir).as_posix() for path in targets}
    assert "runs/20260519T020202Z__bbbbbb/latest" in target_set
    assert "runs/20260519T020202Z__bbbbbb/promoted" in target_set
    assert "runs/20260519T020202Z__bbbbbb/runs" in target_set
    assert "runs/20260519T020202Z__bbbbbb/paper2_pack" in target_set


def test_collect_targets_only_prunes_paper2_pack_when_evidence_bundle_exists(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    run_dir = _make_run(output_dir, "20260519T010101Z__aaaaaa")
    (run_dir / "paper2_pack").mkdir(parents=True, exist_ok=True)

    targets = coa._collect_targets(  # pylint: disable=protected-access
        output_dir,
        keep_run_ids=set(),
        keep_runtime_logs=0,
    )

    target_set = {path.relative_to(output_dir).as_posix() for path in targets}
    assert "runs/20260519T010101Z__aaaaaa/paper2_pack" not in target_set


def test_collect_targets_prunes_old_run_local_latest_and_split_freeze_exports(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    old_run = _make_run(output_dir, "20260519T010101Z__aaaaaa")
    keep_run = _make_run(output_dir, "20260519T020202Z__bbbbbb")
    old_diag = old_run / "diagnostics"
    keep_diag = keep_run / "diagnostics"
    old_diag.mkdir(parents=True, exist_ok=True)
    keep_diag.mkdir(parents=True, exist_ok=True)

    (old_diag / "feature_build_coverage.latest.json").write_text("{}", encoding="utf-8")
    (old_diag / "split_freeze_ablation__full_fused__type_slug__xgboost__20260519T010101Z__aaaaaa.csv").write_text(
        "x\n",
        encoding="utf-8",
    )
    (keep_diag / "feature_build_coverage.latest.json").write_text("{}", encoding="utf-8")
    (keep_diag / "split_freeze_ablation__full_fused__type_slug__xgboost__20260519T020202Z__bbbbbb.csv").write_text(
        "x\n",
        encoding="utf-8",
    )

    targets = coa._collect_targets(  # pylint: disable=protected-access
        output_dir,
        keep_run_ids={"20260519T020202Z__bbbbbb"},
        keep_runtime_logs=0,
    )

    target_set = {path.relative_to(output_dir).as_posix() for path in targets}
    assert "runs/20260519T010101Z__aaaaaa/diagnostics/feature_build_coverage.latest.json" in target_set
    assert (
        "runs/20260519T010101Z__aaaaaa/diagnostics/"
        "split_freeze_ablation__full_fused__type_slug__xgboost__20260519T010101Z__aaaaaa.csv"
    ) in target_set
    assert "runs/20260519T020202Z__bbbbbb/diagnostics/feature_build_coverage.latest.json" not in target_set


def test_collect_targets_prunes_repo_root_legacy_short_name_logs(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    (logs_root / "menu.log").write_text("", encoding="utf-8")
    (logs_root / "database.log").write_text("legacy\n", encoding="utf-8")

    monkeypatch.setattr(coa, "project_logs_root", lambda: logs_root)

    targets = coa._collect_targets(  # pylint: disable=protected-access
        output_dir,
        keep_run_ids=set(),
        keep_runtime_logs=0,
    )

    target_set = {path for path in targets}
    assert logs_root / "menu.log" in target_set
    assert logs_root / "database.log" in target_set


def test_collect_targets_prunes_legacy_runtime_category_logs_for_old_runs(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    logs_root = tmp_path / "logs"
    runtime_old = logs_root / "runtime" / "20260519T010101Z__aaaaaa"
    runtime_keep = logs_root / "runtime" / "20260519T020202Z__bbbbbb"
    runtime_old.mkdir(parents=True, exist_ok=True)
    runtime_keep.mkdir(parents=True, exist_ok=True)
    (runtime_old / "ml.log").write_text("legacy\n", encoding="utf-8")
    (runtime_old / "pipeline_runtime_console_20260519T010101Z__aaaaaa.log").write_text("tee\n", encoding="utf-8")
    (runtime_keep / "ml.log").write_text("legacy\n", encoding="utf-8")

    monkeypatch.setattr(coa, "project_logs_root", lambda: logs_root)

    targets = coa._collect_targets(  # pylint: disable=protected-access
        output_dir,
        keep_run_ids={"20260519T020202Z__bbbbbb"},
        keep_runtime_logs=5,
    )

    target_set = {path for path in targets}
    assert runtime_old / "ml.log" in target_set
    assert runtime_keep / "ml.log" not in target_set


def test_discover_recent_run_ids_preserves_mtime_order_not_lexicographic(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    runs_dir = output_dir / "runs"
    older = _make_run(output_dir, "20260519T090000Z__zzzzzz")
    newer = _make_run(output_dir, "20260519T080000Z__aaaaaa")

    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    os.utime(runs_dir, (200, 200))

    keep = coa._discover_recent_run_ids(output_dir, keep_latest_runs=1)  # pylint: disable=protected-access

    assert keep == {"20260519T080000Z__aaaaaa"}


def test_discover_recent_run_ids_prefers_canonical_latest_run_pointer(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    (output_dir / "diagnostics").mkdir(parents=True, exist_ok=True)
    _make_run(output_dir, "20260519T071502Z__c09270")
    _make_run(output_dir, "20260519T070012Z__0e798e")
    (output_dir / "diagnostics" / "latest_run_pointer.json").write_text(
        '{"run_id":"20260519T071502Z__c09270"}',
        encoding="utf-8",
    )

    keep = coa._discover_recent_run_ids(output_dir, keep_latest_runs=1)  # pylint: disable=protected-access

    assert keep == {"20260519T071502Z__c09270"}


def test_sync_promoted_latest_run_pointers_uses_canonical_pointer(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    diagnostics_dir = output_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "latest_run_pointer.json").write_text(
        json.dumps(
            {
                "created_at_utc": "2026-05-19T07:15:02.442806+00:00",
                "run_id": "20260519T071502Z__c09270",
                "run_root": "/tmp/output/runs/20260519T071502Z__c09270",
            }
        ),
        encoding="utf-8",
    )

    changed = coa._sync_promoted_latest_run_pointers(output_dir)  # pylint: disable=protected-access

    assert changed is True
    assert (output_dir / "promoted" / "latest_run.txt").read_text(encoding="utf-8").strip() == (
        "20260519T071502Z__c09270"
    )
    payload = json.loads((output_dir / "promoted" / "latest_run_manifest.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "20260519T071502Z__c09270"
    assert payload["run_root"] == "/tmp/output/runs/20260519T071502Z__c09270"


def test_cleanup_main_syncs_promoted_pointers_even_without_delete_targets(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "output"
    diagnostics_dir = output_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    promoted_dir = output_dir / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "latest_run_pointer.json").write_text(
        json.dumps(
            {
                "created_at_utc": "2026-05-19T07:15:02.442806+00:00",
                "run_id": "20260519T071502Z__c09270",
                "run_root": "/tmp/output/runs/20260519T071502Z__c09270",
            }
        ),
        encoding="utf-8",
    )
    (promoted_dir / "latest_run.txt").write_text("old_run\n", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        ["cleanup_output_artifacts.py", "--output-dir", str(output_dir), "--apply"],
    )

    coa.main()

    out = capsys.readouterr().out
    assert "No cleanup targets found. Synced promoted latest-run pointers." in out
    assert (promoted_dir / "latest_run.txt").read_text(encoding="utf-8").strip() == "20260519T071502Z__c09270"


def test_cleanup_main_prunes_empty_runtime_dirs_even_without_other_targets(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_root = tmp_path / "logs"
    empty_runtime_dir = logs_root / "runtime" / "20260519T010101Z__aaaaaa"
    empty_runtime_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(coa, "project_logs_root", lambda: logs_root)
    monkeypatch.setattr(
        "sys.argv",
        ["cleanup_output_artifacts.py", "--output-dir", str(output_dir), "--apply"],
    )

    coa.main()

    out = capsys.readouterr().out
    assert "Removed 1 empty runtime log directory" in out
    assert not empty_runtime_dir.exists()


def test_prune_empty_runtime_log_dirs_removes_empty_run_dirs(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    empty_run = logs_root / "runtime" / "20260519T010101Z__aaaaaa"
    keep_run = logs_root / "runtime" / "20260519T020202Z__bbbbbb"
    empty_run.mkdir(parents=True, exist_ok=True)
    keep_run.mkdir(parents=True, exist_ok=True)
    (keep_run / "pipeline_runtime_console_20260519T020202Z__bbbbbb.log").write_text("tee\n", encoding="utf-8")

    removed = coa._prune_empty_runtime_log_dirs(logs_root)  # pylint: disable=protected-access

    assert removed >= 1
    assert not empty_run.exists()
    assert keep_run.exists()
