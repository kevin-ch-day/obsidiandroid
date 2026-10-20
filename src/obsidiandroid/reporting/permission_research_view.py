"""Checksum-bound local views of approved retained descriptive output only."""
import copy
import os
import tempfile
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from obsidiandroid.reporting.permission_descriptive_research import describe_permissions

FORMAT = 'obsidiandroid-retained-pi-view-v1'


class PermissionResearchView:
    """Browse an explicitly selected local packet; no production approval implied."""

    supports_permission_queries = True

    def __init__(self, directory):
        self.root = Path(directory).resolve()
        manifest_path = self.root / 'PI_VIEW_MANIFEST.json'
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 1024*1024:
            raise ValueError('Invalid view manifest')
        self.manifest = json.loads(manifest_path.read_text())
        self.manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if self.manifest.get('format') != FORMAT:
            raise ValueError('Unsupported permission view')
        self.used = 0
        self.samples = self._csv('COHORT_METADATA.csv')
        self.observations = self._csv('OBSERVATION_EVIDENCE.csv')
        for sample in self.samples:
            if (not re.fullmatch(r'[1-9][0-9]*', sample['sample_id']) or
                    not re.fullmatch(r'[0-9a-f]{64}', sample['sha256'])):
                raise ValueError('Invalid sample identity')
        if len({r['sha256'] for r in self.samples}) != len(self.samples):
            raise ValueError('Duplicate sample SHA')
        for row in self.observations:
            for key in ['accepted_identity', 'source_correspondence_verified', 'definition_source_present']:
                if row[key] not in {'True', 'False'}:
                    raise ValueError('Nonboolean evidence field')
                row[key] = row[key] == 'True'
            row['sample_id'], row['obs_id'] = int(row['sample_id']), int(row['obs_id'])
            row['protection_base'] = row['protection_base'] or None
            for key in ['history', 'interpretation', 'source', 'version_identity', 'abstentions', 'capabilities']:
                row[key] = json.loads(row[key])
            if row['version_identity'] != self.manifest['versions']:
                raise ValueError('Frozen classification version mismatch')
            for key in ['category', 'evidence_level', 'protection_base']:
                if key in row['interpretation'] and row[key] != row['interpretation'][key]:
                    raise ValueError('Contradictory retained classification interpretation')
            source = row['source']
            if ('match_state' in source and source['match_state'] != row['source_match_state']):
                raise ValueError('Contradictory source match state')
            if (row['source_correspondence_verified'] and 'raw_candidates' in source
                    and row['exact_token'] not in source['raw_candidates']):
                raise ValueError('Exact token absent from retained source correspondence')
            if (source['sample_id'], source['sha256']) != (row['sample_id'], row['sha256']):
                raise ValueError('Source identity mismatch')
            relationship = source.get('historical_relationship')
            if relationship == 'BOUND_ORIGINAL_EVENT':
                original = (row['history'].get('original_event_id'),
                            row['history'].get('original_payload_sha256'))
                event = (source.get('event_id'), source.get('payload_sha256'))
                if original != event or None in event:
                    raise ValueError('Unbound original history claim')
            elif relationship != 'LATEST_REPORT_CORRESPONDENCE_ONLY':
                raise ValueError('Unknown historical relationship')
            if row['source_correspondence_verified'] != (row['source_match_state'] == 'RAW_EXACT'):
                raise ValueError('Source verification state mismatch')
            if row['canonical_identity'] and not row['accepted_identity']:
                raise ValueError('Canonical acceptance mismatch')
        describe_permissions(self.observations, self.samples)
        if (len(self.samples), len(self.observations)) != (
                self.manifest['samples'], self.manifest['observations']):
            raise ValueError('Packet denominator mismatch')
        self.signatures = self._csv('LINEAGE_SIGNATURES.csv')
        self.av_packet = None

    def bind_av_packet(self, packet):
        """Attach an explicit AV snapshot only when every retained report binding agrees.

        Family labels and PI/export membership are never imported from this packet.
        Snapshot paths remain separate even when the underlying AV reports agree.
        """
        by_id = packet.samples.set_index('sample_id').to_dict('index')
        for member in self.samples:
            av = by_id.get(int(member['sample_id']))
            if av is None:
                raise ValueError('AV snapshot missing research sample')
            for key in ['sha256', 'event_id', 'payload_hash']:
                value = member.get(key)
                if not value or str(av.get(key, '')) != str(value):
                    raise ValueError('AV sample or retained report binding mismatch')
        self.av_packet = packet
        return self

    def require_identities(self, identities):
        """Require the complete exact ID/SHA/report allowlist, not an intersection."""
        def keys(rows):
            result = [tuple(str(r[k]) for k in ('sample_id', 'sha256', 'event_id', 'payload_hash')) for r in rows]
            if len({r[0] for r in result}) != len(result):
                raise ValueError('Duplicate allowlist identity')
            return set(result)
        if keys(self.samples) != keys(identities):
            raise ValueError('Retained cohort differs from exact identity allowlist')
        return self

    def export_subset(self, directory, identities):
        """Write a new validated subset of existing local evidence, never overwrite.

        No database/provider IO, approval service or classification changes. This
        cannot recover observations missing from the input evidence packet.
        """
        if hasattr(self, 'cohort_sources'):
            raise ValueError('Export one source cohort at a time to preserve version identity')
        ids = [str(r['sample_id']) for r in identities]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('Empty or duplicate subset allowlist')
        members = [m for m in self.samples if m['sample_id'] in set(ids)]
        candidate = copy.copy(self)
        candidate.samples = members
        candidate.require_identities(identities)
        rows = [r for r in self.observations if str(r['sample_id']) in set(ids)]
        target = Path(directory)
        if target.exists() or target.is_symlink():
            raise ValueError('Subset destination must be new')
        with tempfile.TemporaryDirectory(prefix='.pi-subset-', dir=target.parent) as temporary:
            stage = Path(temporary)
            for name, records, fields in [
                    ('COHORT_METADATA.csv', members, list(members[0])),
                    ('OBSERVATION_EVIDENCE.csv', rows, list(self.observations[0]) if self.observations else []),
                    ('LINEAGE_SIGNATURES.csv', [], ['family', 'permission', 'components'])]:
                with (stage/name).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows({k: json.dumps(v) if isinstance(v, (dict, list)) else v
                                      for k, v in row.items()} for row in records)
            manifest = dict(format=FORMAT, versions=self.manifest['versions'],
                samples=len(members), observations=len(rows),
                source_packet=dict(path=str(self.root), sha256=self.manifest_sha256),
                files={q.name: hashlib.sha256(q.read_bytes()).hexdigest() for q in stage.iterdir()})
            (stage/'PI_VIEW_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
            PermissionResearchView(stage).require_identities(identities)
            # mkdir is exclusive; a concurrent creator cannot be overwritten.
            target.mkdir()
            try:
                for item in stage.iterdir():
                    os.rename(item, target/item.name)
            except BaseException:
                import shutil
                shutil.rmtree(target)
                raise
        return PermissionResearchView(target)

    @classmethod
    def combine(cls, views):
        """Pool disjoint validated local cohorts with compatible interpretations."""
        if len(views) < 2:
            raise ValueError('Combined view requires at least two cohorts')
        comparable = lambda v: {k: value for k, value in v.manifest['versions'].items()
                                if k != 'source_index_sha256'}
        if any(comparable(v) != comparable(views[0]) for v in views[1:]):
            raise ValueError('Incompatible classification or interpretation versions')
        result = copy.copy(views[0])
        result.samples = [m for view in views for m in view.samples]
        result.observations = [r for view in views for r in view.observations]
        if len({m['sha256'] for m in result.samples}) != len(result.samples):
            raise ValueError('Overlapping cohort SHA identities')
        describe_permissions(result.observations, result.samples)
        result.signatures = []  # Use structure view; old per-cohort summaries cannot be pooled.
        result.manifest = dict(versions=dict(cohorts=[v.manifest['versions'] for v in views]))
        result.manifest_sha256 = hashlib.sha256(json.dumps(
            [v.manifest_sha256 for v in views]).encode()).hexdigest()
        result.cohort_sources = [dict(path=str(v.root), sha256=v.manifest_sha256,
                                     samples=len(v.samples), observations=len(v.observations)) for v in views]
        return result

    @staticmethod
    def _modalities(members, rows):
        """Compare retained modalities, without implying feature/training eligibility."""
        accepted = {r['sample_id'] for r in rows
                    if r['accepted_identity'] and r['source_correspondence_verified']}
        observed = {r['sample_id'] for r in rows}
        av = {int(m['sample_id']) for m in members
              if m.get('av_state') == 'VALIDATED_RETAINED_REPORT'}
        unknown = sum(not m.get('av_state') for m in members)
        return [dict(modality=name, samples=count, sample_denominator=len(members),
                     missing_av_state_samples=unknown, training_authorized=False)
                for name, count in [
                    ('Retained AV report', len(av)),
                    ('PI observation', len(observed)),
                    ('Accepted PI with exact source correspondence', len(accepted)),
                    ('Retained AV and accepted exact PI', len(av & accepted)),
                    ('Retained AV without accepted exact PI', len(av - accepted)),
                    ('Accepted exact PI without validated AV report', len(accepted - av))]]

    @staticmethod
    def _permission_totals(members, rows):
        """Pool selected samples without averaging family percentages."""
        positives = defaultdict(set)
        for row in rows:
            if row['accepted_identity'] and row['source_correspondence_verified']:
                positives[row['canonical_identity']].add(row['sample_id'])
        groups = {m.get('lineage_component') for m in members if m.get('lineage_component')}
        families = {m['family'] for m in members}
        result = []
        for token, ids in positives.items():
            positive = [m for m in members if int(m['sample_id']) in ids]
            result.append(dict(
                permission=token, samples=len(ids), sample_denominator=len(members),
                prevalence=len(ids) / len(members),
                represented_families=len({m['family'] for m in positive}),
                family_denominator=len(families),
                common_across_selected_families={m['family'] for m in positive} == families,
                positive_inferred_components=len({m['lineage_component'] for m in positive
                                                  if m.get('lineage_component')}),
                inferred_component_denominator=len(groups),
                missing_lineage_samples=sum(not m.get('lineage_component') for m in members)))
        return sorted(result, key=lambda row: (-row['samples'], row['permission']))

    def _csv(self, name):
        path = self.root / name
        if path.is_symlink() or path.stat().st_size > 64*1024**2:
            raise ValueError('Invalid view file')
        raw = path.read_bytes()
        self.used += len(raw)
        if self.used > 128*1024**2 or hashlib.sha256(raw).hexdigest() != self.manifest['files'][name]:
            raise ValueError('View hash or size mismatch')
        return list(csv.DictReader(io.StringIO(raw.decode())))

    def describe(self, kind='overview', value=''):
        """Use exact denominators and surface uncertainty beside observed frequencies."""
        members = self.samples
        if kind == 'family':
            members = [m for m in members if m['family'].casefold() == value.casefold()]
        elif kind == 'type':
            members = [m for m in members if m['malware_type'].casefold() == value.casefold()]
        elif kind == 'sample':
            members = [m for m in members if m['sample_id'] == str(value) or m['sha256'] == str(value).lower()]
        elif kind not in {'overview', 'permission', 'comparison'}:
            raise ValueError('Unsupported descriptive operation')
        ids = {int(m['sample_id']) for m in members}
        rows = [r for r in self.observations if r['sample_id'] in ids]
        tables = describe_permissions(rows, members) if members else {'prevalence': [], 'temporal': []}
        # A permission query retains the full cohort denominator, including zeros.
        query = str(value)
        if kind == 'permission':
            tables = {key: [r for r in tables[key] if r['permission'] == query]
                      for key in ['prevalence', 'temporal']}
            rows = [r for r in rows if r['canonical_identity'] == query or r['exact_token'] == query]
        profile = sorted((r for r in tables['prevalence'] if r['samples']),
                         key=lambda r: (-r['prevalence'], r['family'], r['permission']))
        unresolved = [dict(obs_id=r['obs_id'], sample_id=r['sample_id'], token=r['exact_token'],
                           status=r['resolution_status'], source=r['source_match_state']) for r in rows
                      if r['resolution_status'] == 'UNRESOLVED' or not r['source_correspondence_verified']]
        dimensions = []
        for key in ['category', 'evidence_level', 'resolution_status', 'protection_base']:
            for value, count in sorted(Counter(r[key] or 'UNKNOWN' for r in rows).items()):
                dimensions.append(dict(dimension=key, value=value, observations=count,
                                       observation_denominator=len(rows)))
        full_families = {f for f in {m['family'] for m in members}
                         if sum(m['family'] == f for m in members) == sum(m['family'] == f for m in self.samples)}
        result = dict(evidence='Retained offline observations; not runtime behavior or independent family proof',
                    packet_path=str(self.root), manifest_sha256=self.manifest_sha256,
                    classification_versions=self.manifest['versions'],
                    permission_query=query if kind == 'permission' else None,
                    permission_comparison=tables['prevalence'] if kind in {'permission', 'comparison'} else [],
                    samples=len(members), observations=len(rows), training_authorized=False,
                    production_authorized=False, governed_capabilities='Unavailable; candidate mappings are not governed definitions',
                    permission_consumer_availability={'mode': 'RETAINED_OFFLINE_ONLY',
                                                     'exact_source_observations': sum(r['source_correspondence_verified'] for r in rows),
                                                     'projection_abstentions': sum(not r['source_correspondence_verified'] for r in rows),
                                                     'original_historical_event_bound': sum(r['source']['historical_relationship'] == 'BOUND_ORIGINAL_EVENT' for r in rows)},
                    permission_profile=profile, authority_and_protection=dimensions,
                    unresolved_evidence=unresolved, temporal_permissions=tables['temporal'],
                    lineage_signatures=[r for r in self.signatures if r['family'] in full_families],
                    lineage_note='Inferred components; family bootstrap ranges are sensitivity, not population confidence',
                    families=dict(Counter(m['family'] for m in members)),
                    types=dict(Counter(m['malware_type'] for m in members)),
                    sources=dict(Counter(m['source_batch_label'] or 'Unavailable' for m in members)),
                    label_authority=dict(Counter(m['authority_version'] for m in members)),
                    vendor_family_relationships=dict(Counter(m['plurality_family'] or 'No unique plurality' for m in members)),
                    first_submission_months=dict(sorted(Counter(m['first_submission_month'] for m in members if m['temporal_eligible']=='True').items())),
                    records=members if kind=='sample' else [])
        result['cohort_sources'] = getattr(self, 'cohort_sources', [dict(path=str(self.root), sha256=self.manifest_sha256)])
        result['modality_comparison'] = self._modalities(members, rows) if kind != 'permission' else []
        result['permission_totals'] = self._permission_totals(members, rows)
        if kind == 'permission':
            result['lineage_signatures'] = [r for r in result['lineage_signatures']
                                            if r.get('permission') == query]
        result['temporal_eligible_samples'] = sum(m['temporal_eligible'] == 'True' for m in members)
        result['temporal_excluded_samples'] = len(members) - result['temporal_eligible_samples']
        result['source_missing_samples'] = sum(not m['source_batch_label'] for m in members)
        vendor_counts = [int(m['distinct_known_families']) for m in members
                         if str(m.get('distinct_known_families', '')).isdecimal()]
        result['vendor_disagreement_evidence_samples'] = len(vendor_counts)
        result['vendor_disagreement_unavailable_samples'] = len(members) - len(vendor_counts)
        result['vendor_conflicting_samples'] = sum(n > 1 for n in vendor_counts) if vendor_counts else None
        result['vendor_evidence'] = [
            dict(sample_id=m['sample_id'], state=m.get('av_state') or 'UNAVAILABLE',
                 retained_vendor_records=m.get('retained_vendor_records') or None,
                 known_family_votes=m.get('known_family_votes') or None,
                 distinct_known_families=m.get('distinct_known_families') or None,
                 plurality_family=m.get('plurality_family') or None,
                 label_basis=m.get('authority_basis') or 'UNAVAILABLE')
            for m in members] if kind == 'sample' else []
        if self.av_packet is not None:
            result['av_evidence_source'] = str(self.av_packet.root)
            result['av_manifest_sha256'] = getattr(self.av_packet, 'manifest_sha256', None)
            result['av_join_basis'] = 'Exact sample ID/SHA, retained report event and payload hash; labels not merged'
            if kind == 'sample' and len(members) == 1:
                result['vendor_claims'] = self.av_packet.vendor_claims(int(members[0]['sample_id']))
        result['permission_evidence'] = [
            {key: r[key] for key in ['sample_id', 'obs_id', 'exact_token', 'canonical_identity',
                                    'accepted_identity', 'category', 'evidence_level', 'protection_base',
                                    'definition_source_present', 'source', 'history', 'interpretation',
                                    'version_identity', 'abstentions']}
            for r in rows] if kind in {'sample', 'permission'} else []
        result['capability_interpretations'] = [
            dict(permission=token, candidate=capability, status='CANDIDATE_NOT_APPROVED',
                 governed_definition='UNAVAILABLE', runtime_behavior='NOT_ESTABLISHED')
            for token, capability in sorted({(r['canonical_identity'] or r['exact_token'], capability)
                                            for r in rows for capability in r['capabilities']})]
        result['comparison_readiness'] = {
            'training_authorized': False, 'untouched_evaluation': 'NOT_ESTABLISHED',
            'source_independence': 'NOT_ESTABLISHED',
            'label_authority': 'Retained family attribution; not independent ground truth',
            'partition_requirement': 'Same ID/SHA-bound population and lineage/source-isolated partitions for all modalities',
            'feature_requirement': 'Training-only vocabulary and selection; unavailable PI is never zero',
            'evaluation_requirement': 'Fixed label universe macro-F1; disclose AV-label circularity and first-submission proxy limits',
        }
        return result
