"""Receipt and PI join checks for the v1 permission consumer."""

from __future__ import annotations

import json
import os
from pathlib import Path
from hashlib import sha256

import pandas as pd
import pytest

from obsidiandroid.orchestration.recovery_receipt_evidence import (
    _action_source_binding, _digest, load_recovery_receipt_evidence,
    reconcile_provider_observations,
)
from obsidiandroid.orchestration.source_aware_permission_features import (
    _token_feature, _build_from_verified_evidence, CONTRACT_VERSION,
    assert_verified_source_aware_frame,
)
from obsidiandroid.orchestration import permission_features


SHA = "a" * 64
PROJECTED = "android.permission.internet"
RAW = "android.permission.INTERNET"


def build_source_aware_permission_features(*args, **kwargs):
    """Exercise feature semantics only; public direct-frame entry is prohibited."""
    path = Path(__file__).resolve()
    return _build_from_verified_evidence(
        *args, **kwargs, source_snapshot_digest="a" * 64,
        source_file_bindings=((str(path), sha256(path.read_bytes()).hexdigest()),),
    )


def _files(tmp_path):
    action_body = {
        "sample_id": 1, "sha256": SHA,
        "analysis_date_utc": "2026-10-01T00:00:00Z",
        "source_evidence_receipt_sha256": "d" * 64,
        "source_row_identity_digest": "e" * 64,
        "source_payload_hash": "f" * 64,
        "projected_permission_names": [PROJECTED],
        "token_evidence": [{
            "provider_token": RAW, "projected_pi_token": PROJECTED,
            "projection_policy_version": "provider-token-to-pi-storage-v2-width-bound",
        }],
    }
    action = {**action_body, "action_digest": _digest(action_body, newline=True)}
    plan_body = {
        "actions": [action], "plan_core_digest": "b" * 64,
        "single_use_execution_id": "00000000-0000-4000-8000-000000000001",
        "pi_catalog": "android_permission_intel",
        "primary_catalog": "erebus_threat_intel_prod",
    }
    plan = {**plan_body, "plan_digest": _digest(plan_body, newline=True)}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    plan_path.chmod(0o600)
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    receipt_body = {
        "receipt_format": "erebus-pi-production-sample-receipt-v1",
        "execution_scope": "PRODUCTION_PI_ONLY_RECOVERY",
        "production_effect": "local_permission_intel_materialization",
        "plan_digest": plan["plan_digest"],
        "plan_core_digest": plan["plan_core_digest"],
        "single_use_execution_id": plan["single_use_execution_id"],
        "action_digest": action["action_digest"],
        "action_source_binding": _action_source_binding(action),
        "provider_requests": 0, "primary_catalog_mutations": 0,
        "result": {
            "sample_id": 1, "action_digest": action["action_digest"],
            "classification": "COMPLETED", "target_pi_catalog": "android_permission_intel",
            "source_primary_catalog": "erebus_threat_intel_prod",
            "provider_requests": 0, "primary_mutations": 0,
        },
    }
    receipt = {**receipt_body, "receipt_digest": _digest(receipt_body)}
    receipt_path = receipt_dir / f"pi-production-sample-{action['action_digest']}.json"
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o600)
    return plan_path, receipt_dir, plan["plan_digest"], receipt_path


def _observation(**changes):
    value = {
        "sample_id": 1, "permission_string": PROJECTED,
        "observation_source": "virustotal", "recovery_plan_core": "b" * 64,
        "recovery_batch_id": "00000000-0000-4000-8000-000000000001",
        "event_analysis_date_utc": "2026-10-01T00:00:00Z",
        "event_source_system": "virustotal", "event_source_engine": "androguard",
        "canonical_permission": PROJECTED,
        "current_evidence_state": "ACCEPTED_CANONICAL",
        "current_identifier_kind": "PERMISSION",
        "unresolved_conflict_count": 0,
    }
    value.update(changes)
    return value


