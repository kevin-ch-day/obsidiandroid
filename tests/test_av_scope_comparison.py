"""Tests for paired, read-only AV feature-scope comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics.av_scope_comparison import (
    build_av_scope_comparison,
    load_av_scope_run,
    render_comparison_markdown,
)


def _write_run(root: Path, *, run_id: str, scope: str, metric: float, split_hash: str = "split") -> None:
    diagnostics = root / "diagnostics"
    diagnostics.mkdir(parents=True)
    (root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": "profile",
                # The scope is the independent variable; model parameters must
                # otherwise remain frozen for a meaningful comparison.
                "model_config_hash": "frozen-model-config",
            }
        ),
        encoding="utf-8",
    )
    (diagnostics / f"feature_contract_{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "binary_feature_engine_scope": scope,
                "classification_surface": "label_independent",
                "direct_target_proxies": 0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "dataset_hash": "dataset",
                "split_hash": split_hash,
                "training_label_field": "family_id",
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "Model": ["random_forest"],
            "Macro F1-Score": [metric],
            "split_hash": [split_hash],
            "train_sample_hash": ["train"],
            "test_sample_hash": ["test"],
            "evaluation_label_hash": ["labels"],
        }
    ).to_csv(diagnostics / f"model_comparison_summary_{run_id}.csv", index=False)


def test_av_scope_comparison_requires_matched_contracts(tmp_path: Path) -> None:
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    _write_run(baseline_root, run_id="base", scope="all_observed", metric=0.70)
    _write_run(candidate_root, run_id="candidate", scope="lifecycle_included", metric=0.73)

    baseline = load_av_scope_run(baseline_root)
    candidate = load_av_scope_run(candidate_root)
    checks, deltas = build_av_scope_comparison(baseline, candidate)

    assert checks["passed"].all()
    assert deltas.iloc[0]["macro_f1_delta_candidate_minus_baseline"] == pytest.approx(0.03)
    report = render_comparison_markdown(
        baseline=baseline,
        candidate=candidate,
        checks=checks,
        deltas=deltas,
    )
    assert "status: `COMPARABLE`" in report
    assert "delta=+0.0300" in report


def test_av_scope_comparison_blocks_mismatched_split(tmp_path: Path) -> None:
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    _write_run(baseline_root, run_id="base", scope="all_observed", metric=0.70)
    _write_run(
        candidate_root,
        run_id="candidate",
        scope="lifecycle_included",
        metric=0.73,
        split_hash="different_split",
    )

    checks, deltas = build_av_scope_comparison(
        load_av_scope_run(baseline_root),
        load_av_scope_run(candidate_root),
    )

    assert not checks["passed"].all()
    assert not deltas.empty


def test_av_scope_comparison_blocks_model_retuning(tmp_path: Path) -> None:
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    _write_run(baseline_root, run_id="base", scope="all_observed", metric=0.70)
    _write_run(candidate_root, run_id="candidate", scope="lifecycle_included", metric=0.73)
    manifest_path = candidate_root / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_config_hash"] = "retuned-model-config"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    checks, _ = build_av_scope_comparison(
        load_av_scope_run(baseline_root),
        load_av_scope_run(candidate_root),
    )

    row = checks.loc[checks["check"] == "model_config_hash"].iloc[0]
    assert not bool(row["passed"])
