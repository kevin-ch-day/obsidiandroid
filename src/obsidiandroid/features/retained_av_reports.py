"""Validate retained Erebus report bytes for independent AV-only development.

No database/provider calls, permission reads, label inference or estimator fitting.
Report identities bind existing event IDs to exact stored payload hashes.
"""
from __future__ import annotations

import hashlib
import json
import re

import pandas as pd

from .av_lineage import identifier, lineage_components


def prepare_retained_av(snapshot):
    """Return coherent AV rows and conservative lineage components.

    Labels remain recorded reviewed attributions, not independent ground truth.
    Components union package, non-public signer and exact TLSH/ssdeep across
    the whole candidate cohort without consulting labels or model outcomes.
    Vhash is retained for structural-similarity audits, not standalone lineage.
    Missing fingerprints do not establish independence; callers must report it.
    """
    if snapshot.get('format') != 'obsidiandroid-retained-av-development-v1':
        raise ValueError('Unsupported retained AV snapshot')
    members = snapshot['members']
    reports = snapshot['reports']
    if not 1 <= len(members) <= 3000 or len(reports) != len(members):
        raise ValueError('Retained AV cohort must have 1..3000 exact reports')
    ids = [m['sample_id'] for m in members]
    hashes = [m['sha256'] for m in members]
    if (any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids)
            or len(set(hashes)) != len(hashes)
            or any(not re.fullmatch('[a-f0-9]{64}', s) for s in hashes)):
        raise ValueError('Invalid or duplicate sample identity')
    by_sha = {m['sha256']: m for m in members}
    seen = set()
    event_ids = set()
    rows, metadata = [], []
    for report in reports:
        sha = report['sha256']
        if sha not in by_sha or sha in seen or report.get('http_status') != 200:
            raise ValueError('Retained report identity or status mismatch')
        seen.add(sha)
        payload = report['payload_json']
        if hashlib.sha256(payload.encode()).hexdigest() != report['payload_hash']:
            raise ValueError('Retained report payload hash mismatch')
        if type(report['event_id']) is not int or report['event_id'] <= 0:
            raise ValueError('Retained event identity is missing')
        if report['event_id'] in event_ids:
            raise ValueError('Duplicate retained event identity')
        event_ids.add(report['event_id'])
        data = json.loads(payload)['data']
        attrs = data['attributes']
        if data['id'] != sha or attrs.get('sha256') != sha:
            raise ValueError('Provider and source SHA identities disagree')
        member = by_sha[sha]
        sid = member['sample_id']
        results = attrs.get('last_analysis_results')
        if not isinstance(results, dict) or not 1 <= len(results) <= 256:
            raise ValueError('Retained AV engine results unavailable or unbounded')
        for engine, verdict in sorted(results.items()):
            status = str(verdict.get('category', '')).replace('-', '_')
            if status not in {'malicious', 'suspicious', 'undetected', 'harmless',
                              'timeout', 'confirmed_timeout', 'failure', 'type_unsupported'}:
                raise ValueError('Unknown retained AV category')
            rows.append({'sample_id': sid, 'engine_name': engine, 'status': status,
                         'report_id': f"erebus-event:{report['event_id']}:{report['payload_hash']}"})
        certificate = attrs.get('androguard', {}).get('certificate', {}) or {}
        signer = str(certificate.get('thumbprint', '')).lower()
        if not re.fullmatch('[a-f0-9]{40}', signer):
            signer = ''
        package = identifier(member.get('package_group')).lower()
        values = {'package': package, 'signer_sha1': signer}
        for name in ('vhash', 'tlsh', 'ssdeep'):
            value = str(attrs.get(name, '') or '').strip()
            values[name] = '' if value.lower() in {'', 'null', 'none', 'n/a', 'tnull'} else value
        metadata.append({'sample_id': sid, 'sha256': sha, **values,
                         'recorded_family': member['recorded_family'],
                         'recorded_family_id': member['recorded_family_id']})
    components = lineage_components(metadata)
    for item in metadata:
        item['lineage_component'] = components[item['sample_id']]
    return pd.DataFrame(rows), pd.DataFrame(metadata).sort_values('sample_id').reset_index(drop=True)
