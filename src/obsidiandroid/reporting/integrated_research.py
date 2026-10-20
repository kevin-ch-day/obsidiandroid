"""Read-only, identity-bound descriptive research over explicit retained packets.

No model loading, database connections, permission inference or training authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import pandas as pd

from obsidiandroid.labeling.taxonomy import normalize_family_name
from obsidiandroid.reporting.permission_coverage import (
    consumer_availability, coverage_summary, validate_coverage,
)

FORMAT = 'obsidiandroid-integrated-research-v1'


def attribution_relationship(raw, canonical):
    """Describe normalization agreement without rewriting authoritative labels."""
    a, b = str(raw or '').strip(), str(canonical or '').strip()
    unknown = {'', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan'}
    if a.lower() in unknown or b.lower() in unknown:
        return 'unresolved'
    if a == b:
        return 'exact'
    if a.casefold() == b.casefold():
        return 'case_or_whitespace'
    if re.sub(r'[\s_-]+', '', a.casefold()) == re.sub(r'[\s_-]+', '', b.casefold()):
        return 'separator_formatting'
    normalized = normalize_family_name(a)
    if normalized not in unknown and normalized == normalize_family_name(b):
        return 'recognized_normalization'
    return 'conflict_requires_review'


def submission_proxy(first_submission, scan_time):
    """Interpret only provider Unix seconds, never substitute other date fields."""
    def timestamp(value):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            return None
        try:
            return pd.to_datetime(value, unit='s', utc=True, errors='raise')
        except (ValueError, OverflowError, pd.errors.OutOfBoundsDatetime):
            return None
    first, scan = timestamp(first_submission), timestamp(scan_time)
    anomaly = first is not None and scan is not None and first > scan
    return {'first_submission_utc': first.isoformat() if first is not None else '',
            'last_analysis_utc': scan.isoformat() if scan is not None else '',
            'first_submission_month': first.strftime('%Y-%m') if first is not None else '',
            'first_after_analysis': anomaly,
            'temporal_eligible': first is not None and not anomaly}


def attach_permission_coverage(samples, identities):
    """Require both ID and SHA agreement; unknown coverage is not zero permissions."""
    for frame in (samples, identities):
        if frame.sample_id.duplicated().any() or frame.sha256.duplicated().any():
            raise ValueError('Duplicate sample identity')
    by_id = samples.set_index('sample_id').sha256.to_dict()
    by_sha = samples.set_index('sha256').sample_id.to_dict()
    for row in identities.itertuples():
        if ((row.sample_id in by_id and by_id[row.sample_id] != row.sha256)
                or (row.sha256 in by_sha and by_sha[row.sha256] != row.sample_id)):
            raise ValueError('Permission sample ID/SHA disagreement')
    pairs = set(zip(identities.sample_id, identities.sha256))
    result = samples.copy()
    result['permission_covered'] = [(sid, sha) in pairs for sid, sha in
                                     zip(result.sample_id, result.sha256)]
    result['permission_state'] = result.permission_covered.map(
        {True: 'PROVIDER_REPORTED_UNRESOLVED', False: 'UNAVAILABLE'})
    return result


def permission_profile(samples, occurrences):
    """Count distinct covered samples, with an explicit covered denominator."""
    covered = samples.loc[samples.permission_covered.eq(True), 'sample_id']
    subset = occurrences[occurrences.sample_id.isin(covered)]
    counts = subset.drop_duplicates(['sample_id', 'token']).groupby('token').size()
    return [{'token': token, 'samples': int(count), 'covered_denominator': len(covered),
             'covered_prevalence': float(count / len(covered)),
             'category': 'UNAVAILABLE', 'capability': 'UNAVAILABLE',
             'definition_state': 'No governed definition in approved export'}
            for token, count in counts.sort_values(ascending=False).items()]


class ResearchPacket:
    """Load explicit checksum-bound CSV evidence without executable artifacts."""

    def __init__(self, directory):
        self.root = Path(directory).resolve()
        raw_manifest = (self.root / 'RESEARCH_MANIFEST.json').read_bytes()
        self.manifest = json.loads(raw_manifest)
        self.manifest_sha256 = hashlib.sha256(raw_manifest).hexdigest()
        if self.manifest.get('format') != FORMAT:
            raise ValueError('Unsupported research packet')
        self.samples = self._csv('SAMPLES.csv')
        self.permissions = self._csv('PERMISSIONS.csv')
        if self.samples.sample_id.duplicated().any() or self.samples.sha256.duplicated().any():
            raise ValueError('Duplicate packet identities')
        pairs = set(zip(self.samples.sample_id, self.samples.sha256))
        if any(pair not in pairs for pair in zip(self.permissions.sample_id, self.permissions.sha256)):
            raise ValueError('Permission rows do not match packet identities')
        self.coverage = None
        self.coverage_metadata = self.manifest.get('permission_coverage_audit')
        if self.coverage_metadata is not None:
            self.coverage = self._csv('PI_COVERAGE.csv')
            validate_coverage(self.samples, self.coverage, self.coverage_metadata)
        elif 'PI_COVERAGE.csv' in self.manifest.get('files', {}):
            raise ValueError('Permission coverage metadata missing')

    def _csv(self, name):
        path = self.root / name
        if path.is_symlink() or path.stat().st_size > 128 * 1024**2:
            raise ValueError('Research artifact exceeds bound or is a symlink')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.manifest['files'][name]:
            raise ValueError('Research artifact hash mismatch')
        from io import BytesIO
        return pd.read_csv(BytesIO(raw), keep_default_na=False)

    def describe(self, kind='overview', value=''):
        """Return sample/family/type evidence; unknown populations remain visible."""
        rows = self.samples
        if kind == 'sample':
            rows = rows[rows.sample_id.eq(int(value))] if str(value).isdigit() else rows[rows.sha256.eq(str(value).lower())]
        elif kind in {'family', 'type'}:
            field = 'recorded_family' if kind == 'family' else 'malware_type'
            rows = rows[rows[field].str.casefold().eq(str(value).casefold())]
        elif kind != 'overview':
            raise ValueError('Unknown research perspective')
        covered = int(rows.permission_covered.eq(True).sum())
        eligible = rows[rows.temporal_eligible.eq(True)]
        output = {'evidence': 'Frozen descriptive snapshot; not independent evaluation or current approval',
                  'samples': len(rows), 'permission_covered_samples': covered,
                  'permission_unavailable_samples': len(rows) - covered,
                  'permission_coverage_scope': 'Approved export membership; upstream coverage is a separate audit',
                  'upstream_audit_authorizes_features': False,
                  'permission_coverage_matrix': coverage_summary(rows, self.coverage, self.coverage_metadata),
                  'permission_consumer_availability': consumer_availability(rows, self.coverage, self.coverage_metadata),
                  'category_and_capability_state': 'UNAVAILABLE: governed definitions not present',
                  'type_basis': 'Family primary taxonomy mapping; not sample behavior',
                  'training_authorized': False,
                  'families': rows.recorded_family.value_counts().to_dict(),
                  'types': rows.malware_type.value_counts().to_dict(),
                  'sources': rows.source_batch_label.replace('', 'Unavailable').value_counts().to_dict(),
                  'label_authority': rows.authority_basis.replace('', 'Unavailable').value_counts().to_dict(),
                  'label_eligible_samples': int(rows.reviewed_label.eq(True).sum()),
                  'vendor_conflicting_samples': int((rows.distinct_known_families > 1).sum()),
                  'vendor_unresolved_samples': int(rows.known_family_votes.eq(0).sum()),
                  'temporal_eligible_samples': len(eligible),
                  'missing_first_submission': int(rows.first_submission_utc.eq('').sum()),
                  'first_after_analysis': int(rows.first_after_analysis.eq(True).sum()),
                  'first_submission_months': eligible.first_submission_month.value_counts().sort_index().to_dict(),
                  'permission_profile': permission_profile(rows, self.permissions)}
        if kind == 'sample':
            output['records'] = rows.to_dict('records')
            if len(rows) == 1:
                output['vendor_claims'] = self.vendor_claims(int(rows.iloc[0].sample_id))
                output['exact_permission_tokens'] = self.permissions[self.permissions.sample_id.eq(int(rows.iloc[0].sample_id))].to_dict('records')
        return output

    def vendor_claims(self, sample_id):
        """Read only the indexed retained vendor shard, verifying its exact bytes."""
        entry = self.manifest['vendor_shards'][str(sample_id)]
        path = Path(entry['path'])
        if path.is_symlink() or path.stat().st_size > 32 * 1024**2:
            raise ValueError('Invalid vendor shard')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Vendor shard changed')
        import gzip
        from io import BytesIO
        frame = pd.read_csv(BytesIO(gzip.decompress(raw)), keep_default_na=False)
        return frame[frame.sample_id.eq(sample_id)].to_dict('records')


def open_research_packet(directory, *, av_packet=None):
    """Select an explicit local format without changing production access."""
    if (Path(directory) / 'SOURCE_PERMISSION_MANIFEST.json').exists():
        if av_packet is not None:
            raise ValueError('Source permission reports are pinned in their manifest')
        from obsidiandroid.reporting.source_permission_research import SourcePermissionResearch
        return SourcePermissionResearch(directory)
    if (Path(directory) / 'ATLAS_MANIFEST.json').exists():
        if av_packet is not None:
            raise ValueError('Atlas source companions are pinned in its manifest')
        from obsidiandroid.reporting.research_atlas import ResearchAtlas
        return ResearchAtlas(directory)
    if (Path(directory) / 'PI_VIEW_MANIFEST.json').exists():
        from obsidiandroid.reporting.permission_research_view import PermissionResearchView
        view = PermissionResearchView(directory)
        return view.bind_av_packet(ResearchPacket(av_packet)) if av_packet is not None else view
    if av_packet is not None:
        raise ValueError('An AV companion requires a retained PI view')
    return ResearchPacket(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', required=True)
    parser.add_argument('--write-subset', help='New local PI packet directory; never overwrite')
    parser.add_argument('--identities', help='Exact sample_id, sha256, event_id, payload_hash CSV for subset export')
    parser.add_argument('--pi-cohort', help='Atlas cohort: original, named retained cohort, or combined')
    parser.add_argument('--av-packet', help='Optional exact-report-bound retained AV companion for a PI view')
    parser.add_argument('kind', choices=['overview', 'sample', 'family', 'type', 'permission', 'comparison', 'engine', 'overlap', 'export', 'association', 'structure', 'aliases'])
    parser.add_argument('value', nargs='?', default='')
    args = parser.parse_args()
    packet = open_research_packet(args.packet, av_packet=args.av_packet)
    if args.pi_cohort:
        if not hasattr(packet, 'select_pi_cohort'):
            parser.error('--pi-cohort requires an atlas')
        packet.select_pi_cohort(args.pi_cohort)
    if args.write_subset or args.identities:
        if not (args.write_subset and args.identities):
            parser.error('--write-subset and --identities must be supplied together')
        import csv
        identity_path = Path(args.identities)
        if identity_path.is_symlink() or identity_path.stat().st_size > 1024**2:
            parser.error('Invalid identity file bound')
        with identity_path.open() as stream:
            identities = list(csv.DictReader(stream))
        view = getattr(packet, 'pi', packet)
        if not hasattr(view, 'export_subset') or hasattr(view, 'cohort_sources'):
            parser.error('Subset export requires one retained PI packet, not combined cohorts')
        packet = view.export_subset(args.write_subset, identities)
    print(json.dumps(packet.describe(args.kind, args.value), indent=2))


if __name__ == '__main__':
    main()
