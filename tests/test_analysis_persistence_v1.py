"""Native analytical persistence, exact membership and assessment isolation."""

import json
import os
from pathlib import Path
from copy import deepcopy
import pytest
from obsidiandroid.analysis_persistence.contract import (
    artifact,
    digest,
    validate_result,
)
from obsidiandroid.analysis_persistence.service import AnalysisStore


@pytest.fixture
def payload(tmp_path):
    hashes = [f"{i:064x}" for i in range(1, 5)]
    spec = {
        "profile": "diagnostic",
        "mode": "supervised",
        "code": {"git_commit": "a" * 40, "worktree_sha256": "b" * 64},
        "feature_schema": ["permission_count"],
        "source_digests": {"fixture": "c" * 64},
        "cohort_id": "fixture",
        "evidence_cutoff": "2026-09-21T00:00:00Z",
        "seeds": {"split": 42},
        "label_authority": "synthetic_test_only",
    }
    split = {h: ("train" if i < 2 else "test") for i, h in enumerate(hashes)}
    predictions = [
        {
            "sha256": h,
            "status": "PREDICTED",
            "actual": "family_a",
            "predicted": "family_a",
            "score": 0.9,
        }
        for h in hashes
    ]
    model = {
        "key": "fixture",
        "implementation": "synthetic",
        "parameters": {},
        "dimension": "family",
        "feature_schema": spec["feature_schema"],
        "training_digest": digest(hashes[:2]),
        "library_versions": {"test": "1"},
        "seed": 42,
        "split_contract": {
            "members": split,
            "seed": 42,
            "stratification": "none",
            "labels": dict.fromkeys(hashes, "family_a"),
        },
        "predictions": predictions,
        "metrics": {
            "accuracy": 1.0,
            "per_class": {
                "family_a": {"precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 2}
            },
        },
        "confusion": [{"true": "family_a", "predicted": "family_a", "count": 2}],
    }
    (tmp_path / "metrics.json").write_text("{}")
    result = {
        "members": [
            {
                "sha256": h,
                "role": split[h],
                "eligibility": "ELIGIBLE",
                "outcome": "PREDICTED",
            }
            for h in hashes
        ],
        "models": [model],
        "artifacts": [artifact(tmp_path, "metrics.json", kind="metrics")],
    }
    return spec, result, tmp_path


def test_exact_membership_and_model_contract(payload):
    spec, result, _ = payload
    assert len(validate_result(spec, result)) == 64
    for mutation in ("duplicate", "missing", "training", "confusion", "secret"):
        bad = deepcopy(result)
        if mutation == "duplicate":
            bad["members"].append(bad["members"][0])
        elif mutation == "missing":
            bad["models"][0]["predictions"].pop()
        elif mutation == "training":
            bad["models"][0]["training_digest"] = "a" * 64
        elif mutation == "confusion":
            bad["models"][0]["confusion"][0]["count"] = 3
        else:
            bad["password"] = "do-not-store"
        with pytest.raises(ValueError):
            validate_result(spec, bad)


def test_artifact_path_and_hash(payload):
    _, result, root = payload
    with pytest.raises(ValueError):
        artifact(root, "../metrics.json", kind="bad")
    (root / "link").symlink_to(root / "metrics.json")
    with pytest.raises(ValueError):
        artifact(root, "link", kind="bad")
    old = result["artifacts"][0]
    (root / "metrics.json").write_text("changed")
    assert artifact(root, "metrics.json", kind="metrics")["sha256"] != old["sha256"]


@pytest.fixture
def store():
    path = os.environ.get("OBSIDIAN_ANALYSIS_TEST_CONFIG")
    if not path:
        pytest.skip("Explicit disposable database required")
    import mysql.connector

    db = "obsidiandroid_core_persistence_test_20260921_analysis"
    return AnalysisStore(
        lambda: mysql.connector.connect(option_files=path, database=db), database=db
    )


def test_lifecycle_replay_and_database_immutability(store, payload):
    spec, result, root = payload
    rid = store.begin_run(spec)
    assert store.show(rid)["run"]["run_status"] == "running"
    assert store.finalize_run(rid, result, artifact_root=root)["status"] == "SUCCEEDED"
    assert (
        store.finalize_run(rid, result, artifact_root=root)["status"] == "EXACT_REPLAY"
    )
    record = store.show(rid)
    assert len(record["core_run_sample"]) == 4
    assert len(record["prediction"]) == 4
    assert len(record["split_ledger"]) == 4
    assert record["model_execution"][0]["promoted_flag"] == 0
    again = store.begin_run(spec)
    store.finalize_run(again, result, artifact_root=root)
    assert store.show(again)["run"]["replay_of_run_id"] is not None
    for sql, args in [
        ("UPDATE core_run SET run_status=%s WHERE run_id=%s", ("running", rid)),
        (
            "DELETE FROM prediction WHERE model_execution_id=%s",
            (record["model_execution"][0]["model_execution_id"],),
        ),
        ("UPDATE core_run_sample SET sha256=%s WHERE run_id=%s", ("a" * 64, rid)),
    ]:
        with pytest.raises(Exception), store.transaction() as c, c.cursor() as q:
            q.execute(sql, args)
    with store.transaction(True) as c, c.cursor() as q:
        q.execute("SELECT COUNT(*) FROM core_assessment_revision")
        assert q.fetchone()[0] == 0


def test_failure_cancel_and_atomic_finalize(store, payload):
    spec, result, root = payload
    rid = store.begin_run(spec)
    (root / "metrics.json").write_text("changed")
    with pytest.raises(ValueError):
        store.finalize_run(rid, result, artifact_root=root)
    assert not store.show(rid)["prediction"]
    store.fail_run(rid, stage="artifact_validation", error_type="ValueError")
    assert store.show(rid)["run"]["run_status"] == "failed"
    with pytest.raises(ValueError):
        store.finalize_run(rid, result, artifact_root=root)
    rid2 = store.begin_run(spec)
    store.fail_run(
        rid2, stage="operator", error_type="KeyboardInterrupt", cancelled=True
    )
    assert store.show(rid2)["run"]["run_status"] == "cancelled"


def test_multi_model_dimensions_states_and_artifact_loss(store, payload, tmp_path):
    from obsidiandroid.analysis_persistence.export import export_run

    spec, result, root = payload
    second = deepcopy(result["models"][0])
    second.update(key="type_model", dimension="type", feature_schema=["type_feature"])
    spec["model_feature_schemas"] = {
        "fixture": spec["feature_schema"],
        "type_model": ["type_feature"],
    }
    second["predictions"][0] = {
        "sha256": result["members"][0]["sha256"],
        "status": "MODEL_ERROR",
        "reason": "SyntheticInferenceError",
    }
    result["models"].append(second)
    rid = store.begin_run(spec)
    store.finalize_run(rid, result, artifact_root=root)
    record = store.show(rid)
    assert len(record["feature_contract"]) == 2
    assert {m["evaluation_scope"] for m in record["model_execution"]} == {
        "family",
        "type",
    }
    assert len(record["prediction"]) == 8
    (root / "metrics.json").write_text("changed")
    changed = export_run(store, rid, tmp_path / "changed_export")
    assert changed["artifact_checks"][0]["status"] != "verified"
    (root / "metrics.json").unlink()
    missing = export_run(store, rid, tmp_path / "missing_export")
    assert missing["database_export_complete"] is True
    assert missing["artifact_checks"][0]["status"] != "verified"


def test_concurrent_same_run_finalization(store, payload):
    from concurrent.futures import ThreadPoolExecutor

    spec, result, root = payload
    rid = store.begin_run(spec)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: store.finalize_run(rid, result, artifact_root=root), range(2)
            )
        )
    assert sorted(r["status"] for r in results) == ["EXACT_REPLAY", "SUCCEEDED"]
    assert len(store.show(rid)["prediction"]) == 4


