"""Audit the opt-in provider tier on a pinned release; no database/model access."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import replace
from datetime import datetime, UTC
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import yaml

from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.governance.mobile_attack_permission_mapping import validate_mapping, _stable_hash
from obsidiandroid.governance.permission_attack_evidence import (
    PermissionIdentity, PermissionObservation, assess_permission_observation,
    load_retained_pi_catalog, project_identity_dispositions,
)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def mapping(path):
    result = validate_mapping(yaml.safe_load(path.read_text()))
    result['hash'] = _stable_hash(result)
    return result


def run(parquet, parquet_sha256, fixture, fixture_sha256, output):
    import pyarrow.parquet as pq

    if digest(parquet) != parquet_sha256:
        raise ValueError('Frozen Parquet SHA-256 mismatch')
    catalog, fixture_digest = load_retained_pi_catalog(fixture, fixture_sha256)
    root = repo_root()
    old = mapping(root / 'config/taxonomy/mobile_attack_permission_mapping.yaml')
    new = mapping(root / 'config/taxonomy/mobile_attack_permission_mapping.v4-candidate.yaml')
    identities = {r['canonical_permission']: PermissionIdentity(
        r['canonical_permission'], r['authority_class'], r['identity_status'],
        r['source_scope'], r['source_digest'])
        for r in project_identity_dispositions(catalog, fixture_digest, old)}
    rules = {r['rule_id']: r for r in old['rules']}
    token_rules = defaultdict(list)
    for rule in rules.values():
        for token in rule['required_any']: token_rules[token].append(rule['rule_id'])
    columns = ['id_sample_id', 'id_sha256', 'group_detected_v2', 'label_v2_type_v2',
               'time_first_submission_year', 'pay_permission_names_raw', 'pay_event_id',
               'pay_payload_hash', 'pay_androguard_version', 'time_analysis_payload_epoch']
    rows = [r for r in pq.read_table(parquet, columns=columns).to_pylist() if r['group_detected_v2']]
    if len(rows) != 27495 or len({r['id_sha256'] for r in rows}) != 27495:
        raise ValueError('DETECTED_V2 must contain 27,495 unique frozen identities')
    output.mkdir(parents=True, exist_ok=False)
    counters = defaultdict(Counter)
    totals = Counter()
    token_states = Counter()
    changed_rules = {r['rule_id'] for r in new['rules'] if 'PROVIDER_REPORTED' in r['allowed_roles']}
    full = gzip.open(output / 'sample_rule_results.jsonl.gz', 'wt')
    try:
        for sample in rows:
            raw = sample['pay_permission_names_raw']
            names = json.loads(raw) if raw is not None else None
            invalid = [t for t in (names or []) if not isinstance(t, str) or not t or t != t.strip() or any(ord(c) < 32 or ord(c) == 127 for c in t)]
            totals['invalid_token_profiles'] += bool(invalid)
            totals['provider_profiles'] += names is not None
            states = defaultdict(set)
            baseline_roles = set()
            for token in names or []:
                if token in invalid:
                    token_states['INVALID_TOKEN'] += 1
                    continue
                epoch = sample['time_analysis_payload_epoch']
                obs = PermissionObservation(
                    sample['id_sample_id'], sample['id_sha256'], token, 'UNKNOWN',
                    'PROVIDER_REPORT', sample['pay_androguard_version'] or 'UNKNOWN_VERSION',
                    source_event_id=str(sample['pay_event_id']),
                    source_payload_digest=sample['pay_payload_hash'],
                    observed_at=datetime.fromtimestamp(epoch, UTC).isoformat() if epoch is not None else None,
                    observation_time_meaning='PROVIDER_LAST_ANALYSIS' if epoch is not None else 'UNKNOWN',
                    provenance_refs=('dataset-sha256:' + parquet_sha256, 'field:$.data.attributes.androguard.permission_details'),
                    source_validation='SOURCE_BOUND', api_level=None,
                    source_asserted_role='PROVIDER_REPORTED_REQUIRED_PERMISSION',
                    source_field_path='$.data.attributes.androguard.permission_details',
                    role_interpretation_rule='pi-retained-provider-required-v1')
                identity = identities.get(token)
                before = assess_permission_observation(obs, identity, old)
                after = assess_permission_observation(replace(obs, role='PROVIDER_REPORTED'), identity, new)
                token_states[before[0]['identity_status']] += 1
                before_by = {r.get('rule_id'): r for r in before}
                after_by = {r.get('rule_id'): r for r in after}
                for rid in token_rules.get(token, []):
                    previous = before_by.get(rid)
                    result = after_by.get(rid)
                    if previous and not previous['permission_role_compatible']:
                        baseline_roles.add(rid)
                    if result is None:
                        states[rid].add('UNRESOLVED_IDENTITY' if after[0]['disposition'] == 'UNRESOLVED' else after[0]['disposition'])
                        continue
                    assert result['technique_observed'] is False and not result['source_role_complete']
                    assert result['api_applicability'] == 'UNKNOWN'
                    if result['behavioral_interpretation'] == 'PROVIDER_REPORTED_CAPABILITY_HYPOTHESIS':
                        assert rid in changed_rules and result['evidence_tier'] == 'PROVIDER_REPORTED_LOWER'
                        state = 'ASSESSED'
                    else:
                        state = 'ROLE_NOT_OBSERVABLE'
                    states[rid].add(state)
                    full.write(json.dumps({'sample_id': sample['id_sample_id'], 'token': token,
                                           'status': state, 'assessment': result}, sort_keys=True) + '\n')
            for rid in rules:
                options = states[rid]
                if names is None: status = 'NO_PERMISSION_EVIDENCE'
                elif 'ASSESSED' in options: status = 'ASSESSED'
                elif 'ROLE_NOT_OBSERVABLE' in options: status = 'ROLE_NOT_OBSERVABLE'
                elif 'UNRESOLVED_IDENTITY' in options: status = 'UNRESOLVED_IDENTITY'
                elif options: status = sorted(options)[0]
                else: status = 'NO_MATCHING_VALID_TOKEN'
                for dimension, value in [('all', 'DETECTED_V2'), ('type', sample['label_v2_type_v2'] or 'MISSING_TYPE'),
                                         ('year', str(sample['time_first_submission_year']) if sample['time_first_submission_year'] is not None else 'UNKNOWN_YEAR')]:
                    count = counters[(rid, dimension, value)]
                    count['denominator_n'] += 1
                    count[status] += 1
                    count['baseline_ROLE_NOT_OBSERVABLE'] += rid in baseline_roles
                    count['ASSESSED_with_invalid_profile_tokens'] += status == 'ASSESSED' and bool(invalid)
    finally:
        full.close()
    statuses = sorted({s for c in counters.values() for s in c if s not in {'denominator_n', 'baseline_ROLE_NOT_OBSERVABLE', 'ASSESSED_with_invalid_profile_tokens'}})
    for dimension, filename in [('all', 'per_rule.csv'), ('type', 'per_rule_type.csv'), ('year', 'per_rule_year.csv')]:
        fields = ['rule_id', 'attack_id', 'relationship_category', 'dimension', 'stratum', 'dataset_sha256',
                  'denominator_id', 'denominator_n', 'baseline_ROLE_NOT_OBSERVABLE'] + statuses + ['ASSESSED_with_invalid_profile_tokens']
        with (output / filename).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
            for (rid, dim, value), count in sorted(counters.items()):
                if dim != dimension: continue
                assert sum(count[s] for s in statuses) == count['denominator_n']
                if rid not in changed_rules: assert count['ASSESSED'] == 0
                writer.writerow({'rule_id': rid, 'attack_id': rules[rid]['attack_id'],
                                 'relationship_category': rules[rid]['relationship_category'],
                                 'dimension': dim, 'stratum': value, 'dataset_sha256': parquet_sha256,
                                 'denominator_id': 'V2_DETECTED_MALWARE_27495' if dim == 'all' else 'V2_DETECTED_MALWARE_27495/' + dim + '/' + value,
                                 **{k: count[k] for k in ['denominator_n', 'baseline_ROLE_NOT_OBSERVABLE'] + statuses + ['ASSESSED_with_invalid_profile_tokens']}})
    summary = {'observed_utc': datetime.now(UTC).isoformat(), 'base_commit': 'e6fd07373723b813bc121d6b9f28ef7bb6f99e77',
               'code_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
               'dataset_sha256': parquet_sha256, 'fixture_sha256': fixture_digest,
               'mapping_v3_hash': old['hash'], 'mapping_candidate_hash': new['hash'],
               'detected_n': len(rows), 'candidate_capability_rules': len(changed_rules),
               'unchanged_context_rules': len(rules) - len(changed_rules), 'totals': dict(totals),
               'token_identity_states': dict(token_states), 'training_authorized': False,
               'production_adoption_authorized': False, 'semantic_role_observable': False,
               'status_definition': 'ASSESSED means only lower-tier provider-reported capability hypothesis, never observed behavior; API applicability remains UNKNOWN.',
               'invalid_policy': 'Invalid tokens abstain; other valid tokens in the same profile remain evaluable. ASSESSED_with_invalid_profile_tokens permits whole-profile-exclusion sensitivity.',
               'sample_rule_status_precedence': ['NO_PERMISSION_EVIDENCE', 'ASSESSED', 'ROLE_NOT_OBSERVABLE', 'UNRESOLVED_IDENTITY', 'review disposition', 'NO_MATCHING_VALID_TOKEN']}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['parquet', 'fixture', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ['parquet-sha256', 'fixture-sha256']:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.parquet, args.parquet_sha256, args.fixture, args.fixture_sha256, args.output), indent=2))