def test_receipt_verified_provider_projection_and_join(tmp_path) -> None:
    plan_path, receipt_dir, digest, _ = _files(tmp_path)
    receipts = load_recovery_receipt_evidence(
        plan_path, receipt_dir, expected_plan_digest=digest
    )
    assert receipts.iloc[0]["raw_token"] == RAW
    samples = pd.DataFrame({"sample_id": [1, 2], "sha256": [SHA, "c" * 64]})
    joined = reconcile_provider_observations(
        samples, pd.DataFrame([_observation(), _observation()]), receipts
    )
    assert len(joined) == 1
    assert joined["source_verified"].all()
    result = build_source_aware_permission_features(
        samples, joined, training_sample_ids=[1]
    ).set_index("sample_id")
    assert result.loc[1, _token_feature(PROJECTED, "provider")] == 1
    assert result.loc[2, "perm_status__provider_missing"] == 1


@pytest.mark.parametrize(("change", "status", "alias_count", "conflict_count"), [
    ({"canonical_permission": RAW}, "UNRESOLVED_ALIAS", 1, 0),
    ({"canonical_permission": pd.NA,
      "current_evidence_state": "UNRESOLVED",
      "current_identifier_kind": "UNKNOWN"}, "UNRESOLVED_IDENTITY", 0, 0),
    ({"unresolved_conflict_count": 1}, "CONFLICT", 0, 1),
])
def test_receipt_bound_identity_holds_remain_distinct(
    tmp_path, change, status, alias_count, conflict_count,
) -> None:
    plan_path, receipt_dir, digest, _ = _files(tmp_path)
    receipts = load_recovery_receipt_evidence(
        plan_path, receipt_dir, expected_plan_digest=digest
    )
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    joined = reconcile_provider_observations(
        samples, pd.DataFrame([_observation(**change)]), receipts
    )
    assert joined.loc[0, "identity_status"] == status
    if status == "UNRESOLVED_IDENTITY":
        assert joined.loc[0, "canonical_token"] == ""
    result = build_source_aware_permission_features(
        samples, joined, training_sample_ids=[1]
    )
    assert result.loc[0, "perm_status__unresolved_count"] == 1
    assert result.loc[0, "perm_status__alias_review_count"] == alias_count
    assert result.loc[0, "perm_status__governance_conflict_count"] == conflict_count
    assert not any(name.startswith("perm_provider__") for name in result.columns)


@pytest.mark.parametrize("change", [
    {"observation_source": "apk_manifest"},
    {"event_source_engine": "other"},
    {"event_analysis_date_utc": "2026-10-02T00:00:00Z"},
    {"recovery_plan_core": "d" * 64},
    {"recovery_batch_id": "wrong"},
])
def test_mismatched_source_event_or_plan_is_unresolved(tmp_path, change) -> None:
    plan_path, receipt_dir, digest, _ = _files(tmp_path)
    receipts = load_recovery_receipt_evidence(
        plan_path, receipt_dir, expected_plan_digest=digest
    )
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    joined = reconcile_provider_observations(
        samples, pd.DataFrame([_observation(**change)]), receipts
    )
    result = build_source_aware_permission_features(
        samples, joined, training_sample_ids=[1]
    )
    assert result.loc[0, "perm_status__unresolved_count"] == 1
    assert not any(name.startswith("perm_provider__") for name in result.columns)


def test_receipt_tamper_and_catalog_sha_mismatch_fail_closed(tmp_path) -> None:
    plan_path, receipt_dir, digest, receipt_path = _files(tmp_path)
    receipts = load_recovery_receipt_evidence(
        plan_path, receipt_dir, expected_plan_digest=digest
    )
    samples = pd.DataFrame({"sample_id": [1], "sha256": ["e" * 64]})
    joined = reconcile_provider_observations(
        samples, pd.DataFrame([_observation()]), receipts
    )
    assert joined.loc[0, "source_verified"] == False
    receipt = json.loads(receipt_path.read_text())
    receipt["result"]["sample_id"] = 9
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="digest differs"):
        load_recovery_receipt_evidence(
            plan_path, receipt_dir, expected_plan_digest=digest
        )


