#!/usr/bin/env python3
"""Offline PI-owner snapshot -> Obsidian analytical ATT&CK dispositions.

No database/network/provider access, training, or family-label input. Outputs
are created in a fresh directory; a retained snapshot is never a live attestation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from obsidiandroid.governance.mobile_attack_permission_mapping import mobile_attack_permission_mapping_payload
from obsidiandroid.governance.permission_attack_evidence import (
    PermissionIdentity, PermissionObservation, assess_permission_observation,
    load_retained_pi_catalog, project_identity_dispositions, build_development_store,
)


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, (list, dict, tuple)) else v
                         for k, v in row.items()} for row in rows)


def identity_index(rows: list[dict]) -> dict[str, PermissionIdentity]:
    return {r['canonical_permission']: PermissionIdentity(
        r['canonical_permission'], r['authority_class'], r['identity_status'],
        r['source_scope'], r['source_digest'], json.dumps(r['protection']), r['api_release'])
        for r in rows}


def report_approved_export(path: Path, identities: dict, mapping: dict) -> tuple[list[dict], dict]:
    # Use the existing fail-closed root-approved consumer; this is not a new
    # export authorization path. No occurrence-feature frame is constructed.
    from obsidiandroid.orchestration.permission_v2_export import _checked_export, describe_v2_occurrences
    payload, _, export = _checked_export(path)
    describe_v2_occurrences(path)  # Validate all exact bindings and raw members.
    import hashlib
    export_sha = hashlib.sha256(payload).hexdigest()
    result = []
    for sample in export['samples']:
        for member in sample['members']:
            observation = PermissionObservation(
                sample['sample_id'], sample['sha256'], member['raw_token'], 'UNKNOWN',
                'PROVIDER_REPORT', export['source_commit'],
                source_snapshot_digest=sample['source_snapshot_digest'],
                provenance_refs=(str(path), 'export-sha256:' + export_sha),
                source_validation='SOURCE_BOUND')
            result.extend(assess_permission_observation(observation, identities.get(observation.raw_token), mapping))
    assert all(not r['technique_observed'] for r in result)
    return result, {'samples': len(export['samples']), 'raw_observations': sum(len(s['members']) for s in export['samples']),
                    'relationship_rows': len(result), 'export_sha256': export_sha,
                    'observation_roles': dict(Counter(r['role'] for r in result)),
                    'observation_timestamps_available': sum(r['timestamp_available'] for r in result),
                    'techniques_observed': 0,
                    'dispositions': dict(Counter(r['disposition'] for r in result)),
                    'missing_observation_semantics': 'ABSENT_EXPORT_MEMBERSHIP_IS_UNKNOWN_NOT_VERIFIED_NEGATIVE'}


def run(catalog_path: Path, expected_sha256: str, output: Path, export_path: Path | None = None,
        owner_export_path: Path | None = None, owner_export_sha256: str | None = None) -> dict:
    catalog, digest = load_retained_pi_catalog(catalog_path, expected_sha256)
    mapping = mobile_attack_permission_mapping_payload()
    rows = project_identity_dispositions(catalog, digest, mapping)
    from obsidiandroid.governance.permission_attack_reconciliation import (
        load_owner_reference_export, reconcile_catalog_populations,
    )
    if (owner_export_path is None) != (owner_export_sha256 is None):
        raise ValueError('Owner export path and trusted SHA-256 must be supplied together')
    current = load_owner_reference_export(owner_export_path, owner_export_sha256) if owner_export_path else None
    reconciliation = reconcile_catalog_populations(rows, current)
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output/'PI_CATALOG_RECONCILIATION.csv', reconciliation)
    write_csv(output/'PERMISSION_ATTACK_MAPPING_COVERAGE.csv', rows)
    store = build_development_store(output/'permission_attack_development.sqlite3', rows, mapping)
    receipt = {**store, 'catalog_path': str(catalog_path), 'catalog_sha256': digest,
               'catalog_scope': catalog['fixture_set'], 'live_currentness': 'NOT_ATTESTED',
               'current_reconciliation_status': 'SUPPLIED_OWNER_EXPORT_ONLY' if current else 'CURRENT_EVIDENCE_UNAVAILABLE',
               'reconciliation_rows': len(reconciliation),
               'dispositions': dict(Counter(r['disposition'] for r in rows)),
               'authorities': dict(Counter(r['authority_class'] for r in rows)),
               'mapping_version': mapping['version'], 'mapping_hash': mapping['hash'],
               'attack_source': mapping['attack_source']}
    if export_path is not None:
        reports, receipt['sample_reporting'] = report_approved_export(export_path, identity_index(rows), mapping)
        write_csv(output/'SOURCE_AWARE_SAMPLE_RELATIONSHIPS.csv', reports)
    (output/'PROJECTION_RECEIPT.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--catalog-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--approved-export', type=Path)
    parser.add_argument('--current-owner-export', type=Path)
    parser.add_argument('--current-owner-sha256')
    args = parser.parse_args()
    print(json.dumps(run(args.catalog, args.catalog_sha256, args.output, args.approved_export, args.current_owner_export, args.current_owner_sha256), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
