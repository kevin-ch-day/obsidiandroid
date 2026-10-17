"""Deterministic v1 permission-evidence contract checks; no model training."""

from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path
from hashlib import sha256

from obsidiandroid.orchestration.source_aware_permission_features import (
    CONTRACT_VERSION, _token_feature, build_source_aware_permission_features,
    _build_from_verified_evidence, assert_verified_source_aware_frame,
)
from obsidiandroid.orchestration.permission_features import build_permission_feature_frame
from obsidiandroid.pipeline import stage_feature_enrichment


TOKEN = "android.permission.INTERNET"
SHA = {i: f"{i:064x}" for i in range(1, 5)}


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "sample_id": [1, 2, 3, 4],
        "sha256": [SHA[i] for i in range(1, 5)],
        "family_id": [10, 10, None, 20],
        "canonical_family": ["A", "A", None, "B"],
    })


def row(sample_id: int, origin: str, token: str = TOKEN, **changes) -> dict:
    value = {
        "sample_id": sample_id,
        "sha256": SHA[sample_id],
        "raw_token": token,
        "projected_token": token,
        "observation_origin": origin,
        "source_verified": True,
        "source_receipt_digest": "b" * 64,
        "event_verified": True,
        "identity_status": "ACCEPTED_EXACT",
        "canonical_token": token,
        "alias_release_digest": "",
    }
    value.update(changes)
    return value


def build(*rows: dict, train=(1, 2, 3, 4), accepted_aliases=None) -> pd.DataFrame:
    test_file = Path(__file__).resolve()
    return _build_from_verified_evidence(
        sample_frame(), pd.DataFrame(rows, columns=row(1, "provider").keys()),
        training_sample_ids=train,
        accepted_aliases=accepted_aliases,
        source_snapshot_digest="a" * 64,
        source_file_bindings=((str(test_file), sha256(test_file.read_bytes()).hexdigest()),),
    )


def test_manifest_verified_provider_only_and_both_are_separate() -> None:
    result = build(row(1, "manifest"), row(2, "provider"),
                   row(3, "manifest"), row(3, "provider"))
    indexed = result.set_index("sample_id")
    manifest = _token_feature(TOKEN, "manifest")
    provider = _token_feature(TOKEN, "provider")
    assert indexed.loc[1, [manifest, provider]].tolist() == [1, 0]
    assert indexed.loc[2, [manifest, provider]].tolist() == [0, 1]
    assert indexed.loc[3, [manifest, provider]].tolist() == [1, 1]
    assert indexed.loc[4, "perm_status__provider_missing"] == 1
    assert indexed.loc[4, "perm_status__manifest_missing"] == 1
    assert result.attrs["permission_feature_contract_version"] == CONTRACT_VERSION


def test_disagreement_and_missing_evidence_are_not_negative_observations() -> None:
    conflict = row(1, "provider", identity_status="CONFLICT")
    unverified = row(2, "manifest", source_verified=False)
    result = build(conflict, unverified).set_index("sample_id")
    assert not any(name.startswith("perm_provider__") for name in result.columns)
    assert result.loc[1, "perm_status__unresolved_count"] == 1
    assert result.loc[2, "perm_status__manifest_missing"] == 1
    assert result.loc[3, "perm_status__provider_missing"] == 1


def test_alias_requires_reviewed_release_and_exact_spelling_remains_distinct() -> None:
    lower = "com.google.android.c2dm.permission.receive"
    upper = "com.google.android.c2dm.permission.RECEIVE"
    result = build(
        row(1, "provider", lower, canonical_token=upper,
            identity_status="ACCEPTED_ALIAS", alias_release_digest="a" * 64),
        row(2, "provider", lower, canonical_token=upper,
            identity_status="ACCEPTED_ALIAS"),
        accepted_aliases={(lower, upper): "a" * 64},
    ).set_index("sample_id")
    assert result.loc[1, _token_feature(upper, "provider")] == 1
    assert result.loc[2, _token_feature(upper, "provider")] == 0
    assert result.loc[2, "perm_status__unresolved_count"] == 1
    without_release = build(row(
        1, "provider", lower, canonical_token=upper,
        identity_status="ACCEPTED_ALIAS", alias_release_digest="a" * 64,
    )).set_index("sample_id")
    assert without_release.loc[1, "perm_status__unresolved_count"] == 1


def test_exact_case_conflict_remains_unresolved() -> None:
    lower = "com.google.android.c2dm.permission.receive"
    upper = "com.google.android.c2dm.permission.RECEIVE"
    result = build(row(1, "provider", lower, canonical_token=upper)).set_index("sample_id")
    assert result.loc[1, "perm_status__unresolved_count"] == 1
    assert not any(name.startswith("perm_provider__") for name in result.columns)