@pytest.mark.parametrize("field,value", [
    ("execution_scope", "DISPOSABLE_REHEARSAL"),
    ("production_effect", "none"),
    ("result.provider_requests", 1),
    ("result.primary_mutations", 1),
])
def test_self_consistent_wrong_scope_or_side_effect_receipt_rejected(
    tmp_path, field, value
) -> None:
    plan_path, receipt_dir, digest, receipt_path = _files(tmp_path)
    receipt = json.loads(receipt_path.read_text())
    target = receipt["result"] if field.startswith("result.") else receipt
    target[field.split(".")[-1]] = value
    receipt["receipt_digest"] = _digest({
        key: item for key, item in receipt.items() if key != "receipt_digest"
    })
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="binding differs"):
        load_recovery_receipt_evidence(
            plan_path, receipt_dir, expected_plan_digest=digest
        )


def test_receipt_filename_must_bind_exact_action(tmp_path) -> None:
    plan_path, receipt_dir, digest, receipt_path = _files(tmp_path)
    receipt_path.rename(receipt_dir / f"pi-production-sample-{'f' * 64}.json")
    with pytest.raises(ValueError, match="filename differs"):
        load_recovery_receipt_evidence(
            plan_path, receipt_dir, expected_plan_digest=digest
        )


def test_receipt_reader_rejects_symlink_fifo_and_missing_file(tmp_path) -> None:
    plan_path, receipt_dir, digest, receipt_path = _files(tmp_path)
    outside = tmp_path / "outside.json"
    receipt_path.rename(outside)
    receipt_path.symlink_to(outside)
    with pytest.raises(ValueError, match="unreadable"):
        load_recovery_receipt_evidence(
            plan_path, receipt_dir, expected_plan_digest=digest
        )
    receipt_path.unlink()
    os.mkfifo(receipt_path, mode=0o600)
    with pytest.raises(ValueError, match="private regular file"):
        load_recovery_receipt_evidence(
            plan_path, receipt_dir, expected_plan_digest=digest
        )
    receipt_path.unlink()
    with pytest.raises(ValueError, match="unreadable"):
        load_recovery_receipt_evidence(
            plan_path.with_name("missing.json"), receipt_dir,
            expected_plan_digest=digest,
        )


def test_resealed_source_binding_cannot_claim_manifest_provenance(tmp_path) -> None:
    plan_path, receipt_dir, digest, receipt_path = _files(tmp_path)
    receipt = json.loads(receipt_path.read_text())
    receipt["exact_manifest_digest"] = "a" * 64
    receipt["exact_selection_digest"] = "b" * 64
    receipt["action_source_binding"]["observation_origin"] = "manifest_verified"
    receipt["receipt_digest"] = _digest({
        key: item for key, item in receipt.items() if key != "receipt_digest"
    })
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="binding differs"):
        load_recovery_receipt_evidence(
            plan_path, receipt_dir, expected_plan_digest=digest,
            expected_manifest_digest="a" * 64,
            expected_selection_digest="b" * 64,
        )


def test_historical_event_join_row_does_not_add_false_unresolved(tmp_path) -> None:
    plan_path, receipt_dir, digest, _ = _files(tmp_path)
    receipts = load_recovery_receipt_evidence(
        plan_path, receipt_dir, expected_plan_digest=digest
    )
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    joined = reconcile_provider_observations(
        samples,
        pd.DataFrame([
            _observation(event_analysis_date_utc="2026-09-01T00:00:00Z"),
            _observation(),
        ]),
        receipts,
    )
    assert len(joined) == 1
    result = build_source_aware_permission_features(
        samples, joined, training_sample_ids=[1]
    )
    assert result.loc[0, _token_feature(PROJECTED, "provider")] == 1
    assert result.loc[0, "perm_status__unresolved_count"] == 0


