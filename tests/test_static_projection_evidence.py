"""Static APK declaration provenance is independent of PI source labels."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.orchestration.static_projection_evidence import (
    _semantic_digest, load_static_projection_evidence,
)
from obsidiandroid.orchestration.source_aware_permission_features import (
    _token_feature, _build_from_verified_evidence,
)


SHA = "a" * 64
TOKEN = "android.permission.INTERNET"


def build_source_aware_permission_features(*args, **kwargs):
    """Exercise feature semantics only; public direct-frame entry is prohibited."""
    path = Path(__file__).resolve()
    return _build_from_verified_evidence(
        *args, **kwargs, source_snapshot_digest="a" * 64,
        source_file_bindings=((str(path), hashlib.sha256(path.read_bytes()).hexdigest()),),
    )


def _fixture(tmp_path, *, state="PROJECTED_KNOWN"):
    baseline = {
        "sha256": SHA, "runtime_evidence_used": False,
        "static": {"status": "VALID_APK", "extracted_sha256": SHA,
                   "permissions": [TOKEN]},
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))
    baseline_digest = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    occurrence_body = {
        "occurrence_role": "MANIFEST_USES_PERMISSION",
        "evidence_layer": "DIRECT_MANIFEST", "semantic_claim": "PERMISSION_REQUEST",
        "subject": {"artifact_sha256": SHA},
        "identity": {"raw_token": TOKEN, "projected_pi_token": TOKEN},
        "provenance": {"source_artifact_sha256": baseline_digest,
                       "evidence_locator": "/static/permissions/0"},
    }
    occurrence = {
        **occurrence_body,
        "occurrence_evidence_digest": _semantic_digest(occurrence_body),
    }
    projection_body = {
        "contract": "pi.static-declaration-projection.v1", "sha256": SHA,
        "baseline_sha256": baseline_digest, "declared_count": 1,
        "occurrence_complete": True,
        "rows": [{"raw_token": TOKEN, "state": state, "occurrence": occurrence}],
    }
    projection = {**projection_body, "projection_digest": _semantic_digest(projection_body)}
    projection_path = tmp_path / "projection.json"
    projection_path.write_text(json.dumps(projection))
    return baseline_path, projection_path


def test_verified_static_projection_yields_manifest_only_feature(tmp_path) -> None:
    baseline_path, projection_path = _fixture(tmp_path)
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    evidence = load_static_projection_evidence(
        samples, [projection_path], baseline_paths_by_sha={SHA: baseline_path},
        expected_projection_digests_by_sha={SHA: json.loads(projection_path.read_text())["projection_digest"]},
    )
    result = build_source_aware_permission_features(
        samples, evidence, training_sample_ids=[1]
    )
    assert result.loc[0, _token_feature(TOKEN, "manifest")] == 1
    assert result.loc[0, "perm_status__provider_missing"] == 1


def test_unresolved_manifest_token_stays_unresolved(tmp_path) -> None:
    baseline_path, projection_path = _fixture(tmp_path, state="UNRESOLVED")
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    evidence = load_static_projection_evidence(
        samples, [projection_path], baseline_paths_by_sha={SHA: baseline_path},
        expected_projection_digests_by_sha={SHA: json.loads(projection_path.read_text())["projection_digest"]},
    )
    result = build_source_aware_permission_features(
        samples, evidence, training_sample_ids=[1]
    )
    assert result.loc[0, "perm_status__unresolved_count"] == 1
    assert not any(name.startswith("perm_manifest__") for name in result.columns)


def test_static_baseline_or_projection_tamper_fails_closed(tmp_path) -> None:
    baseline_path, projection_path = _fixture(tmp_path)
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    with pytest.raises(ValueError, match="reviewed digest"):
        load_static_projection_evidence(
            samples, [projection_path], baseline_paths_by_sha={SHA: baseline_path},
            expected_projection_digests_by_sha={SHA: "0" * 64},
        )
    baseline_path.write_text(baseline_path.read_text() + " ")
    with pytest.raises(ValueError, match="baseline file digest"):
        load_static_projection_evidence(
            samples, [projection_path], baseline_paths_by_sha={SHA: baseline_path},
            expected_projection_digests_by_sha={SHA: json.loads(projection_path.read_text())["projection_digest"]},
        )


def test_verified_empty_manifest_is_coverage_without_positive_permission(tmp_path) -> None:
    baseline_path, projection_path = _fixture(tmp_path)
    baseline = json.loads(baseline_path.read_text())
    baseline["static"]["permissions"] = []
    baseline_path.write_text(json.dumps(baseline))
    body = json.loads(projection_path.read_text())
    body["baseline_sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    body["declared_count"] = 0
    body["rows"] = []
    body["projection_digest"] = _semantic_digest({
        key: value for key, value in body.items() if key != "projection_digest"
    })
    projection_path.write_text(json.dumps(body))
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    evidence = load_static_projection_evidence(
        samples, [projection_path], baseline_paths_by_sha={SHA: baseline_path},
        expected_projection_digests_by_sha={SHA: body["projection_digest"]},
    )
    features = build_source_aware_permission_features(
        samples, evidence, training_sample_ids=[1]
    )
    assert features.loc[0, "perm_status__has_manifest_parse"] == 1
    assert features.loc[0, "perm_status__manifest_missing"] == 0
    assert features.loc[0, "perm_status__unresolved_count"] == 0
    assert not any(name.startswith("perm_manifest__") for name in features.columns)
