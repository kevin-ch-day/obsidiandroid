"""Offline evidence-consumer conformance, with no production admission path.

A binding supplied by an audit harness pins immutable bytes. It is deliberately
not the installed V2 approval anchor and cannot authorize features or training.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Callable

FORMAT = 'obsidiandroid-pi-offline-conformance-v1'
PURPOSE = 'OFFLINE_CONFORMANCE_ONLY'
MAX_EVIDENCE_BYTES = 128 * 1024 * 1024
OPERATIONS = frozenset({'DESCRIBE_SAMPLE', 'DESCRIBE_FAMILY', 'DESCRIBE_TYPE', 'DESCRIBE_TEMPORAL'})
LEVELS = frozenset({'CATALOG_ACCEPTED', 'GOVERNED_EXACT', 'GOVERNED_NON_PERMISSION',
                   'SOURCE_ASSERTED', 'KIND_ANNOTATION', 'PATTERN_ONLY', 'PROVISIONAL',
                   'INSUFFICIENT_EVIDENCE', 'CONFLICT'})
STATUSES = frozenset({'RESOLVED_CURRENT_IDENTITY', 'RESOLVED_GOVERNED_EXACT',
                     'RESOLVED_GOVERNED_NON_PERMISSION', 'RESOLVED_SOURCE_AUTHORITY',
                     'SOURCE_KIND_ONLY', 'PATTERN_ONLY', 'PROVISIONAL', 'UNRESOLVED',
                     'CONFLICTING_PROTECTION_EVIDENCE', 'CONFLICTING_AUTHORITY_EVIDENCE'})
CATEGORIES = frozenset({'AOSP', 'GOOGLE', 'OEM', 'APP_DEFINED', 'UNKNOWN'})
PROTECTION = frozenset({'normal', 'dangerous', 'signature', 'signatureOrSystem', 'internal'})
IDENTITIES = frozenset({'EXACT_ACCEPTED_CANONICAL', 'CASE_ONLY_CANONICAL_CANDIDATE',
                        'NONCANONICAL_KNOWN_IDENTIFIER', 'UNRESOLVED_IDENTIFIER'})


def canonical_bytes(value: object) -> bytes:
    """Encode JSON deterministically; reject non-JSON floating point values."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _check(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0,
           'UTC timestamp required')
    return parsed


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _check(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def _json(raw: bytes):
    return json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


@dataclass(frozen=True)
class OfflineBinding:
    """Independent audit-harness pins; never a production permission grant."""

    packet_sha256: str
    identities_sha256: str
    history_sha256: str
    versions_sha256: str
    snapshot_id: str
    issued_utc: str
    expires_utc: str
    reader_sha256: str
    operations: tuple[str, ...] = ('DESCRIBE_FAMILY',)
    purpose: str = PURPOSE
    revoked: bool = False


def validate_offline_packet(
    raw: bytes,
    binding: OfflineBinding,
    read_blob: Callable[[str], bytes],
    *,
    operation: str,
    now_utc: datetime,
) -> dict:
    """Verify bounded bytes and cross-row semantics, returning audit dimensions.

    ``read_blob`` is an offline content-addressed byte reader owned by the harness.
    Missing occurrence blobs cause explicit abstention; corrupt bytes fail closed.
    Version/reference bytes are mandatory. No network or database is opened here.
    """
    _check(binding.purpose == PURPOSE and binding.revoked is False, 'offline binding revoked or wrong purpose')
    _check(binding.reader_sha256 == digest(Path(__file__).read_bytes()), 'consumer reader identity changed')
    _check(operation in OPERATIONS and operation in binding.operations, 'operation not allowed')
    _check(now_utc.tzinfo is not None and now_utc.utcoffset().total_seconds() == 0, 'UTC clock required')
    _check(_utc(binding.issued_utc) <= now_utc < _utc(binding.expires_utc), 'offline binding expired or not yet valid')
    _check(len(raw) <= 64 * 1024 * 1024 and digest(raw) == binding.packet_sha256, 'packet byte identity mismatch')
    packet = _json(raw)
    _check(set(packet) == {'format', 'purpose', 'snapshot_id', 'versions', 'samples', 'observations'},
           'unsupported packet fields')
    _check(packet['format'] == FORMAT and packet['purpose'] == PURPOSE, 'unsupported packet contract')
    _check(packet['snapshot_id'] == binding.snapshot_id, 'snapshot mismatch')
    samples, observations, versions = packet['samples'], packet['observations'], packet['versions']
    _check(0 < len(samples) <= 1212 and len(observations) <= 100000, 'population bound exceeded')
    _check(digest(canonical_bytes(samples)) == binding.identities_sha256, 'identity population changed')
    _check(digest(canonical_bytes(versions)) == binding.versions_sha256, 'version identity changed')
    _check(versions['classifier_policy'] == 'permission-current-interpretation-adapter-v4'
           and versions['profile_version'] == 'permission-operational-dimensions-v2', 'unsupported classifier/profile version')
    for key in ('classifier_source_sha256', 'dictionary_sha256', 'interpretations_sha256',
                'source_index_sha256'):
        _check(_hex(versions[key]), 'version digest required')
    _check(bool(versions['dictionary_release']) and _hex(versions['dictionary_catalog_digest']), 'dictionary release identity required')
    cache = {}
    evidence_bytes = 0

    def blob(key):
        nonlocal evidence_bytes
        _check(_hex(key), 'invalid blob identity')
        if key not in cache:
            data = read_blob(key)
            _check(isinstance(data, bytes) and len(data) <= 64 * 1024 * 1024
                   and digest(data) == key, 'evidence blob byte identity mismatch')
            evidence_bytes += len(data)
            _check(evidence_bytes <= MAX_EVIDENCE_BYTES, 'aggregate evidence byte bound exceeded')
            cache[key] = data
        return cache[key]

    # Mandatory source/interpretation identity; cannot abstain into an unknown version.
    blob(versions['classifier_source_sha256'])
    for key, value in versions.items():
        if key.endswith('_sha256'):
            blob(value)
    catalog = _json(blob(versions['dictionary_sha256']))
    reference = _json(blob(versions['interpretations_sha256']))
    source_index = _json(blob(versions['source_index_sha256']))
    _check(catalog['release'] == versions['dictionary_release']
           and catalog['catalog_digest'] == versions['dictionary_catalog_digest'], 'dictionary metadata mismatch')
    accepted_tokens = set(catalog['accepted_tokens'])
    _check(len(accepted_tokens) == len(catalog['accepted_tokens']), 'duplicate canonical identities')
    catalog_rows = list(csv.DictReader(io.StringIO(blob(catalog['source_bytes_sha256']).decode('utf-8'))))
    catalog_by_token = {row['canonical_permission']: row for row in catalog_rows}
    _check(len(catalog_rows) == len(catalog_by_token)
           and accepted_tokens == {row['canonical_permission'] for row in catalog_rows
                                    if row['identity_status'] == 'ACCEPTED'},
           'canonical projection differs from dictionary bytes')
    _check(all(row['catalog_release_id'] == catalog['release']
               and row['catalog_digest'] == catalog['catalog_digest'] for row in catalog_rows),
           'dictionary row version mismatch')
    by_id = {}
    hashes = set()
    for sample in samples:
        sid, sha = sample['sample_id'], sample['sha256']
        _check(type(sid) is int and sid > 0 and _hex(sha), 'invalid sample identity')
        _check(sid not in by_id and sha not in hashes, 'duplicate sample identity')
        _check(type(sample['observation_count']) is int and sample['observation_count'] >= 0,
               'sample observation denominator required')
        by_id[sid] = sample
        hashes.add(sha)
    histories = [{'obs_id': row['obs_id'], 'sample_id': row['sample_id'],
                  'sha256': row['sha256'], 'token_hex': row['token_hex'],
                  'history': row['history']} for row in observations]
    _check(digest(canonical_bytes(histories)) == binding.history_sha256, 'immutable history changed')
    seen = set()
    seen_tokens = set()
    counts = {sid: 0 for sid in by_id}
    output = []
    report_cache = {}
    for row in observations:
        oid, sid = row['obs_id'], row['sample_id']
        _check(type(oid) is int and oid > 0 and oid not in seen, 'duplicate/invalid observation identity')
        seen.add(oid)
        _check(sid in by_id and row['sha256'] == by_id[sid]['sha256'], 'observation sample ID/SHA mismatch')
        counts[sid] += 1
        token = bytes.fromhex(row['token_hex']).decode('utf-8')
        _check(bool(token) and len(token) <= 512 and row['token_hex'] == token.encode().hex(), 'invalid exact token bytes')
        _check((sid, row['token_hex']) not in seen_tokens, 'duplicate sample/token observation')
        seen_tokens.add((sid, row['token_hex']))
        history, interpretation, source = row['history'], row['interpretation'], row['source']
        _check(history['classification'] in CATEGORIES, 'unknown historical category')
        _utc(history['observed_utc'])
        for field in ('rule', 'source', 'run_id', 'classifier_policy', 'authority_snapshot_sha256',
                      'recovery_plan_sha256', 'original_event_id', 'original_payload_sha256',
                      'canonical_snapshot', 'protection_snapshot'):
            _check(field in history, 'historical field must be explicit, including unknown')
        _check(token in reference and interpretation == reference[token], 'interpretation differs from pinned source')
        level, status = interpretation['evidence_level'], interpretation['resolution_status']
        category, canonical = interpretation['category'], interpretation['canonical']
        protection = interpretation['protection_base']
        _check(level in LEVELS and status in STATUSES and category in CATEGORIES
               and interpretation['identity_recognition'] in IDENTITIES, 'unsupported interpretation enum')
        _check(protection is None or protection in PROTECTION, 'unknown protection category')
        _check(type(interpretation['definition_source_present']) is bool, 'definition provenance state required')
        accepted = interpretation['identity_recognition'] == 'EXACT_ACCEPTED_CANONICAL'
        if accepted:
            _check(canonical == token and token in accepted_tokens and level == 'CATALOG_ACCEPTED',
                   'canonical acceptance requires exact dictionary identity')
            _check(interpretation['definition_source_present']
                   == (catalog_by_token[token]['source_provenance_status'] == 'PRESENT'),
                   'definition provenance differs from dictionary')
        if level == 'CATALOG_ACCEPTED':
            _check(accepted, 'catalog evidence requires accepted exact identity')
        if level == 'GOVERNED_EXACT' or status == 'RESOLVED_GOVERNED_EXACT':
            _check(level == 'GOVERNED_EXACT' and status == 'RESOLVED_GOVERNED_EXACT'
                   and category == 'GOOGLE' and interpretation['authority_scope'] == 'GOOGLE_SERVICE'
                   and not accepted and protection is None, 'governed category does not grant catalog/protection authority')
        nonpermission = status == 'RESOLVED_GOVERNED_NON_PERMISSION'
        if nonpermission or level == 'GOVERNED_NON_PERMISSION':
            _check(nonpermission and level == 'GOVERNED_NON_PERMISSION'
                   and category == 'UNKNOWN' and protection is None and not accepted, 'non-permission interpretation conflict')
        if level == 'CONFLICT' or status.startswith('CONFLICTING_'):
            _check(level == 'CONFLICT' and status.startswith('CONFLICTING_') and protection is None,
                   'conflicting evidence must abstain on protection')
        _check(interpretation['capability_status'] == 'CANDIDATE_NOT_APPROVED', 'capability promotion forbidden')
        _check(isinstance(interpretation['capabilities'], list)
               and all(isinstance(v, str) and v for v in interpretation['capabilities']), 'invalid capability candidates')
        if interpretation['capabilities']:
            _check('capability_mapping_sha256' in versions, 'capability mapping identity required')
            _check(accepted and protection is not None and interpretation['definition_source_present'],
                   'capability candidate lacks required exact definition evidence')
        _check(source['sample_id'] == sid and source['sha256'] == row['sha256'], 'source sample ID/SHA mismatch')
        _check(type(source['event_id']) is int and source['event_id'] > 0, 'source event identity required')
        _check(source_index.get(str(sid)) == {
            'sample_id': sid, 'sha256': row['sha256'], 'event_id': source['event_id'],
            'payload_sha256': source['payload_sha256'],
        }, 'source event differs from pinned source index')
        reasons = []
        source_verified = False
        _check(source['match_state'] in {'RAW_EXACT', 'PROJECTED_UNIQUE_CANDIDATE',
                                        'PROJECTED_MULTIPLE_CANDIDATES',
                                        'NO_MATCH_IN_LATEST_RETAINED_REPORT'},
               'unsupported source correspondence state')
        try:
            payload_hash = source['payload_sha256']
            if payload_hash not in report_cache:
                report_cache[payload_hash] = _json(blob(payload_hash))
            report = report_cache[payload_hash]['data']
            _check(report['id'] == row['sha256'], 'report SHA does not match sample')
            permissions = (report.get('attributes', {}).get('androguard') or {}).get('permission_details')
            _check(isinstance(permissions, dict), 'declared permission evidence missing in report')
            candidates = source['raw_candidates']
            _check(isinstance(candidates, list) and len(candidates) == len(set(candidates))
                   and all(v in permissions for v in candidates), 'source token correspondence mismatch')
            state = source['match_state']
            if state == 'RAW_EXACT':
                _check(candidates == [token] and token in permissions, 'exact source token mismatch')
                source_verified = True
            elif state == 'PROJECTED_UNIQUE_CANDIDATE':
                _check(len(candidates) == 1 and token not in permissions, 'projection candidate ambiguity')
                reasons.append('PROJECTION_AUTHORITY_NOT_ESTABLISHED')
            elif state == 'PROJECTED_MULTIPLE_CANDIDATES':
                _check(len(candidates) > 1 and token not in permissions, 'multiple candidates required')
                reasons.append('AMBIGUOUS_PROJECTION')
            elif state == 'NO_MATCH_IN_LATEST_RETAINED_REPORT':
                _check(not candidates and token not in permissions, 'claimed source absence conflicts with bytes')
                reasons.append('NO_SOURCE_TOKEN_MATCH')
            else:
                raise ValueError('unsupported source correspondence state')
        except FileNotFoundError:
            reasons.append('SOURCE_BYTES_UNAVAILABLE')
        relationship = source['historical_relationship']
        if relationship == 'BOUND_ORIGINAL_EVENT':
            _check(history['original_event_id'] == source['event_id']
                   and history['original_payload_sha256'] == source['payload_sha256'], 'unbound historical source claim')
        else:
            _check(relationship == 'LATEST_REPORT_CORRESPONDENCE_ONLY', 'unknown historical relationship')
            reasons.append('ORIGINAL_HISTORICAL_EVENT_UNBOUND')
        if not accepted:
            reasons.append('NO_ACCEPTED_CANONICAL_IDENTITY')
        if protection is None:
            reasons.append('PROTECTION_UNKNOWN')
        if level in {'INSUFFICIENT_EVIDENCE', 'PATTERN_ONLY', 'PROVISIONAL', 'KIND_ANNOTATION', 'CONFLICT'}:
            reasons.append('PERMISSION_AUTHORITY_UNRESOLVED')
        if nonpermission:
            reasons.append('EXCLUDE_NON_PERMISSION')
        output.append({'obs_id': oid, 'sample_id': sid, 'sha256': row['sha256'],
                       'family': by_id[sid]['family'], 'exact_token': token,
                       'historical_classification': history['classification'], 'category': category,
                       'accepted_identity': accepted, 'evidence_level': level,
                       'resolution_status': status, 'protection_base': protection,
                       'definition_source_present': interpretation['definition_source_present'],
                       'canonical_identity': canonical if accepted else None,
                       'canonical_candidate': canonical,
                       'protection_scope': 'SOURCE_ASSERTION_NOT_TARGET_APK',
                       'history': dict(history), 'interpretation': dict(interpretation),
                       'source': dict(source), 'version_identity': dict(versions),
                       'capabilities': list(interpretation['capabilities']),
                       'source_correspondence_verified': source_verified,
                       'source_match_state': source['match_state'],
                       'historical_relationship': relationship,
                       'abstentions': reasons})
    _check(all(counts[sid] == sample['observation_count'] for sid, sample in by_id.items()),
           'sample observation denominator mismatch')
    return {'status': 'OFFLINE_CONFORMANCE_PASS', 'purpose': PURPOSE,
            'consumer_activation': False, 'training_authorized': False,
            'sample_count': len(samples), 'observation_count': len(output),
            'rows': output}
