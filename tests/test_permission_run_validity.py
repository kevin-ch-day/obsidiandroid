"""QA-05: failed PI input must not silently become accepted research."""

import pandas as pd
import pytest

from obsidiandroid.pipeline.permission_run_validity import (
    assert_training_permission_validity,
    evaluate_permission_run_validity,
    permission_frame_status,
)


def test_required_unavailable_stops_before_training(monkeypatch):
    called = []
    with pytest.raises(RuntimeError, match="training blocked"):
        evaluate_permission_run_validity(
            {"enable_permission_features": True, "permission_input_policy": "required"},
            available=False, degraded=True, evidence_status="UNAVAILABLE")
        called.append("fit")
    assert not called


def test_development_continuation_is_durable_and_not_accepted():
    decision = evaluate_permission_run_validity(
        {"enable_permission_features": True, "permission_input_policy":
         "development_compatibility"}, available=False, degraded=True)
    assert decision == {
        "policy": "development_compatibility", "evidence_status": "UNAVAILABLE",
        "research_validity": "DEVELOPMENT_ONLY_NOT_ACCEPTED_RESEARCH",
    }
    assert_training_permission_validity(decision)


def test_intentional_disablement_differs_from_failed_fetch():
    decision = evaluate_permission_run_validity(
        {"enable_permission_features": False, "permission_input_policy":
         "intentionally_disabled"}, available=False, degraded=False)
    assert decision["research_validity"] == "PI_DISABLED_DECLARED"
    with pytest.raises(ValueError, match="conflicts"):
        evaluate_permission_run_validity(
            {"enable_permission_features": True, "permission_input_policy":
             "intentionally_disabled"}, available=False, degraded=False)


def test_statuses_preserve_verified_empty_and_conflict():
    frame = pd.DataFrame({
        "sample_id": [1], "perm_status__has_manifest_parse": [1],
        "perm_status__unresolved_count": [0],
        "perm_status__governance_conflict_count": [0],
    })
    assert permission_frame_status(frame, degraded=False) == "VERIFIED_EMPTY"
    frame["perm_status__governance_conflict_count"] = 1
    assert permission_frame_status(frame, degraded=False) == "CONTRADICTORY"
    assert permission_frame_status(frame, degraded=True) == "UNAVAILABLE"
    assert permission_frame_status(pd.DataFrame({"sample_id": [1]}), degraded=False) == "NO_OBSERVATIONS"


def test_training_boundary_rejects_invalid_or_missing_decision():
    for decision in (None, {"policy": "required", "evidence_status": "UNAVAILABLE",
                            "research_validity": "ACCEPTED_PI_INPUT"}):
        with pytest.raises(RuntimeError):
            assert_training_permission_validity(decision)


def test_required_v2_accepts_only_explicit_unresolved_occurrence_contract():
    frame = pd.DataFrame({"sample_id": [1],
                          "perm_status__provider_reported_unresolved_count": [1]})
    frame.attrs["permission_feature_contract_version"] = (
        "obsidiandroid-permission-exact-v2-unresolved-v1")
    status = permission_frame_status(frame, degraded=False)
    assert status == "PROVIDER_REPORTED_UNRESOLVED"
    decision = evaluate_permission_run_validity(
        {"enable_permission_features": True, "permission_input_policy": "required",
         "permission_feature_contract_version": frame.attrs[
             "permission_feature_contract_version"]},
        available=True, degraded=False, evidence_status=status)
    assert decision["research_validity"] == "ACCEPTED_UNRESOLVED_OCCURRENCE_CONTRACT"
    with pytest.raises(RuntimeError, match="training blocked"):
        evaluate_permission_run_validity(
            {"enable_permission_features": True,
             "permission_input_policy": "required"},
            available=True, degraded=False, evidence_status=status)


@pytest.mark.parametrize("enabled", ["false", 0, 1, None])
def test_feature_enablement_is_not_coerced_into_a_research_decision(enabled):
    with pytest.raises(TypeError, match="boolean"):
        evaluate_permission_run_validity(
            {"enable_permission_features": enabled},
            available=False, degraded=False)


@pytest.mark.parametrize("decision", [
    {"policy": "required", "evidence_status": "PRESENT",
     "research_validity": "PI_DISABLED_DECLARED"},
    {"policy": "intentionally_disabled", "evidence_status": "PRESENT",
     "research_validity": "PI_DISABLED_DECLARED"},
    {"policy": "development_compatibility", "evidence_status": "UNAVAILABLE",
     "research_validity": "ACCEPTED_PI_INPUT"},
    {"policy": "required", "evidence_status": "PROVIDER_REPORTED_UNRESOLVED",
     "research_validity": "ACCEPTED_PI_INPUT"},
])
def test_training_boundary_rejects_inconsistent_decision_triplets(decision):
    with pytest.raises(RuntimeError, match="before training"):
        assert_training_permission_validity(decision)
