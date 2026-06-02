from __future__ import annotations

from obsidiandroid.diagnostics.research_validity.permission_signal_seed import SIGNAL_CATALOG_ROWS
from obsidiandroid.diagnostics.research_validity.permission_signal_seed import SIGNAL_MAPPING_ROWS


def _catalog_row(signal_key: str) -> dict[str, object]:
    return next(row for row in SIGNAL_CATALOG_ROWS if row["signal_key"] == signal_key)


def _mapping_row(signal_key: str, perm_name: str) -> dict[str, object]:
    return next(
        row
        for row in SIGNAL_MAPPING_ROWS
        if row["signal_key"] == signal_key and row["perm_name"] == perm_name
    )


def test_scaffolding_lanes_are_model_yes_behavioral_no() -> None:
    row = _catalog_row("app_defined_scaffolding")
    assert row["include_in_model_features"] is True
    assert row["include_in_behavioral_claims"] is False
    assert row["mitre_candidate_only"] is True

    mapping = _mapping_row("app_defined_scaffolding", "app_defined_dynamic_receiver_guard")
    assert mapping["mapping_basis"] == "remediation_lane"
    assert mapping["include_in_model_features"] is True
    assert mapping["include_in_behavioral_claims"] is False


def test_aosp_dangerous_permissions_can_be_behavioral_yes() -> None:
    row = _catalog_row("sms")
    assert row["include_in_behavioral_claims"] is True
    assert row["mitre_candidate_only"] is True

    mapping = _mapping_row("sms", "android.permission.read_sms")
    assert mapping["mapping_basis"] == "exact_permission"
    assert mapping["include_in_behavioral_claims"] is True
    assert mapping["candidate_behavior_area"] == "messaging_access"
    assert mapping["mitre_candidate_tactic"] == "collection"


def test_needs_source_validation_stays_behavioral_no() -> None:
    row = _catalog_row("aosp_hidden_privileged")
    assert row["include_in_model_features"] is True
    assert row["include_in_behavioral_claims"] is False
    assert row["mitre_candidate_only"] is True

    mapping = _mapping_row("aosp_hidden_privileged", "needs_source_validation")
    assert mapping["mapping_basis"] == "remediation_lane"
    assert mapping["include_in_model_features"] is False
    assert mapping["include_in_behavioral_claims"] is False


def test_mitre_fields_remain_candidate_only() -> None:
    assert all(bool(row["mitre_candidate_only"]) for row in SIGNAL_CATALOG_ROWS)
    assert all("technique" not in str(row.get("candidate_behavior_area", "")).lower() for row in SIGNAL_MAPPING_ROWS)
