"""Offline Mobile ATT&CK v20.1 gate and identity-matching contract for every mapping rule."""
import json

import pandas as pd
import pytest

from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.governance.mobile_attack_reference import ARTIFACT, RELEASE, load_mobile_attack_reference
from obsidiandroid.governance.mobile_attack_permission_mapping import load_mobile_attack_permission_mapping
from obsidiandroid.governance.permission_attack_evidence import (
    PermissionIdentity, PermissionObservation, assess_permission_observation, project_identity_dispositions,
)
from obsidiandroid.pipeline.permission_trends.attack_mapping import build_attack_mobile_hypotheses

MAPPING = load_mobile_attack_permission_mapping()
RULES = MAPPING['rules']
REFERENCE = load_mobile_attack_reference()
MULTI_TACTIC = {'T1453', 'T1430', 'T1616', 'T1516', 'T1517', 'T1603', 'T1541'}


def _display_aliases() -> dict[str, str]:
    """Documented alias: ``<parent technique name>: <sub-technique name>`` (ATT&CK site display form)."""
    bundle = json.loads((repo_root() / ARTIFACT).read_bytes())
    by_id = {o['id']: o for o in bundle['objects']}
    aliases = {}
    for rel in bundle['objects']:
        if rel['type'] == 'relationship' and rel.get('relationship_type') == 'subtechnique-of':
            sub, parent = by_id.get(rel['source_ref']), by_id.get(rel['target_ref'])
            if sub and parent:
                aliases[sub['id']] = f"{parent['name']}: {sub['name']}"
    return aliases


ALIASES = _display_aliases()


def test_mapping_is_pinned_to_the_v20_1_reference():
    assert RELEASE == 'v20.1'
    assert MAPPING['attack_source']['release'] == RELEASE
    assert len(RULES) == 21


@pytest.mark.parametrize('rule', RULES, ids=[r['rule_id'] for r in RULES])
def test_every_rule_names_an_active_android_v20_1_technique(rule):
    technique = REFERENCE.technique(rule['attack_id'])  # raises for missing, revoked, deprecated or non-Android
    assert technique.revoked is False and technique.deprecated is False
    assert 'Android' in technique.platforms
    assert rule['stix_id'] == technique.stix_id
    assert rule['attack_name'] in {technique.name, ALIASES.get(technique.stix_id)}
    for tactic in rule['tactics']:
        assert tactic in technique.tactics, f'{tactic} is not a kill-chain phase of {rule["attack_id"]}'
    assert sorted(rule['tactics']) == list(technique.tactics), 'tactic list must be the complete official set'


def test_rules_carry_a_tactics_list_not_a_single_tactic():
    for rule in RULES:
        assert 'tactic' not in rule
        assert isinstance(rule['tactics'], list) and rule['tactics']
    assert {r['attack_id'] for r in RULES if len(r['tactics']) > 1} == MULTI_TACTIC


def test_loader_preserves_canonical_case_on_the_authoritative_path():
    tokens = [t for r in RULES for t in r['required_any']] + [a['permission'] for a in MAPPING['identity_assessments']]
    assert tokens
    for token in tokens:
        assert token == token.strip()
        assert token != token.lower(), f'authoritative identities keep canonical case: {token}'


def _identity(token):
    return PermissionIdentity(token, 'AOSP_PUBLIC', 'RETAINED_SOURCE_EXACT', 'synthetic', 'a' * 64)


def _observation(token):
    return PermissionObservation(1, 'b' * 64, token, 'REQUESTED', 'STATIC_MANIFEST', 'synthetic', api_level=37)


def test_authoritative_matching_is_exact_identity_not_casefold():
    canonical = 'android.permission.READ_SMS'
    exact = assess_permission_observation(_observation(canonical), _identity(canonical), MAPPING)
    assert {r['attack_id'] for r in exact} == {'T1636.004'}
    lowered = assess_permission_observation(_observation(canonical.lower()), _identity(canonical.lower()), MAPPING)
    assert [r['attack_id'] for r in lowered] == [None]
    assert lowered[0]['disposition'] in {'UNRESOLVED', 'PENDING_REVIEW'}
    catalog = {'fixture_set': 'synthetic', 'platform_release': {'full_api': '37'},
               'permission_identities': [{'canonical_name': canonical.lower(), 'authority_class': 'AOSP_PUBLIC', 'source_snapshot_ids': ['s']}],
               'declaration_revisions': [{'canonical_name': canonical.lower(), 'protection': {'raw_expression': 'dangerous'}}]}
    projected = project_identity_dispositions(catalog, 'c' * 64, MAPPING)[0]
    assert projected['disposition'] == 'PENDING_REVIEW' and projected['attack_ids'] == []


def test_casefold_matching_is_only_an_explicit_non_authoritative_hint():
    lower = pd.DataFrame([{'group': 'banker', 'permission': 'android.permission.read_sms', 'sample_count': 10, 'prevalence': 0.5}])
    hint = build_attack_mobile_hypotheses(prevalence_df=lower, run_id='synthetic', group_field='group', group_kind='family')
    assert not hint.empty
    assert hint.identity_matching.eq('LEGACY_CASEFOLD_HINT_NOT_IDENTITY_AUTHORITY').all()
    assert not hint.eligible_for_family_model_features.any() and not hint.technique_observed.any()
    strict = build_attack_mobile_hypotheses(prevalence_df=lower, run_id='synthetic', group_field='group', group_kind='family', casefold_hint=False)
    assert strict.empty, 'exact mode must not match a lowercased token'
    canonical = lower.assign(permission='android.permission.READ_SMS')
    exact = build_attack_mobile_hypotheses(prevalence_df=canonical, run_id='synthetic', group_field='group', group_kind='family', casefold_hint=False)
    assert not exact.empty and exact.identity_matching.eq('EXACT_TOKEN_HINT_NOT_IDENTITY_AUTHORITY').all()
