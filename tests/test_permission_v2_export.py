"""Disposable fixture authority for the unpublished V2 research consumer."""

import hashlib
import json
import os
import stat

import pandas as pd
import pytest

from obsidiandroid.orchestration import permission_v2_export as v2
from obsidiandroid.pipeline import stage_ablation, stage_feature_enrichment


def _fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(v2, "FROZEN_SAMPLE_COUNT", 1)
    sample = pd.DataFrame({"sample_id": [7], "sha256": ["a" * 64]})
    export = {
        "format": v2.EXPORT_FORMAT,
        "manifest_sha256": v2.FROZEN_MANIFEST_SHA256,
        "source_commit": "c" * 40, "source_authority_digest": "d" * 64,
        "projection_policy_version": "projection-v2",
        "interpretation_release": "unresolved-v1",
        "feature_contract": v2.CONTRACT_VERSION, "completeness": "COMPLETE",
        "samples": [{"sample_id": 7, "sha256": "a" * 64,
                     "source_snapshot_digest": "e" * 64,
                     "evidence_state": "PROVIDER_REPORTED_UNRESOLVED",
                     "members": [{"raw_token": "android.permission.INTERNET",
                                  "projected_token": "android.permission.internet"}]}],
    }
    path = tmp_path / "export.json"
    data = json.dumps(export, sort_keys=True).encode()
    path.write_bytes(data)
    anchor = {"format": v2.ANCHOR_FORMAT,
              "approved_export_sha256": hashlib.sha256(data).hexdigest(),
              **{key: export[key] for key in v2._BOUND_FIELDS}}
    anchor_bytes = json.dumps(anchor, sort_keys=True).encode()
    monkeypatch.setattr(v2, "_trusted_anchor_bytes", lambda: anchor_bytes)
    return sample, path, export, anchor


def test_v2_export_is_unresolved_and_anchor_bound(monkeypatch, tmp_path):
    samples, path, _export, _anchor = _fixture(monkeypatch, tmp_path)
    frame = v2.build_v2_unresolved_features(
        samples, path, training_sample_ids=[7], min_support=1)
    occurrence = [column for column in frame if column.startswith("perm_provider_unresolved__")]
    assert len(occurrence) == 1 and frame.loc[0, occurrence[0]] == 1
    assert frame.loc[0, "perm_status__manifest_verified"] == 0
    assert not any(column.startswith("perm_provider__") for column in frame)
    v2.assert_verified_v2_frame(frame, samples=samples, training_sample_ids=[7],
                                min_support=1)
    flags = {"permission_feature_contract_version": v2.CONTRACT_VERSION,
             "permission_training_sample_ids": [7],
             "enable_sample_metadata_features": False}
    from config import app_config
    monkeypatch.setattr(app_config, "PERMISSION_MIN_SUPPORT", 1, raising=False)
    fused = stage_feature_enrichment.merge_sample_metadata_features(
        pd.DataFrame({"sample_id": [7]}), samples, flags, frame)
    assert fused.loc[0, occurrence[0]] == 1
    assert stage_ablation.run_ablation_experiments(
        samples, pd.DataFrame(), {}, frame, [], "test-v2") == []


def test_tamper_wrong_anchor_and_stale_cache_fail(monkeypatch, tmp_path):
    samples, path, export, anchor = _fixture(monkeypatch, tmp_path)
    frame = v2.build_v2_unresolved_features(
        samples, path, training_sample_ids=[7], min_support=1)
    changed = frame.copy()
    column = next(name for name in changed if name.startswith("perm_provider_unresolved__"))
    changed[column] = 0
    with pytest.raises(ValueError, match="cached frame"):
        v2.assert_verified_v2_frame(changed, samples=samples,
                                    training_sample_ids=[7], min_support=1)
    anchor["interpretation_release"] = "changed"
    monkeypatch.setattr(v2, "_trusted_anchor_bytes", lambda: json.dumps(anchor).encode())
    with pytest.raises(ValueError, match="approval differs"):
        v2.assert_verified_v2_frame(frame, samples=samples,
                                    training_sample_ids=[7], min_support=1)
    anchor["interpretation_release"] = export["interpretation_release"]
    path.write_text(json.dumps({**export, "completeness": "INCOMPLETE"}))
    with pytest.raises(ValueError, match="bytes differ"):
        v2.build_v2_unresolved_features(samples, path, training_sample_ids=[7])


@pytest.mark.parametrize("mutation", [
    lambda x: x["samples"][0].pop("source_snapshot_digest"),
    lambda x: x["samples"][0].update({"evidence_state": "ACCEPTED_ALIAS"}),
    lambda x: x.update({"feature_contract": "unknown-v9"}),
    lambda x: x["samples"][0]["members"].append(
        {"raw_token": "android.permission.INTERNET",
         "projected_token": "android.permission.internet"}),
    lambda x: x["samples"][0].update({"members": []}),
])
def test_invalid_content_rejected_even_with_fixture_anchor(monkeypatch, tmp_path, mutation):
    samples, path, export, anchor = _fixture(monkeypatch, tmp_path)
    mutation(export)
    data = json.dumps(export).encode()
    path.write_bytes(data)
    anchor["approved_export_sha256"] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(v2, "_trusted_anchor_bytes", lambda: json.dumps(anchor).encode())
    with pytest.raises(ValueError):
        v2.build_v2_unresolved_features(samples, path, training_sample_ids=[7])


