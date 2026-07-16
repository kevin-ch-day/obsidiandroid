import json
from pathlib import Path

import pytest

from obsidiandroid.governance.frozen_benchmark_lifecycle import FrozenBenchmarkLifecycle
from obsidiandroid.common.hash_utils import sha256_hex


def _write(root: Path, name: str):
    path = root / name
    path.write_text(name, encoding="utf-8")
    return path


def _prepare(life, root):
    for name in ("cohort", "split", "features", "models"):
        life.record_artifact(name, _write(root, f"{name}.json"))
    extract = _write(root, "source.csv")
    index = root / "source_snapshot_index.json"
    index.write_text(json.dumps([{"name": "cohort_labels", "path": str(extract), "sha256": sha256_hex(extract.read_text()), "run_id": life.run_id}]), encoding="utf-8")
    life.record_artifact("sources", index)
    for state, required in (("COHORT_LOCKED", ("cohort", "sources")), ("SPLIT_LOCKED", ("split",)), ("FEATURE_CONTRACTS_LOCKED", ("features",)), ("MODELS_LOCKED", ("models",))):
        life.transition(state, required_artifacts=required)


def test_persisted_lifecycle_seals_one_atomic_evaluation(tmp_path):
    life = FrozenBenchmarkLifecycle(tmp_path, "synthetic", classification="synthetic_validation")
    _prepare(life, tmp_path)
    plan = {"arms": ["A", "B", "C"], "models": ["random_forest", "logistic_regression", "xgboost"], "sensitivity_contrasts": [("B", "detection_only"), ("B", "detection_plus_mask"), ("C", "detection_only"), ("C", "detection_plus_mask")], "paired_comparisons": ["B_detection_plus_mask-B_detection_only", "C_detection_plus_mask-C_detection_only", "B-A", "C-A", "C-B"], "metrics": ["macro_f1", "weighted_f1", "accuracy", "balanced_accuracy"]}
    life.authorize(plan=plan, source_commit="a", dependency_hash="b", approved_manifest_hash="c")
    cells = [f"{arm}:{variant}:{model}" for arm in plan["arms"] for variant in (["base"] if arm == "A" else ["detection_only", "detection_plus_mask"]) for model in plan["models"]]
    with pytest.raises(ValueError, match="complete"):
        life.complete_evaluation(execution_cells=cells[:-1], prediction_path=_write(tmp_path, "p.csv"), comparison_path=_write(tmp_path, "c.csv"))
    life.complete_evaluation(execution_cells=cells, prediction_path=_write(tmp_path, "p.csv"), comparison_path=_write(tmp_path, "c.csv"))
    assert json.loads((tmp_path / "frozen_benchmark_manifest.json").read_text())["state"] == "HELDOUT_EVALUATED"
    with pytest.raises(ValueError, match="sealed"):
        life.complete_evaluation(execution_cells=cells, prediction_path=_write(tmp_path, "p2.csv"), comparison_path=_write(tmp_path, "c2.csv"))


def test_dirty_and_latest_evidence_fail_closed(tmp_path):
    life = FrozenBenchmarkLifecycle(tmp_path, "synthetic", classification="canonical")
    with pytest.raises(ValueError, match="latest"):
        life.record_artifact("bad", _write(tmp_path, "x.latest.csv"))
    _prepare(life, tmp_path)
    with pytest.raises(ValueError, match="runtime repository state"):
        life.authorize(plan={"arms": ["A", "B", "C"], "models": ["random_forest", "logistic_regression", "xgboost"], "sensitivity_contrasts": [("B", "detection_only"), ("B", "detection_plus_mask"), ("C", "detection_only"), ("C", "detection_plus_mask")], "paired_comparisons": ["B_detection_plus_mask-B_detection_only", "C_detection_plus_mask-C_detection_only", "B-A", "C-A", "C-B"], "metrics": ["macro_f1", "weighted_f1", "accuracy", "balanced_accuracy"]}, source_commit="a", dependency_hash="b", approved_manifest_hash="c")