def test_duplicate_observations_do_not_multiply_sample_rows() -> None:
    result = build(row(1, "provider"), row(1, "provider"), row(1, "manifest"))
    assert len(result) == 4
    assert result["sample_id"].is_unique
    assert result.set_index("sample_id").loc[1, _token_feature(TOKEN, "provider")] == 1


def test_status_counts_distinct_projected_facts_not_raw_spellings() -> None:
    alias_a = row(1, "provider", "android.permission.Foo",
                  projected_token=TOKEN, identity_status="UNRESOLVED_ALIAS")
    alias_b = row(1, "provider", "android.permission.FOO",
                  projected_token=TOKEN, identity_status="UNRESOLVED_ALIAS")
    conflict = row(1, "provider", "android.permission.Bar",
                   projected_token="android.permission.BAR", identity_status="CONFLICT")
    manifest = row(1, "manifest", "android.permission.Foo",
                   projected_token=TOKEN, identity_status="UNRESOLVED_ALIAS")
    indexed = build(alias_a, alias_b, conflict, manifest).set_index("sample_id")
    assert indexed.loc[1, "perm_status__unresolved_count"] == 3
    assert indexed.loc[1, "perm_status__alias_review_count"] == 2
    assert indexed.loc[1, "perm_status__governance_conflict_count"] == 1
    assert not any(column.startswith("perm_provider__") for column in indexed.columns)


def test_status_counts_preserve_case_distinct_identities_and_source() -> None:
    upper = "android.permission.RECEIVE"
    lower = "android.permission.receive"
    indexed = build(
        row(1, "provider", upper, identity_status="CASE_CONFLICT"),
        row(1, "provider", upper, identity_status="CASE_CONFLICT"),
        row(1, "provider", lower, identity_status="CASE_CONFLICT"),
        row(1, "manifest", upper, identity_status="CASE_CONFLICT"),
    ).set_index("sample_id")
    assert indexed.loc[1, "perm_status__unresolved_count"] == 3
    assert indexed.loc[1, "perm_status__governance_conflict_count"] == 3
    assert indexed.loc[1, "perm_status__alias_review_count"] == 0


def test_governed_alias_and_duplicate_evidence_have_one_positive_fact() -> None:
    raw = "android.permission.Read_Contacts"
    canonical = "android.permission.READ_CONTACTS"
    alias = row(1, "provider", raw, projected_token=raw,
                canonical_token=canonical, identity_status="ACCEPTED_ALIAS",
                alias_release_digest="c" * 64)
    indexed = build(alias, dict(alias),
                    accepted_aliases={(raw, canonical): "c" * 64}).set_index("sample_id")
    assert indexed.loc[1, _token_feature(canonical, "provider")] == 1
    assert indexed.loc[1, "perm_status__unresolved_count"] == 0
    assert indexed.loc[1, "perm_status__alias_review_count"] == 0


def test_conflicting_evidence_for_one_projected_fact_suppresses_positive() -> None:
    indexed = build(
        row(1, "provider", TOKEN),
        row(1, "provider", TOKEN, identity_status="CONFLICT"),
        row(2, "provider", TOKEN),
    ).set_index("sample_id")
    feature = _token_feature(TOKEN, "provider")
    assert indexed.loc[1, feature] == 0
    assert indexed.loc[1, "perm_status__unresolved_count"] == 1
    assert indexed.loc[1, "perm_status__governance_conflict_count"] == 1
    assert indexed.loc[2, feature] == 1


def test_conflicting_accepted_canonicals_for_one_projected_fact_abstain() -> None:
    projected = "com.example.permission.read"
    first = "com.example.permission.READ"
    second = "com.example.permission.Read"
    digest = "d" * 64
    indexed = build(
        row(1, "provider", projected, canonical_token=first,
            identity_status="ACCEPTED_ALIAS", alias_release_digest=digest),
        row(1, "provider", projected, canonical_token=second,
            identity_status="ACCEPTED_ALIAS", alias_release_digest=digest),
        row(2, "provider", projected, canonical_token=first,
            identity_status="ACCEPTED_ALIAS", alias_release_digest=digest),
        row(3, "provider", projected, canonical_token=second,
            identity_status="ACCEPTED_ALIAS", alias_release_digest=digest),
        accepted_aliases={(projected, first): digest, (projected, second): digest},
    ).set_index("sample_id")
    assert indexed.loc[1, _token_feature(first, "provider")] == 0
    assert indexed.loc[1, _token_feature(second, "provider")] == 0
    assert indexed.loc[1, "perm_status__governance_conflict_count"] == 1
    assert indexed.loc[1, "perm_status__unresolved_count"] == 1
    assert indexed.loc[2, _token_feature(first, "provider")] == 1
    assert indexed.loc[3, _token_feature(second, "provider")] == 1


