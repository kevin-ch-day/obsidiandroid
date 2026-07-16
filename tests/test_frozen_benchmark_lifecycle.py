import json
from pathlib import Path

import pytest

from obsidiandroid.governance.frozen_benchmark_lifecycle import FrozenBenchmarkLifecycle


def _write(root: Path, name: str):
    path = root / name
    path.write_text(name, encoding="utf-8")
    return path


def _prepare(life, root):
    for name in ("cohort", "split", "features", "models", "sources"):
        life.record_artifact(name, _write(root, f"{name}.json"))
    for state, required in (("COHORT_LOCKED", ("cohort", "sources")), ("SPLIT_LOCKED", ("split",)), ("FEATURE_CONTRACTS_LOCKED", ("features",)), ("MODELS_LOCKED", ("models",))):
        life.transition(state, required_artifacts=required)


def test_persisted_lifecycle_seals_one_atomic_evaluation(tmp_path):
    life = FrozenBenchmarkLifecycle(tmp_path, "synthetic")
    _prepare(life, tmp_path)
    plan = {"arms": ["A", "B", "C"], "models": ["random_forest", "logistic_regression", "xgboost"], "sensitivity_contrasts": [("B", "detection_only"), ("B", "detection_plus_mask"), ("C", "detection_only"), ("C", "detection_plus_mask")], "paired_comparisons": ["B-A", "C-A", "C-B"], "metrics": ["macro_f1"]}
    life.authorize(plan=plan, clean_tree=True, source_commit="a", dependency_hash="b", approved_manifest_hash="c")
    cells = {"A:random_forest", "A:logistic_regression"}
    with pytest.raises(ValueError, match="complete"):
        life.complete_evaluation(execution_cells=cells, required_cells={"A:random_forest", "B:random_forest"}, prediction_path=_write(tmp_path, "p.csv"), comparison_path=_write(tmp_path, "c.csv"))
    life.complete_evaluation(execution_cells=cells, required_cells=cells, prediction_path=_write(tmp_path, "p.csv"), comparison_path=_write(tmp_path, "c.csv"))
    assert json.loads((tmp_path / "frozen_benchmark_manifest.json").read_text())["state"] == "HELDOUT_EVALUATED"
    with pytest.raises(ValueError, match="sealed"):
        life.complete_evaluation(execution_cells=cells, required_cells=cells, prediction_path=_write(tmp_path, "p2.csv"), comparison_path=_write(tmp_path, "c2.csv"))


def test_dirty_and_latest_evidence_fail_closed(tmp_path):
    life = FrozenBenchmarkLifecycle(tmp_path, "synthetic")
    with pytest.raises(ValueError, match="latest"):
        life.record_artifact("bad", _write(tmp_path, "x.latest.csv"))
    _prepare(life, tmp_path)
    with pytest.raises(ValueError, match="clean"):
        life.authorize(plan={"arms": ["A", "B", "C"], "models": ["random_forest", "logistic_regression", "xgboost"], "sensitivity_contrasts": [("B", "detection_only"), ("B", "detection_plus_mask"), ("C", "detection_only"), ("C", "detection_plus_mask")], "paired_comparisons": ["B-A", "C-A", "C-B"], "metrics": ["macro_f1"]}, clean_tree=False, source_commit="a", dependency_hash="b", approved_manifest_hash="c")