def test_pipeline_capture_retains_exclusion_and_target(store, tmp_path, monkeypatch):
    import pandas as pd
    import joblib
    from sklearn.linear_model import LogisticRegression
    from config import app_config
    from obsidiandroid.analysis_persistence.pipeline_bridge import (
        ACTIVE,
        PipelineCapture,
        capture_cohort,
        capture_model,
    )

    root = Path(__file__).resolve().parents[1]
    capture = PipelineCapture(store, "dev_smoke", root, tmp_path / "capture")
    capture.expected_models = ["logistic_regression"]
    token = ACTIVE.set(capture)
    try:
        capture_cohort(
            pd.DataFrame(
                {"sample_id": range(1, 6), "sha256": [f"{i:064x}" for i in range(1, 6)]}
            )
        )
        features = pd.DataFrame({"permission_count": [0, 1, 0, 1]}, index=[1, 2, 3, 4])
        labels = pd.Series(
            ["rat", "banker", "rat", "banker"], index=features.index, name="type_slug"
        )
        model = LogisticRegression(random_state=17).fit(
            features.iloc[:2], labels.iloc[:2]
        )
        model_path = tmp_path / "model.joblib"
        joblib.dump(model, model_path)
        predictions = model.predict(features)
        result = {
            "model": model,
            "sample_ids_train": [1, 2],
            "sample_ids_test": [3, 4],
            "prediction_metadata": {
                i: {
                    "decoded_label": str(predictions[n]),
                    "confidence": float(model.predict_proba(features)[n].max()),
                }
                for n, i in enumerate(features.index)
            },
            "true_labels": labels.to_dict(),
            "export_paths": {"model_path": str(model_path)},
        }
        monkeypatch.setattr(
            app_config,
            "RUNTIME_SPLIT_METADATA",
            {
                "split_seed": 17,
                "split_algorithm": "fixture",
                "label_target": "type_slug",
            },
            raising=False,
        )
        capture_model("logistic_regression", result, features, labels)
        assert capture.finish()["status"] == "SUCCEEDED"
        record = store.show(capture.run_id)
        assert len(record["core_run_sample"]) == len(record["prediction"]) == 5
        assert record["model_execution"][0]["evaluation_scope"] == "type"
        assert (
            sum(p["prediction_status"] == "EXCLUDED" for p in record["prediction"]) == 1
        )
        assert len(record["split_ledger"]) == 5
    finally:
        ACTIVE.reset(token)