def test_no_direct_family_leakage_and_train_only_vocabulary() -> None:
    holdout = "android.permission.SEND_SMS"
    result = build(row(1, "provider"), row(4, "provider", holdout), train=(1, 2, 3))
    assert _token_feature(TOKEN, "provider") in result.columns
    assert _token_feature(holdout, "provider") not in result.columns
    assert not any("family" in name.lower() or "banker" in name.lower() for name in result.columns)
    assert result.set_index("sample_id").loc[3, "perm_status__provider_missing"] == 1


def test_sha_join_mismatch_and_duplicate_sample_fail_closed() -> None:
    with pytest.raises(ValueError, match="SHA binding"):
        build(row(1, "provider", sha256=SHA[2]))
    samples = pd.concat([sample_frame(), sample_frame().iloc[[0]]])
    with pytest.raises(ValueError, match="duplicated"):
        _build_from_verified_evidence(
            samples, pd.DataFrame([row(1, "provider")]), training_sample_ids=[1],
            source_snapshot_digest="a" * 64,
            source_file_bindings=((str(Path(__file__).resolve()),
                                   sha256(Path(__file__).read_bytes()).hexdigest()),),
        )


def test_direct_claimed_evidence_cannot_create_a_positive_feature() -> None:
    with pytest.raises(ValueError, match="direct source-aware DataFrames are untrusted"):
        build_source_aware_permission_features(
            sample_frame(), pd.DataFrame([row(1, "provider")]), training_sample_ids=[1]
        )


def test_bound_feature_frame_rejects_content_and_policy_drift() -> None:
    frame = build(row(1, "provider"))
    assert_verified_source_aware_frame(frame, accepted_aliases=None)
    changed = frame.copy()
    changed.loc[changed["sample_id"] == 2, _token_feature(TOKEN, "provider")] = 1
    with pytest.raises(ValueError, match="content changed"):
        assert_verified_source_aware_frame(changed, accepted_aliases=None)
    with pytest.raises(ValueError, match="policy changed"):
        assert_verified_source_aware_frame(frame, accepted_aliases={(TOKEN, TOKEN): "a" * 64})


def test_cached_frame_cannot_bypass_rechecked_gate(monkeypatch) -> None:
    frame = build(row(1, "provider"))
    from config import app_config
    monkeypatch.setattr(app_config, "PERMISSION_MIN_SUPPORT", 1, raising=False)
    calls = []
    def blocked() -> None:
        calls.append(1)
        raise RuntimeError("PI V2 research gate blocks legacy permission features")
    monkeypatch.setattr(stage_feature_enrichment, "assert_legacy_observation_read_allowed", blocked)
    with pytest.raises(RuntimeError, match="research gate blocks"):
        stage_feature_enrichment.merge_sample_metadata_features(
            None, sample_frame(),
            {"enable_sample_metadata_features": False,
             "permission_feature_contract_version": CONTRACT_VERSION,
             "permission_training_sample_ids": [1, 2, 3, 4]},
            permission_features_df=frame,
        )
    assert calls == [1]


def test_fabricated_cached_frame_cannot_fuse(monkeypatch) -> None:
    frame = build(row(1, "provider"))
    from config import app_config
    monkeypatch.setattr(app_config, "PERMISSION_MIN_SUPPORT", 1, raising=False)
    forged = frame.copy()
    forged.attrs["permission_feature_seal"] = "a" * 64
    monkeypatch.setattr(stage_feature_enrichment, "assert_legacy_observation_read_allowed",
                        lambda: None)
    with pytest.raises(ValueError, match="seal is invalid"):
        stage_feature_enrichment.merge_sample_metadata_features(
            None, sample_frame(),
            {"enable_sample_metadata_features": False,
             "permission_feature_contract_version": CONTRACT_VERSION,
             "permission_training_sample_ids": [1, 2, 3, 4]},
            permission_features_df=forged,
        )


def test_status_only_cached_frame_cannot_hide_under_legacy_contract() -> None:
    frame = build(row(1, "provider", identity_status="CONFLICT"))
    assert not any(name.startswith("perm_provider__") for name in frame.columns)
    with pytest.raises(ValueError, match="legacy fusion contract"):
        stage_feature_enrichment.merge_sample_metadata_features(
            None, sample_frame(), {"enable_sample_metadata_features": False,
                                   "permission_training_sample_ids": [1, 2, 3, 4]},
            permission_features_df=frame,
        )


def test_legacy_contract_is_not_silently_reinterpreted() -> None:
    with pytest.raises(ValueError, match="training membership"):
        build_permission_feature_frame(
            sample_frame(), feature_contract_version=CONTRACT_VERSION
        )
    with pytest.raises(ValueError, match="unknown permission feature contract"):
        build_permission_feature_frame(sample_frame(), feature_contract_version="v2")