def test_approved_bytes_with_duplicate_json_key_still_fail(monkeypatch, tmp_path):
    samples, path, export, anchor = _fixture(monkeypatch, tmp_path)
    data = json.dumps(export).replace('"format":', '"format": "shadow", "format":', 1).encode()
    path.write_bytes(data)
    anchor["approved_export_sha256"] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(v2, "_trusted_anchor_bytes", lambda: json.dumps(anchor).encode())
    with pytest.raises(ValueError, match="duplicate"):
        v2.build_v2_unresolved_features(samples, path, training_sample_ids=[7])


def test_approval_and_export_reads_refuse_symlinks_and_fifo(monkeypatch, tmp_path):
    anchor_reader = v2._trusted_anchor_bytes
    samples, path, _export, _anchor = _fixture(monkeypatch, tmp_path)
    linked_export = tmp_path / "linked-export.json"
    linked_export.symlink_to(path)
    with pytest.raises(ValueError, match="export is unavailable"):
        v2.build_v2_unresolved_features(samples, linked_export, training_sample_ids=[7])
    pipe = tmp_path / "export-pipe.json"
    os.mkfifo(pipe, 0o600)
    with pytest.raises(ValueError, match="not a regular file"):
        v2.build_v2_unresolved_features(samples, pipe, training_sample_ids=[7])

    anchor = tmp_path / "approval.json"
    anchor.write_text("{}")
    anchor.chmod(0o600)
    monkeypatch.setattr(v2, "_trusted_anchor_bytes", anchor_reader)
    monkeypatch.setattr(v2, "_ANCHOR_PATH", anchor)
    real_fstat = os.fstat

    def root_fstat(descriptor):
        fields = list(real_fstat(descriptor))
        fields[4] = 0
        if stat.S_ISDIR(fields[0]):
            fields[0] &= ~(stat.S_IWGRP | stat.S_IWOTH)
        return os.stat_result(fields)

    monkeypatch.setattr(v2.os, "fstat", root_fstat)
    assert v2._trusted_anchor_bytes() == b"{}"
    linked_anchor = tmp_path / "linked-approval.json"
    linked_anchor.symlink_to(anchor)
    monkeypatch.setattr(v2, "_ANCHOR_PATH", linked_anchor)
    with pytest.raises(ValueError, match="approval is unavailable"):
        v2._trusted_anchor_bytes()


def test_approved_partial_or_other_manifest_export_is_not_complete(monkeypatch, tmp_path):
    samples, path, export, anchor = _fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(v2, "FROZEN_SAMPLE_COUNT", 1813)
    with pytest.raises(ValueError, match="identity or completeness"):
        v2.build_v2_unresolved_features(samples, path, training_sample_ids=[7])
    monkeypatch.setattr(v2, "FROZEN_SAMPLE_COUNT", 1)
    export["manifest_sha256"] = "b" * 64
    data = json.dumps(export).encode()
    path.write_bytes(data)
    anchor["manifest_sha256"] = export["manifest_sha256"]
    anchor["approved_export_sha256"] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(v2, "_trusted_anchor_bytes", lambda: json.dumps(anchor).encode())
    with pytest.raises(ValueError, match="identity or completeness"):
        v2.build_v2_unresolved_features(samples, path, training_sample_ids=[7])


@pytest.mark.parametrize("sample_id", ["7", 7.0, True, 0])
def test_sample_identity_never_coerces_non_exact_ids(monkeypatch, tmp_path, sample_id):
    samples, path, _export, _anchor = _fixture(monkeypatch, tmp_path)
    samples["sample_id"] = [sample_id]
    with pytest.raises(TypeError, match="exact positive integer"):
        v2.build_v2_unresolved_features(samples, path, training_sample_ids=[7])


@pytest.mark.parametrize("training_id", ["7", 7.0, True, 0])
def test_training_membership_never_coerces_non_exact_ids(monkeypatch, tmp_path, training_id):
    samples, path, _export, _anchor = _fixture(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="exact positive integer"):
        v2.build_v2_unresolved_features(
            samples, path, training_sample_ids=[training_id])


@pytest.mark.parametrize("support", [True, 1.5, "1", 0])
def test_support_policy_requires_positive_integer(monkeypatch, tmp_path, support):
    samples, path, _export, _anchor = _fixture(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="positive integer"):
        v2.build_v2_unresolved_features(
            samples, path, training_sample_ids=[7], min_support=support)