def test_failure_context_and_all_outcome_states(store, payload):
    spec, result, root = payload
    for status in (
        "EXCLUDED",
        "FEATURE_INCOMPLETE",
        "LABEL_UNAVAILABLE",
        "MODEL_ERROR",
        "INVALID_ARTIFACT",
        "NOT_APPLICABLE",
    ):
        changed = deepcopy(result)
        for row in changed["models"][0]["predictions"]:
            row.pop("predicted")
            row["status"] = status
            row["reason"] = "controlled_fixture"
        changed["models"][0]["confusion"] = []
        assert validate_result(spec, changed)
    rid = store.begin_run(spec)
    context = {
        "members": [{"sha256": m["sha256"]} for m in result["members"]],
        "finalization_complete": False,
    }
    store.fail_run(
        rid, stage="model_training", error_type="ValueError", context=context
    )
    meta = json.loads(store.show(rid)["run"]["metadata_json"])
    assert meta["partial_evidence"] == context
    assert any(r["run_id"] == rid for r in store.history())


def test_hyperparameter_nan_is_explicit_not_invalid_json():
    from obsidiandroid.analysis_persistence.pipeline_bridge import _plain
    from obsidiandroid.analysis_persistence.contract import canonical

    assert (
        canonical(_plain({"missing": float("nan")}))
        == '{"missing":{"__float__":"NaN"}}'
    )
