"""Evidence semantics through the offline reader, without DB or model imports."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

from obsidiandroid.governance import permission_consumer_conformance as consumer

import pytest

from obsidiandroid.governance.permission_consumer_conformance import (
    FORMAT, PURPOSE, OfflineBinding, canonical_bytes, digest, validate_offline_packet,
)

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
SHA = 'a' * 64
TOKEN = 'android.permission.CAMERA'


def fixture():
    blobs = {}

    def add(value):
        raw = canonical_bytes(value)
        key = digest(raw)
        blobs[key] = raw
        return key

    payload = add({'data': {'id': SHA, 'attributes': {'androguard': {
        'permission_details': {TOKEN: {}}}}}})
    interpretation = {'category': 'AOSP', 'canonical': TOKEN,
                      'identity_recognition': 'EXACT_ACCEPTED_CANONICAL',
                      'evidence_level': 'CATALOG_ACCEPTED',
                      'resolution_status': 'RESOLVED_CURRENT_IDENTITY',
                      'authority_scope': 'AOSP_PLATFORM', 'protection_base': 'dangerous',
                      'definition_source_present': True,
                      'capabilities': ['camera'], 'capability_status': 'CANDIDATE_NOT_APPROVED'}
    catalog_csv = ('canonical_permission,identity_status,catalog_release_id,catalog_digest,source_provenance_status\n'
                   + TOKEN + ',ACCEPTED,synthetic-release,' + 'b' * 64 + ',PRESENT\n').encode()
    blobs[digest(catalog_csv)] = catalog_csv
    versions = {'classifier_policy': 'permission-current-interpretation-adapter-v4',
                'profile_version': 'permission-operational-dimensions-v2',
                'classifier_source_sha256': add({'synthetic_classifier_fixture': 1}),
                'capability_mapping_sha256': add({'mapping_version': 'synthetic-v1', TOKEN: ['camera']}),
                'dictionary_release': 'synthetic-release', 'dictionary_catalog_digest': 'b' * 64,
                'dictionary_sha256': add({'release': 'synthetic-release', 'catalog_digest': 'b' * 64,
                                          'accepted_tokens': [TOKEN], 'source_bytes_sha256': digest(catalog_csv)}),
                'interpretations_sha256': add({TOKEN: interpretation}),
                'source_index_sha256': add({'1': {'sample_id': 1, 'sha256': SHA,
                                                 'event_id': 7, 'payload_sha256': payload}})}
    history = {'classification': 'UNKNOWN', 'rule': 'historical-default', 'source': 'retained_fixture',
               'observed_utc': '2026-01-01T00:00:00Z', 'run_id': None, 'classifier_policy': None,
               'authority_snapshot_sha256': None, 'recovery_plan_sha256': None,
               'original_event_id': None, 'original_payload_sha256': None,
               'canonical_snapshot': None, 'protection_snapshot': None}
    row = {'obs_id': 1, 'sample_id': 1, 'sha256': SHA, 'token_hex': TOKEN.encode().hex(),
           'history': history, 'interpretation': interpretation,
           'source': {'sample_id': 1, 'sha256': SHA, 'event_id': 7, 'payload_sha256': payload,
                      'raw_candidates': [TOKEN], 'match_state': 'RAW_EXACT',
                      'historical_relationship': 'LATEST_REPORT_CORRESPONDENCE_ONLY'}}
    packet = {'format': FORMAT, 'purpose': PURPOSE, 'snapshot_id': 'synthetic-test',
              'versions': versions, 'samples': [{'sample_id': 1, 'sha256': SHA, 'family': 'fixture',
                                               'observation_count': 1}], 'observations': [row]}
    return packet, blobs


def bind(packet):
    histories = [{k: row[k] for k in ('obs_id', 'sample_id', 'sha256', 'token_hex', 'history')}
                 for row in packet['observations']]
    return OfflineBinding(digest(canonical_bytes(packet)), digest(canonical_bytes(packet['samples'])),
                          digest(canonical_bytes(histories)), digest(canonical_bytes(packet['versions'])),
                          packet['snapshot_id'], '2026-10-17T00:00:00Z', '2026-10-19T00:00:00Z',
                          digest(Path(consumer.__file__).read_bytes()))


def run(packet, blobs, binding=None, operation='DESCRIBE_FAMILY'):
    def read(key):
        if key not in blobs:
            raise FileNotFoundError(key)
        return blobs[key]
    return validate_offline_packet(canonical_bytes(packet), binding or bind(packet), read,
                                   operation=operation, now_utc=NOW)


def rebind_interpretation(packet, blobs):
    row = packet['observations'][0]
    data = canonical_bytes({bytes.fromhex(row['token_hex']).decode(): row['interpretation']})
    blobs[digest(data)] = data
    packet['versions']['interpretations_sha256'] = digest(data)


def test_positive_exact_preserves_historical_label_and_scopes():
    packet, blobs = fixture()
    before = deepcopy(packet)
    result = run(packet, blobs)
    row = result['rows'][0]
    assert packet == before
    assert row['history'] == before['observations'][0]['history']
    assert row['interpretation'] == before['observations'][0]['interpretation']
    assert row['source'] == before['observations'][0]['source']
    assert row['version_identity'] == before['versions']
    assert row['protection_scope'] == 'SOURCE_ASSERTION_NOT_TARGET_APK'
    assert row['historical_classification'] == 'UNKNOWN' and row['category'] == 'AOSP'
    assert row['accepted_identity'] and row['source_correspondence_verified']
    assert row['capabilities'] == ['camera']
    assert 'ORIGINAL_HISTORICAL_EVENT_UNBOUND' in row['abstentions']
    assert not result['consumer_activation'] and not result['training_authorized']


@pytest.mark.parametrize('kind', ['governed', 'nonpermission', 'unresolved', 'conflict', 'projection', 'missing_source', 'original_event'])
def test_positive_abstention_and_governed_paths(kind):
    packet, blobs = fixture()
    row = packet['observations'][0]
    if kind == 'missing_source':
        del blobs[row['source']['payload_sha256']]
    elif kind == 'original_event':
        row['history']['original_event_id'] = row['source']['event_id']
        row['history']['original_payload_sha256'] = row['source']['payload_sha256']
        row['source']['historical_relationship'] = 'BOUND_ORIGINAL_EVENT'
    else:
        interpretation = row['interpretation']
        interpretation.update(category='UNKNOWN', canonical=None, protection_base=None, capabilities=[],
                              identity_recognition='UNRESOLVED_IDENTIFIER',
                              evidence_level='INSUFFICIENT_EVIDENCE', resolution_status='UNRESOLVED',
                              authority_scope='UNKNOWN', definition_source_present=False)
        if kind == 'governed':
            interpretation.update(category='GOOGLE', authority_scope='GOOGLE_SERVICE',
                                  evidence_level='GOVERNED_EXACT', resolution_status='RESOLVED_GOVERNED_EXACT')
        elif kind == 'nonpermission':
            interpretation.update(evidence_level='GOVERNED_NON_PERMISSION', resolution_status='RESOLVED_GOVERNED_NON_PERMISSION')
        elif kind == 'conflict':
            interpretation.update(evidence_level='CONFLICT', resolution_status='CONFLICTING_PROTECTION_EVIDENCE')
        elif kind == 'projection':
            row['token_hex'] = TOKEN.lower().encode().hex()
            row['source']['match_state'] = 'PROJECTED_UNIQUE_CANDIDATE'
        rebind_interpretation(packet, blobs)
    output = run(packet, blobs)['rows'][0]
    reasons = {'missing_source': 'SOURCE_BYTES_UNAVAILABLE', 'governed': 'PROTECTION_UNKNOWN',
               'nonpermission': 'EXCLUDE_NON_PERMISSION', 'unresolved': 'PERMISSION_AUTHORITY_UNRESOLVED',
               'conflict': 'PERMISSION_AUTHORITY_UNRESOLVED', 'projection': 'PROJECTION_AUTHORITY_NOT_ESTABLISHED'}
    if kind != 'original_event':
        assert reasons[kind] in output['abstentions']
    else:
        assert 'ORIGINAL_HISTORICAL_EVENT_UNBOUND' not in output['abstentions']


@pytest.mark.parametrize('kind', ['expired', 'future', 'revoked', 'wrong_purpose', 'training', 'stale_identity', 'stale_history', 'stale_version', 'byte_drift', 'snapshot', 'reader_drift'])
def test_binding_negative_paths(kind):
    packet, blobs = fixture()
    binding = bind(packet)
    operation = 'DESCRIBE_FAMILY'
    if kind == 'reader_drift': binding = replace(binding, reader_sha256='0' * 64)
    elif kind == 'expired': binding = replace(binding, expires_utc='2026-10-17T01:00:00Z')
    elif kind == 'future': binding = replace(binding, issued_utc='2026-10-19T00:00:00Z')
    elif kind == 'revoked': binding = replace(binding, revoked=True)
    elif kind == 'wrong_purpose': binding = replace(binding, purpose='PRODUCTION')
    elif kind == 'training': operation = 'TRAIN'
    elif kind == 'stale_identity': binding = replace(binding, identities_sha256='0' * 64)
    elif kind == 'stale_history': binding = replace(binding, history_sha256='0' * 64)
    elif kind == 'stale_version': binding = replace(binding, versions_sha256='0' * 64)
    elif kind == 'snapshot': binding = replace(binding, snapshot_id='other')
    else: packet['observations'][0]['history']['classification'] = 'GOOGLE'
    with pytest.raises(ValueError):
        run(packet, blobs, binding, operation)


@pytest.mark.parametrize('kind', ['wrong_sha', 'duplicate_id', 'duplicate_observation', 'missing_observation', 'extra_observation', 'wrong_event', 'wrong_payload_sample', 'bad_blob', 'missing_version_blob', 'wrong_raw_token', 'unknown_source_state', 'false_original', 'invented_category', 'unknown_category', 'false_canonical', 'governed_protection', 'nonpermission_capability', 'self_approval', 'missing_capability_map'])
def test_semantic_negative_paths_even_when_packet_digest_is_recomputed(kind):
    packet, blobs = fixture()
    row = packet['observations'][0]
    if kind == 'wrong_sha': row['sha256'] = 'f' * 64
    elif kind == 'duplicate_id': packet['samples'].append(deepcopy(packet['samples'][0]))
    elif kind == 'duplicate_observation': packet['observations'].append(deepcopy(row))
    elif kind == 'missing_observation': packet['observations'] = []
    elif kind == 'extra_observation':
        extra = deepcopy(row); extra['obs_id'] = 2; packet['observations'].append(extra)
    elif kind == 'wrong_event': row['source']['event_id'] = 9
    elif kind == 'bad_blob': blobs[row['source']['payload_sha256']] = b'corrupt'
    elif kind == 'missing_version_blob': del blobs[packet['versions']['classifier_source_sha256']]
    elif kind == 'wrong_raw_token': row['source']['raw_candidates'] = ['android.permission.FAKE']
    elif kind == 'unknown_source_state': row['source']['match_state'] = 'ASSUMED'
    elif kind == 'false_original': row['source']['historical_relationship'] = 'BOUND_ORIGINAL_EVENT'
    elif kind == 'invented_category': row['interpretation']['category'] = 'GOOGLE'
    elif kind == 'self_approval': packet['authority_granted'] = True
    elif kind == 'missing_capability_map': del packet['versions']['capability_mapping_sha256']
    elif kind == 'wrong_payload_sample':
        payload = json.loads(blobs[row['source']['payload_sha256']]);payload['data']['id'] = 'f' * 64
        raw = canonical_bytes(payload);blobs[digest(raw)] = raw;row['source']['payload_sha256'] = digest(raw)
        index = canonical_bytes({'1': {k: row['source'][k] for k in ('sample_id', 'sha256', 'event_id', 'payload_sha256')}})
        blobs[digest(index)] = index;packet['versions']['source_index_sha256'] = digest(index)
    else:
        if kind == 'unknown_category': row['interpretation']['category'] = 'NEW_UNREVIEWED_ENUM'
        elif kind == 'false_canonical': row['interpretation']['canonical'] = TOKEN.lower()
        elif kind == 'governed_protection':
            row['interpretation'].update(evidence_level='GOVERNED_EXACT', resolution_status='RESOLVED_GOVERNED_EXACT')
        elif kind == 'nonpermission_capability':
            row['interpretation'].update(evidence_level='GOVERNED_NON_PERMISSION', resolution_status='RESOLVED_GOVERNED_NON_PERMISSION')
        rebind_interpretation(packet, blobs)
    with pytest.raises((ValueError, FileNotFoundError)):
        run(packet, blobs)


def test_duplicate_json_keys_fail_before_use():
    packet, blobs = fixture()
    raw = canonical_bytes(packet)
    raw = b'{"purpose":"OFFLINE_CONFORMANCE_ONLY",' + raw[1:]
    binding = replace(bind(packet), packet_sha256=digest(raw))
    with pytest.raises(ValueError, match='duplicate JSON key'):
        validate_offline_packet(raw, binding, blobs.__getitem__, operation='DESCRIBE_FAMILY', now_utc=NOW)


def test_exact_identity_can_have_unknown_protection_without_defaulting():
    packet, blobs = fixture()
    row = packet['observations'][0]
    row['interpretation'].update(protection_base=None, capabilities=[])
    rebind_interpretation(packet, blobs)
    result = run(packet, blobs)['rows'][0]
    assert result['accepted_identity'] is True
    assert result['protection_base'] is None and 'PROTECTION_UNKNOWN' in result['abstentions']


def test_aggregate_evidence_budget_is_enforced(monkeypatch):
    packet, blobs = fixture()
    monkeypatch.setattr(consumer, 'MAX_EVIDENCE_BYTES', 10)
    with pytest.raises(ValueError, match='aggregate evidence byte bound'):
        run(packet, blobs)
