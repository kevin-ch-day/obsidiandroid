"""Tests for shared run-artifact lookup helpers."""

from __future__ import annotations

import json
from pathlib import Path
from obsidiandroid.cli.menu import run_locator

from obsidiandroid.cli.menu import run_artifact_state


def test_resolve_model_comparison_summary_prefers_run_scoped_exact_match(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_scoped = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_scoped.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    exact = run_scoped / f"model_comparison_summary_{run_id}.csv"
    exact.write_text("Model,Macro F1-Score\nrandom_forest,0.95\n", encoding="utf-8")
    (global_diag / f"model_comparison_summary_{run_id}.csv").write_text(
        "Model,Macro F1-Score\nxgboost,0.94\n",
        encoding="utf-8",
    )

    resolved = run_artifact_state.resolve_model_comparison_summary_csv(
        output_root=out_root,
        run_id=run_id,
    )

    assert resolved == exact


def test_resolve_within_cross_type_confusion_falls_back_to_global_bundle(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    fallback = (
        out_root
        / "bundles"
        / "latest"
        / "permission_trends"
        / "tables"
        / "confusion_within_vs_cross_type.latest.csv"
    )
    fallback.parent.mkdir(parents=True, exist_ok=True)
    fallback.write_text("run_id,error_type,count\nr1,total_error,10\n", encoding="utf-8")

    resolved = run_artifact_state.resolve_within_cross_type_confusion_csv(
        output_root=out_root,
        run_id="20260515T141956Z__58d84f",
    )

    assert resolved == fallback


def test_resolve_latest_manifest_payload_respects_output_base_full_payload(tmp_path: Path) -> None:
    out = tmp_path / "output"
    diag = out / "diagnostics"
    diag.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": "rid1", "profile_params": {"profile_id": "p1"}, "artifact_list": []}
    (diag / "run_manifest.latest.json").write_text(json.dumps(payload), encoding="utf-8")

    man, rid, path = run_locator.resolve_latest_manifest_payload(output_base=out)
    assert rid == "rid1"
    assert path == diag / "run_manifest.latest.json"
    assert man.get("profile_id") is None and (man.get("profile_params") or {}).get("profile_id") == "p1"


def test_resolve_latest_manifest_payload_follows_pointer_under_output_base(tmp_path: Path) -> None:
    out = tmp_path / "output"
    diag = out / "diagnostics"
    runs = out / "runs" / "majorfam_benchmark"
    diag.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    pointer = {"run_id": "rid2"}
    (diag / "run_manifest.latest.json").write_text(json.dumps(pointer), encoding="utf-8")
    canonical = {
        "run_id": "rid2",
        "run_slot": "majorfam_benchmark",
        "run_root": str(runs),
        "profile_params": {"profile_id": "frozen"},
    }
    (runs / "run_manifest.json").write_text(json.dumps(canonical), encoding="utf-8")

    man, rid, path = run_locator.resolve_latest_manifest_payload(output_base=out)
    assert rid == "rid2"
    assert path == runs / "run_manifest.json"
    assert (man.get("profile_params") or {}).get("profile_id") == "frozen"
