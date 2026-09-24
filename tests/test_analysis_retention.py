"""Offline regression coverage for retained analytical artifacts and inspection."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from obsidiandroid.analysis_persistence.export import export_run, verify_artifacts
from obsidiandroid.cli import analysis


@pytest.fixture
def record(tmp_path):
    model = tmp_path / "model.joblib"
    model.write_bytes(b"opaque model bytes; never deserialize")
    return {
        "run": {"run_id": "fixture", "metadata_json": json.dumps({"artifact_root": str(tmp_path)})},
        "core_artifact": [{
            "immutable_relative_path": model.name,
            "artifact_role": "model",
            "required_flag": 1,
            "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "byte_size": model.stat().st_size,
        }],
    }


def test_verify_reports_changed_missing_and_unsafe(record, tmp_path):
    assert verify_artifacts(record)["status"] == "verified"
    path = tmp_path / "model.joblib"
    path.write_bytes(b"changed")
    assert verify_artifacts(record)["artifact_checks"][0]["status"] == "changed"
    path.unlink()
    assert verify_artifacts(record)["status"] == "unverified_artifacts"
    other = tmp_path / "other"
    other.write_bytes(b"opaque model bytes; never deserialize")
    path.symlink_to(other)
    assert verify_artifacts(record)["artifact_checks"][0]["status"] == "missing_or_unsafe"
    record["core_artifact"][0]["immutable_relative_path"] = "../other"
    assert verify_artifacts(record)["artifact_checks"][0]["status"] == "missing_or_unsafe"


@pytest.mark.parametrize("root", [None, "", "relative", 12])
def test_export_preserves_db_records_when_root_unavailable(record, tmp_path, root):
    record["run"]["metadata_json"] = json.dumps({"artifact_root": root})
    destination = tmp_path / "export"
    store = SimpleNamespace(show=lambda _: deepcopy(record))
    result = export_run(store, "fixture", destination)
    assert result["database_export_complete"] is True
    assert result["artifact_verification_status"] == "unverified_artifacts"
    assert result["artifact_checks"][0]["status"] == "root_unavailable"
    assert json.loads((destination / "run.json").read_text()) == record["run"]
    for line in (destination / "checksums.sha256").read_text().splitlines():
        expected, name = line.split("  ")
        assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected


def test_empty_artifacts_do_not_claim_verified(record):
    record["core_artifact"] = []
    assert verify_artifacts(record)["status"] == "no_registered_artifacts"


@pytest.mark.parametrize("argv", [
    ["show"], ["verify"], ["export", "--run-id", "fixture"],
    ["run"], ["history", "--persist"], ["history", "--plan-only"],
    ["show", "--run-id", "fixture", "--output", "unused"],
])
def test_invalid_cli_requests_do_not_connect(monkeypatch, argv):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid request opened a connection")
    monkeypatch.setattr(analysis, "configured_store", forbidden)
    with pytest.raises(SystemExit) as exc:
        analysis.main(argv)
    assert exc.value.code == 2


def test_verify_cli_is_read_only_and_signals_artifact_loss(record, tmp_path, monkeypatch, capsys):
    store = SimpleNamespace(show=lambda _: deepcopy(record))
    monkeypatch.setattr(analysis, "configured_store", lambda *args: store)
    before = sorted(p.name for p in tmp_path.iterdir())
    assert analysis.main(["verify", "--run-id", "fixture"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    (tmp_path / "model.joblib").unlink()
    assert analysis.main(["verify", "--run-id", "fixture"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unverified_artifacts"


@pytest.mark.parametrize("metadata_state", ["present", "absent", "missing", "symlink"])
def test_capture_retains_metadata_and_rejects_lost_advertised_sidecar(tmp_path, monkeypatch, metadata_state):
    import pandas as pd
    from config import app_config
    from obsidiandroid.analysis_persistence.pipeline_bridge import PipelineCapture

    # Exercise capture without a database, estimator fitting or deserialization.
    capture = PipelineCapture.__new__(PipelineCapture)
    capture.cohort = {1: "1" * 64, 2: "2" * 64}
    capture.models = []
    capture.refs = []
    capture.spec = {"seeds": {}, "source_digests": {}}
    capture.output = tmp_path / "retained"
    capture.output.mkdir()
    model = tmp_path / "model.joblib"
    model.write_bytes(b"opaque")
    sidecar = tmp_path / "metadata.json"
    sidecar.write_text('{"label_name_map":{"0":"family_a"}}')
    paths = {"model_path": str(model)}
    if metadata_state != "absent":
        paths["metadata_path"] = str(sidecar)
    if metadata_state == "missing":
        sidecar.unlink()
    elif metadata_state == "symlink":
        sidecar.unlink()
        sidecar.symlink_to(model)
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_METADATA", {
        "split_seed": 17, "split_algorithm": "fixture", "label_target": "family",
    }, raising=False)
    result = {
        "model": SimpleNamespace(get_params=lambda **kwargs: {"random_state": 17}),
        "sample_ids_train": [1], "sample_ids_test": [2],
        "prediction_metadata": {i: {"decoded_label": "family_a"} for i in (1, 2)},
        "true_labels": {1: "family_a", 2: "family_a"}, "export_paths": paths,
    }
    features = pd.DataFrame({"permission_count": [0, 1]}, index=[1, 2])
    if metadata_state in {"missing", "symlink"}:
        with pytest.raises(ValueError, match="metadata export missing/unsafe"):
            capture.model("fixture", result, features, None)
        assert not capture.models
        return
    capture.model("fixture", result, features, None)
    retained = [r for r in capture.refs if r["kind"] == "fixture_model_metadata"]
    if metadata_state == "present":
        assert len(retained) == 1
        assert (capture.output / retained[0]["path"]).read_bytes() == sidecar.read_bytes()
        assert capture.models[0]["metadata_artifact"] == "fixture_model_metadata"
        sidecar.unlink()
        assert (capture.output / retained[0]["path"]).exists()
    else:
        assert not retained
        assert capture.models[0]["metadata_artifact"] is None
