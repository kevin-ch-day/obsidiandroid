"""Candidate provider tier retains source, role, API and behavior uncertainty."""
import copy
from dataclasses import replace

import pytest
import yaml

from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.governance.mobile_attack_permission_mapping import validate_mapping, mobile_attack_permission_mapping_payload
from obsidiandroid.governance.permission_attack_evidence import PermissionIdentity, PermissionObservation, assess_permission_observation


def candidate():
    return validate_mapping(yaml.safe_load((repo_root() / 'config/taxonomy/mobile_attack_permission_mapping.v4-candidate.yaml').read_text()))


def provider(token='android.permission.READ_SMS'):
    return PermissionObservation(1, 'a' * 64, token, 'PROVIDER_REPORTED', 'PROVIDER_REPORT', 'fixture-androguard',
        source_event_id='fixture-event', source_payload_digest='b' * 64,
        provenance_refs=('fixture-event',), source_validation='SOURCE_BOUND',
        source_asserted_role='PROVIDER_REPORTED_REQUIRED_PERMISSION',
        source_field_path='$.data.attributes.androguard.permission_details',
        role_interpretation_rule='pi-retained-provider-required-v1')


def identity(token):
    return PermissionIdentity(token, 'AOSP_PUBLIC', 'RETAINED_SOURCE_EXACT', 'fixture', 'c' * 64)


def test_lower_tier_is_a_hypothesis_with_unobservable_role_and_api():
    observation = provider()
    row = assess_permission_observation(observation, identity(observation.raw_token), candidate())[0]
    assert row['evidence_tier'] == 'PROVIDER_REPORTED_LOWER'
    assert row['behavioral_interpretation'] == 'PROVIDER_REPORTED_CAPABILITY_HYPOTHESIS'
    assert row['disposition'] == 'CAPABILITY_RELATED'
    assert row['api_applicability'] == 'UNKNOWN'
    assert not row['source_role_complete'] and not row['permission_role_observable']
    assert not row['technique_observed'] and row['missing_evidence']


def test_v3_does_not_admit_the_candidate_provider_tier():
    observation = provider()
    row = assess_permission_observation(observation, identity(observation.raw_token), mobile_attack_permission_mapping_payload())[0]
    assert row['behavioral_interpretation'] == 'INSUFFICIENT_EVIDENCE'
    assert not row['permission_role_compatible']


@pytest.mark.parametrize('change', [
    {'source_asserted_role': None, 'source_field_path': None, 'role_interpretation_rule': None},
    {'source_validation': 'UNVERIFIED'}, {'source_event_id': None},
    {'source_payload_digest': None}, {'provenance_refs': ()},
    {'role': 'REQUESTED'}, {'role': 'RUNTIME_GRANT'}, {'source_kind': 'STATIC_MANIFEST'},
])
def test_provider_role_cannot_bypass_source_or_manifest_role_boundaries(change):
    with pytest.raises(ValueError):
        replace(provider(), **change).validate()


def test_lower_tier_does_not_bypass_identity_or_api_gates():
    observation = provider()
    assert assess_permission_observation(observation, None, candidate())[0]['disposition'] == 'UNRESOLVED'
    rows = assess_permission_observation(replace(observation, api_level=1), identity(observation.raw_token), candidate())
    assert rows[0]['api_applicability'] == 'COMPATIBLE_MINIMUM_ONLY'
    payload = candidate()
    rule = next(r for r in payload['rules'] if 'PROVIDER_REPORTED' in r['allowed_roles']
                and any((v.get('api_min') or 0) > 1 for v in r['permission_constraints'].values()))
    token = next(t for t, v in rule['permission_constraints'].items() if (v.get('api_min') or 0) > 1)
    unsupported = assess_permission_observation(replace(provider(token), api_level=1), identity(token), payload)
    result = next(row for row in unsupported if row.get('rule_id') == rule['rule_id'])
    assert result['api_applicability'] == 'UNSUPPORTED_API'
    assert result['behavioral_interpretation'] == 'INSUFFICIENT_EVIDENCE'
    assert not result['technique_observed']


@pytest.mark.parametrize('mutation', ['context', 'tier', 'note'])
def test_candidate_gate_rejects_scope_or_evidence_promotion(mutation):
    payload = copy.deepcopy(candidate())
    rule = next(r for r in payload['rules'] if 'PROVIDER_REPORTED' in r['allowed_roles'])
    if mutation == 'context': rule['relationship_category'] = 'CONTEXT_REQUIRED'
    elif mutation == 'tier': rule['evidence_tier'] = 'VERIFIED'
    else: rule['provider_review_note'] = 'requested permission verified'
    with pytest.raises(ValueError): validate_mapping(payload)


def test_context_rules_still_abstain_for_provider_reports():
    payload = candidate()
    rule = next(r for r in payload['rules'] if r['relationship_category'] == 'CONTEXT_REQUIRED')
    observation = provider(rule['required_any'][0])
    result = next(r for r in assess_permission_observation(observation, identity(observation.raw_token), payload) if r.get('rule_id') == rule['rule_id'])
    assert not result['permission_role_compatible']
    assert result['behavioral_interpretation'] == 'INSUFFICIENT_EVIDENCE'
    assert result['evidence_tier'] is None
