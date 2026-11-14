"""Exact retained/current catalog comparison for the existing analytical projection.

No database connections, alias expansion, permission authority changes or sample
occurrence approval. Owner attestation is required metadata, not authenticated by
this byte/structure validator; the operator must bind the trusted manifest hash.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

EXPORT_SCHEMA = 'pi-owner-reference-catalog-export-v1'


def load_owner_reference_export(path: Path, expected_sha256: str) -> dict:
    """Validate an explicitly owner-authorized reference-only export and hash."""
    if not re.fullmatch('[a-f0-9]{64}', expected_sha256):
        raise ValueError('Explicit owner export SHA-256 required')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Owner export SHA-256 mismatch')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate owner export JSON key')
            result[key] = value
        return result
    export = json.loads(raw, object_pairs_hook=unique)
    if export.get('schema_version') != EXPORT_SCHEMA:
        raise ValueError('Unsupported owner reference export schema')
    scope = export.get('scope', {})
    for field in ('database', 'snapshot_id', 'generated_at', 'schema_version',
                  'migration_versions', 'source_owner', 'coverage_statement', 'authorization_ref'):
        if field not in scope or scope[field] is None or scope[field] == '':
            raise ValueError('Missing owner scope/authorization field: ' + field)
    if scope['database'] != 'android_permission_intel':
        raise ValueError('Wrong owner database identity')
    instant = datetime.fromisoformat(scope['generated_at'].replace('Z', '+00:00'))
    if instant.tzinfo is None:
        raise ValueError('Owner snapshot timestamp timezone required')
    if scope.get('purpose') != 'REFERENCE_CATALOG_RECONCILIATION':
        raise ValueError('Owner export is not reference-only authorized evidence')
    identities = export.get('identities')
    if not isinstance(identities, list) or type(export.get('record_count')) is not int or export['record_count'] != len(identities):
        raise ValueError('Owner catalog record count mismatch')
    seen = set()
    for entry in identities:
        token = entry.get('raw_token')
        if not isinstance(token, str) or not token or token in seen:
            raise ValueError('Missing or duplicate exact owner identity')
        seen.add(token)
        if token.encode('utf-8').hex() != entry.get('raw_token_utf8_hex'):
            raise ValueError('Exact owner permission bytes mismatch')
        for field in ('authority_class', 'lifecycle_state', 'canonical_interpretations',
                      'aliases', 'api_context', 'protection_context', 'evidence_refs',
                      'available_observation_roles', 'observation_time_fields'):
            if field not in entry:
                raise ValueError('Owner identity lacks explicit field/unknown: ' + field)
        for field in ('canonical_interpretations', 'aliases', 'evidence_refs',
                      'available_observation_roles', 'observation_time_fields'):
            values = entry[field]
            if values is not None and (not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values) or len(values) != len(set(values))):
                raise ValueError('Invalid owner evidence field: ' + field)
        if entry['authority_class'] is None or not isinstance(entry['authority_class'], str):
            raise ValueError('Explicit owner authority class/UNKNOWN required')
    export['verified_artifact_sha256'] = expected_sha256
    return export


def _change(before, after) -> str:
    if before is None or after is None:
        return 'UNKNOWN'
    return 'UNCHANGED' if before == after else 'CHANGED'


def reconcile_catalog_populations(retained_rows: list[dict], current: dict | None = None) -> list[dict]:
    """Compare exact tokens, preserving missing-current evidence as UNKNOWN.

    Source absence is a population observation, never deletion or wrongdoing.
    Retained rows lack lifecycle/role/time authority: those dimensions remain
    unknown unless actually supplied, not inferred from the ATT&CK disposition.
    """
    prior = {r['canonical_permission']: r for r in retained_rows}
    if len(prior) != len(retained_rows):
        raise ValueError('Duplicate retained exact identity')
    if current is not None and 'verified_artifact_sha256' not in current:
        raise ValueError('Load a hash-validated owner reference export first')
    present = {r['raw_token']: r for r in current['identities']} if current is not None else {}
    if current is not None and len(present) != len(current['identities']):
        raise ValueError('Duplicate current exact identity')
    result = []
    for token in sorted(set(prior) | set(present)):
        old = prior.get(token)
        new = present.get(token)
        membership = ('CURRENT_EVIDENCE_UNAVAILABLE' if current is None else
                      'EXACT_BOTH' if old is not None and new is not None else
                      'RETAINED_ONLY_IN_SUPPLIED_SCOPES' if old is not None else
                      'CURRENT_ONLY_IN_SUPPLIED_SCOPES')
        interpretations = new['canonical_interpretations'] if new else None
        result.append({
            'raw_token': token, 'raw_token_utf8_hex': token.encode('utf-8').hex(),
            'reconciliation_status': membership, 'retained_present': old is not None,
            'current_present': (new is not None) if current is not None else None,
            'retained_source_scope': old['source_scope'] if old else None,
            'retained_source_digest': old['source_digest'] if old else None,
            'current_snapshot': current['scope']['snapshot_id'] if current is not None else None,
            'current_export_sha256': current['verified_artifact_sha256'] if current is not None else None,
            'retained_authority': old['authority_class'] if old else None,
            'current_authority': new['authority_class'] if new else None,
            'authority_comparison': _change(old['authority_class'] if old else None, new['authority_class'] if new else None),
            'retained_lifecycle': old.get('lifecycle_state') if old else None,
            'current_lifecycle': new['lifecycle_state'] if new else None,
            'lifecycle_comparison': _change(old.get('lifecycle_state') if old else None, new['lifecycle_state'] if new else None),
            'current_canonical_interpretations': interpretations,
            'canonical_comparison': ('UNKNOWN' if old is None or not interpretations else
                                    'UNCHANGED' if interpretations == [token] else 'CONFLICT_REQUIRES_OWNER_REVIEW'),
            'current_aliases_not_applied': new['aliases'] if new else None,
            'retained_provenance': 'PRESENT' if old and old.get('source_provenance_refs') else 'UNKNOWN',
            'current_provenance': 'UNKNOWN' if new is None or new['evidence_refs'] is None else 'PRESENT' if new['evidence_refs'] else 'MISSING',
            'current_available_observation_roles': new['available_observation_roles'] if new else None,
            'current_observation_time_fields': new['observation_time_fields'] if new else None,
            'current_role_evidence_status': 'UNKNOWN' if new is None or new['available_observation_roles'] is None else 'AVAILABLE' if new['available_observation_roles'] else 'NONE_IN_EXPORT',
            'current_timestamp_evidence_status': 'UNKNOWN' if new is None or new['observation_time_fields'] is None else 'AVAILABLE' if new['observation_time_fields'] else 'NONE_IN_EXPORT',
            'mapping_disposition': old['disposition'] if old else 'UNRESOLVED' if new['authority_class']=='UNKNOWN' or interpretations != [token] else 'PENDING_REVIEW',
            'mapping_assessment_scope': 'RETAINED_SNAPSHOT_NOT_CURRENT_AUTHORITY' if old else 'UNREVIEWED_CURRENT_IDENTITY',
            'attack_ids': old['attack_ids'] if old else [],
            'source_absence_means_deleted': False, 'technique_observed': False,
        })
    return result