def test_normalized_only_pi_event_match_is_not_provider_positive(tmp_path) -> None:
    plan_path, receipt_dir, digest, _ = _files(tmp_path)
    receipts = load_recovery_receipt_evidence(
        plan_path, receipt_dir, expected_plan_digest=digest
    )
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    # Legacy event and observation spellings often agree after case folding.
    # An exact recovery receipt for the lowercase token cannot verify the
    # differently cased PI observation merely through normalized identity.
    joined = reconcile_provider_observations(
        samples,
        pd.DataFrame([_observation(permission_string=RAW)]),
        receipts,
    )
    features = build_source_aware_permission_features(
        samples, joined, training_sample_ids=[1]
    )
    assert features.loc[0, "perm_status__unresolved_count"] == 1
    assert features.loc[0, "perm_status__provider_missing"] == 1
    assert not any(name.startswith("perm_provider__") for name in features.columns)


def test_exact_pilot_receipts_require_manifest_and_selection_binding(tmp_path) -> None:
    plan_path, receipt_dir, digest, receipt_path = _files(tmp_path)
    with pytest.raises(ValueError, match="binding differs"):
        load_recovery_receipt_evidence(
            plan_path, receipt_dir, expected_plan_digest=digest,
            expected_manifest_digest="a" * 64,
            expected_selection_digest="b" * 64,
        )
    receipt = json.loads(receipt_path.read_text())
    receipt["exact_manifest_digest"] = "a" * 64
    receipt["exact_selection_digest"] = "b" * 64
    receipt["receipt_digest"] = _digest({k: v for k, v in receipt.items() if k != "receipt_digest"})
    receipt_path.write_text(json.dumps(receipt))
    assert len(load_recovery_receipt_evidence(
        plan_path, receipt_dir, expected_plan_digest=digest,
        expected_manifest_digest="a" * 64,
        expected_selection_digest="b" * 64,
    )) == 1


def test_source_aware_pi_reader_selects_observation_origin_and_one_parameter(
    monkeypatch,
) -> None:
    captured = []
    monkeypatch.setattr(permission_features, "assert_legacy_observation_read_allowed",
                        lambda: None)
    monkeypatch.setattr(
        permission_features, "_permission_obs_key_expr",
        lambda: "LOWER(TRIM(ops.permission_string))",
    )
    monkeypatch.setattr(
        permission_features.db_engine, "execute_permission_query",
        lambda query, **kwargs: (captured.append((query, kwargs)), pd.DataFrame())[1],
    )
    permission_features._fetch_source_aware_permission_rows([1])
    query, kwargs = captured[0]
    assert "ops.source AS observation_source" in query
    assert "vte.permission_string_bin_sha256 = ops.permission_string_bin_sha256" in query
    assert "BINARY vte.permission_string = BINARY ops.permission_string" in query
    assert "BINARY pi.source_provenance_status = BINARY 'PRESENT'" in query
    assert "classification_recovery_plan_core_sha256" in query
    assert query.count("%s") == 1
    assert kwargs["params"] == (1,)


def test_public_receipt_loader_seals_frame_and_invalidates_changed_source(
    tmp_path, monkeypatch,
) -> None:
    plan_path, receipt_dir, digest, receipt_path = _files(tmp_path)
    samples = pd.DataFrame({"sample_id": [1], "sha256": [SHA]})
    monkeypatch.setattr(permission_features, "_fetch_source_aware_permission_rows",
                        lambda ids: pd.DataFrame([_observation()]))
    frame = permission_features.build_permission_feature_frame(
        samples, min_permission_support=1,
        feature_contract_version=CONTRACT_VERSION,
        training_sample_ids=[1], recovery_plan_path=plan_path,
        recovery_receipt_directory=receipt_dir,
        expected_recovery_plan_digest=digest,
    )
    assert frame.loc[0, _token_feature(PROJECTED, "provider")] == 1
    assert_verified_source_aware_frame(frame, accepted_aliases=None)
    receipt_path.write_text(receipt_path.read_text() + " ")
    with pytest.raises(ValueError, match="file changed"):
        assert_verified_source_aware_frame(frame, accepted_aliases=None)
