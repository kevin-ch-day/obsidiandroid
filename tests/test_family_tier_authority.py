from __future__ import annotations

from obsidiandroid.governance import family_tier_authority


def test_family_tier_authority_artifact_loads_expected_major_family_contract() -> None:
    artifact = family_tier_authority.load_family_tier_authority_artifact()
    payload = family_tier_authority.major_family_authority_payload()

    assert artifact["authority_id"] == "android_family_tier_authority"
    assert artifact["version"] == "20260601-v1"
    assert artifact["seed_source"] == "archived_paper_lock_20260504T044304Z__8c64e6"
    assert len(artifact["major_families"]) == 39
    assert "spynote" in artifact["major_families"]
    assert payload["family_count"] == 39
    assert payload["artifact_path"] == "config/taxonomy/android_family_tier_authority.yaml"
    assert payload["handle"] == "android_family_tier_authority.major_families"
    assert payload["hash"]


def test_generic_coarse_token_policy_payload_includes_type_targets_and_handles() -> None:
    payload = family_tier_authority.generic_coarse_token_policy_payload()

    assert payload["artifact_path"] == "config/taxonomy/android_family_tier_authority.yaml"
    assert payload["handle"] == "android_family_tier_authority.generic_coarse_tokens"
    assert "banker" in payload["tokens"]
    assert "rat" in payload["type_targets"]
    assert "backdoor" in payload["type_targets"]
    assert payload["hash"]
