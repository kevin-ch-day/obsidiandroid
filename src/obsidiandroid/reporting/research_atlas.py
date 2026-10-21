"""Catalog AV comparisons composed with separately authorized retained PI views.

No live source adapter or model execution. Every denominator names its population.
"""
from collections import Counter
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path

import pandas as pd

from obsidiandroid.reporting.integrated_research import ResearchPacket, attribution_relationship
from obsidiandroid.reporting.permission_research_view import PermissionResearchView

FORMAT = 'obsidiandroid-research-atlas-v1'
CATEGORIES = {'malicious', 'suspicious', 'undetected', 'harmless', 'timeout',
              'confirmed_timeout', 'failure', 'type_unsupported'}


def checked_bytes(path, digest, limit=64 * 1024**2):
    """Read a bounded immutable evidence object, never executable content."""
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError('Invalid atlas evidence bound or symlink')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Atlas evidence digest mismatch')
    return raw


def engine_key(name):
    """Conservative compatibility spelling, not verified shared vendor ownership."""
    return str(name).strip().casefold().replace('-', '_')


class ResearchAtlas:
    """Existing research views plus bounded, lazy catalog vendor aggregation."""

    supports_permission_queries = True
    supports_engine_queries = True

    def __init__(self, directory):
        self.root = Path(directory).resolve()
        path = self.root / 'ATLAS_MANIFEST.json'
        if path.is_symlink() or path.stat().st_size > 1024**2:
            raise ValueError('Invalid atlas manifest')
        raw = path.read_bytes()
        self.manifest_sha256 = hashlib.sha256(raw).hexdigest()
        self.manifest = json.loads(raw)
        if self.manifest.get('format') != FORMAT:
            raise ValueError('Unsupported atlas format')
        for key, name in [('av', 'RESEARCH_MANIFEST.json'), ('pi', 'PI_VIEW_MANIFEST.json')]:
            entry = self.manifest[key]
            checked_bytes(Path(entry['path']) / name, entry['sha256'], 32 * 1024**2)
        self.av = ResearchPacket(self.manifest['av']['path'])
        for field in ['event_id','payload_hash']:
            if field not in self.av.samples or self.av.samples[field].eq('').any():
                raise ValueError('Selected report identity unavailable')
        if self.av.samples.event_id.duplicated().any():
            raise ValueError('Repeated selected report event')
        self.pi = PermissionResearchView(self.manifest['pi']['path']).bind_av_packet(self.av)
        self.pi_cohorts = {'original': self.pi}
        for name, entry in self.manifest.get('pi_cohorts', {}).items():
            if name in {'original', 'combined'} or not name:
                raise ValueError('Reserved or empty PI cohort name')
            checked_bytes(Path(entry['path']) / 'PI_VIEW_MANIFEST.json', entry['sha256'])
            view = PermissionResearchView(entry['path']).bind_av_packet(self.av)
            identities = pd.read_csv(BytesIO(checked_bytes(entry['identities']['path'],
                entry['identities']['sha256'])), keep_default_na=False).to_dict('records')
            self.pi_cohorts[name] = view.require_identities(identities)
        self.pi_cohort_name = 'original'
        self.source = None
        if 'source' in self.manifest:
            entry = self.manifest['source']
            self.source = Path(entry['path'])
            raw = checked_bytes(self.source / 'SOURCE_MANIFEST.json', entry['sha256'])
            if entry['sha256'] != self.av.manifest['source_manifest_sha256']:
                raise ValueError('AV source manifest binding mismatch')
            self.source_manifest = json.loads(raw)
        self.coverage = None
        if 'coverage' in self.manifest:
            entry = self.manifest['coverage']
            self.coverage = pd.read_csv(BytesIO(checked_bytes(entry['path'], entry['sha256'])), keep_default_na=False)
            pairs = set(zip(self.av.samples.sample_id, self.av.samples.sha256))
            if (len(self.coverage) != len(pairs) or self.coverage.sample_id.duplicated().any() or
                    set(zip(self.coverage.sample_id,self.coverage.sha256)) != pairs):
                raise ValueError('Coverage audit identity mismatch')
        self.source_context = {}
        if 'source_context' in self.manifest:
            from .source_context import load_context
            entry = self.manifest['source_context']
            self.source_context = load_context(checked_bytes(entry['path'], entry['sha256'], 4 * 1024**2),
                                               self.av.samples.to_dict('records'))
        self._vendors = None
        self._pi_comparison = None
        self._intelligence = None
        self.interpretation_pin = self.manifest.get('vendor_interpretation')
        if self.interpretation_pin is not None:
            from obsidiandroid.vendors.interpretation_quality import source_identity
            if self.interpretation_pin != source_identity():
                raise ValueError('Vendor interpretation source/version mismatch')

    def select_pi_cohort(self, name):
        """Select original, a named retained cohort, or a compatible combined view."""
        if name == 'combined':
            selected = PermissionResearchView.combine(list(self.pi_cohorts.values())).bind_av_packet(self.av)
        elif name in self.pi_cohorts:
            selected = self.pi_cohorts[name]
        else:
            raise ValueError('PI cohort unavailable: no validated retained packet supplied')
        self.pi = selected
        self.pi_cohort_name = name
        self._pi_comparison = None
        return self

    def _load_vendors(self):
        if self._vendors is not None:
            return self._vendors
        entries = self.av.manifest['vendor_shards']
        ids = set(map(int, self.av.samples.sample_id))
        if set(map(int, entries)) != ids or len(ids) > 100000:
            raise ValueError('Incomplete or oversized vendor index')
        paths = {}
        for sid, entry in entries.items():
            key = (entry['path'], entry['sha256'])
            paths.setdefault(key, set()).add(int(sid))
        frames, total = [], 0
        for (path, digest), expected in sorted(paths.items()):
            raw = checked_bytes(path, digest, 32 * 1024**2)
            with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                decoded = stream.read(64 * 1024**2 + 1)
            if len(decoded) > 64 * 1024**2:
                raise ValueError('Decoded vendor shard exceeds bound')
            frame = pd.read_csv(BytesIO(decoded), keep_default_na=False)
            required = {'sample_id', 'engine', 'category', 'raw_label', 'family',
                        'known_family', 'parser_quality', 'parser_error'}
            if not required <= set(frame) or set(frame.sample_id) != expected:
                raise ValueError('Vendor shard identity membership mismatch')
            if frame.duplicated(['sample_id', 'engine']).any():
                raise ValueError('Repeated selected report engine verdict')
            if (not frame.category.isin(CATEGORIES).all() or
                    not frame.known_family.map(lambda x: type(x) is bool).all() or
                    frame.engine.eq('').any()):
                raise ValueError('Unsupported vendor evidence')
            if frame.groupby('sample_id').size().gt(256).any():
                raise ValueError('Per-report engine bound exceeded')
            total += len(frame)
            if total > 256 * len(ids):
                raise ValueError('Verdict population exceeds bound')
            frames.append(frame)
        frame = pd.concat(frames, ignore_index=True)
        frame['engine_key'] = frame.engine.map(engine_key)
        for col in frame.columns:
            if col not in {'sample_id', 'known_family'}:
                frame[col] = frame[col].astype('category')
        self._vendors = frame
        return frame

    def _load_intelligence(self):
        """Layer explanations over frozen verdicts without replacing their columns."""
        if self.interpretation_pin is None:
            raise ValueError('Version-pinned vendor interpretation unavailable')
        if self._intelligence is not None:
            return self._intelligence
        from obsidiandroid.vendors.interpretation_quality import interpret
        rows = self._load_vendors()
        keys = ['engine','raw_label','family','known_family']
        names = set(self.av.samples.recorded_family.str.casefold()) - {'unknown','other',''}
        rules = []
        for values in rows[keys].drop_duplicates().itertuples(index=False, name=None):
            explanation = interpret(*values, catalog_names=names)
            rules.append(dict(zip(keys, values), interpretation_state=explanation['state'],
                interpretation_reason=explanation['reason'], active_family=explanation['family'] or '',
                active_recognized=explanation['recognized'], corrected=explanation['corrected']))
        frame = rows.merge(pd.DataFrame(rules), on=keys, validate='many_to_one', sort=False)
        for col in ['interpretation_state','interpretation_reason','active_family']:
            frame[col] = frame[col].astype('category')
        self._intelligence = frame
        return frame

    def vendor_intelligence(self, kind='overview', value=''):
        """Compare old/new recognized interpretations with explicit verdict denominators."""
        rows = self._load_intelligence()
        members = self._scope(kind,value)
        rows = rows[rows.sample_id.isin(members.sample_id)]
        if kind == 'engine':
            rows = rows[rows.engine.eq(value)] if rows.engine.eq(value).any() else rows[rows.engine_key.eq(engine_key(value))]
        before = rows[rows.known_family.eq(True)].groupby('sample_id',observed=True).family.nunique()
        after = rows[rows.active_recognized.eq(True)].groupby('sample_id',observed=True).active_family.nunique()
        old_conflicts, new_conflicts = set(before[before>1].index), set(after[after>1].index)
        counts = rows.interpretation_state.value_counts()
        nonempty = rows.raw_label.ne('')
        summary = dict(policy=self.interpretation_pin['policy'], verdict_denominator=len(rows),
            sample_denominator=len(members), nonempty_label_verdicts=int(nonempty.sum()),
            distinct_nonempty_raw_labels=int(rows.loc[nonempty,'raw_label'].nunique()),
            recognized_verdicts_before=int(rows.known_family.sum()), recognized_verdicts_after=int(rows.active_recognized.sum()),
            recognized_samples_before=len(before), recognized_samples_after=len(after),
            corrected_interpretations=int(rows.corrected.sum()), lost_recognized_verdicts=int((rows.known_family & ~rows.active_recognized).sum()),
            conflicting_samples_before=len(old_conflicts), conflicting_samples_after=len(new_conflicts),
            newly_conflicting_samples=len(new_conflicts-old_conflicts), resolved_conflicting_samples=len(old_conflicts-new_conflicts),
            detected_verdicts=int(rows.category.isin(['malicious','suspicious']).sum()),
            detection_fraction_of_observed_verdicts=float(rows.category.isin(['malicious','suspicious']).mean()) if len(rows) else None,
            threat_type_unresolved_verdicts=int(rows.malware_type.isin(['unknown','']).sum()) if 'malware_type' in rows else None,
            generic_policy='Conservative reviewed patterns only; C is not proof of a family-bearing label',
            report_identity_basis='One pinned selected event/payload per sample; distinct samples equal distinct selected reports')
        outcomes=[dict(outcome=str(k),verdicts=int(v),verdict_denominator=len(rows)) for k,v in counts.items() if v]
        fields=['engine','raw_label','family','active_family','interpretation_state','interpretation_reason']
        labels=rows[nonempty].groupby(fields, observed=True).agg(verdicts=('sample_id','size'), samples=('sample_id','nunique'), example_sample_id=('sample_id','first')).reset_index()
        labels=labels.sort_values(['samples','verdicts'],ascending=False).head(100)
        source=self.av.samples.set_index('sample_id')
        review=[]
        for row in labels.to_dict('records'):
            sample=source.loc[row['example_sample_id']]
            row.update(distinct_selected_reports=row['samples'],example_catalog_family=sample.recorded_family,
                       example_catalog_relationship=attribution_relationship(row['active_family'],sample.recorded_family),
                       example_sha256=sample.sha256,
                       example_event_id=int(sample.event_id),example_payload_hash=sample.payload_hash)
            review.append(row)
        return dict(vendor_intelligence_summary=summary, interpretation_outcomes=outcomes,
                    vendor_label_review=review, vendor_review_limit=100,
                    vendor_interpretation_sources=self.interpretation_pin,
                    vendor_review_note='100 most frequent labels in selected scope; exact raw and frozen family retained alongside new interpretation. Catalog agreement is not independent truth.')

    def _scope(self, kind, value):
        samples = self.av.samples
        if kind in {'family', 'type'}:
            key = 'recorded_family' if kind == 'family' else 'malware_type'
            return samples[samples[key].str.casefold().eq(str(value).casefold())]
        if kind == 'sample':
            return samples[samples.sample_id.eq(int(value))] if str(value).isdigit() else samples[samples.sha256.eq(str(value).lower())]
        return samples

    def _av_summary(self, kind, value):
        all_rows = self._load_vendors()
        members = self._scope(kind, value)
        rows = all_rows[all_rows.sample_id.isin(members.sample_id)]
        if kind == 'engine':
            # Exact raw spelling first; a compatibility key may name several raw spellings.
            exact = all_rows.engine.eq(str(value))
            rows = rows[rows.engine.eq(str(value))] if exact.any() else rows[rows.engine_key.eq(engine_key(value))]
        engine_universe = sorted(map(str, all_rows.engine.unique()))
        counts = rows.groupby('sample_id', observed=True).size()
        categories = rows.category.value_counts().to_dict()
        category_rows = [dict(category=k, verdicts=int(v), verdict_denominator=len(rows)) for k, v in categories.items() if v]
        raw_claims = rows[rows.raw_label.ne('')].groupby(['engine', 'raw_label'], observed=True).size().sort_values(ascending=False)
        known = rows[rows.known_family.eq(True)]
        claims = known.groupby(['engine', 'family'], observed=True).size().sort_values(ascending=False)
        canonical = members.set_index('sample_id').recorded_family.to_dict()
        relationships = Counter(attribution_relationship(r.family, canonical[r.sample_id]) for r in known.itertuples())
        engine_rows = []
        for engine, group in rows.groupby('engine', observed=True):
            n = group.sample_id.nunique()
            engine_rows.append(dict(engine=str(engine), compatibility_key=engine_key(engine), samples=int(n),
                sample_denominator=len(members), missing_engine_samples=len(members)-int(n),
                categories={str(k):int(v) for k,v in group.category.value_counts().items() if v},
                recognized_family_verdicts=int(group.known_family.sum()),
                nonempty_unrecognized_labels=int((group.raw_label.ne('') & ~group.known_family).sum()),
                parser_quality={str(k):int(v) for k,v in group.parser_quality.value_counts().items() if v},
                empty_raw_labels=int(group.raw_label.eq('').sum())))
        # Report every family within scope, including zero recognized votes.
        family_rows = []
        for family, group in members.groupby('recorded_family', sort=True):
            subset = rows[rows.sample_id.isin(group.sample_id)]
            votes = subset[subset.known_family.eq(True)].groupby('sample_id', observed=True).family.nunique()
            family_rows.append(dict(family=family, samples=len(group), eligible_report_samples=int(subset.sample_id.nunique()),
                verdicts=len(subset), recognized_claim_samples=len(votes), conflicting_claim_samples=int((votes>1).sum()),
                no_recognized_claim_samples=len(group)-len(votes),
                missing_source_batch_samples=int(group.source_batch_label.eq('').sum()),
                inferred_lineage_components=int(group.lineage_component.nunique()) if 'lineage_component' in group else None,
                first_submission_periods=int(group.loc[group.temporal_eligible.eq(True),'first_submission_month'].nunique()),
                categories={str(k):int(v) for k,v in subset.category.value_counts().items() if v},
                detected_samples=int(subset.loc[subset.category.isin(['malicious','suspicious']), 'sample_id'].nunique()),
                detection_fraction=float(subset.loc[subset.category.isin(['malicious','suspicious']), 'sample_id'].nunique()/len(group))))
        strata = []
        detected = set(rows.loc[rows.category.isin(['malicious','suspicious']), 'sample_id'])
        for dimension in ['source_batch_label', 'first_submission_month']:
            labels = members.set_index('sample_id')[dimension].replace('', 'UNAVAILABLE')
            if dimension == 'first_submission_month':
                labels.loc[members.loc[~members.temporal_eligible.eq(True),'sample_id']] = 'UNAVAILABLE'
            grouped = rows.assign(stratum=rows.sample_id.map(labels)).groupby(['stratum','category'], observed=True).size()
            for label, group in members.assign(stratum=members.sample_id.map(labels)).groupby('stratum'):
                cats = grouped.loc[label].to_dict() if label in grouped.index.get_level_values(0) else {}
                strata.append(dict(dimension=dimension, stratum=label, samples=len(group),
                    sample_denominator=len(members), contributing_families=int(group.recorded_family.nunique()),
                    retained_result_samples=int(group.sample_id.isin(counts.index).sum()),
                    detected_samples=int(group.sample_id.isin(detected).sum()),
                    categories={str(k):int(v) for k,v in cats.items() if v}))
        return dict(population='CATALOG_RETAINED_AV', samples=len(members), retained_report_samples=int(counts.size),
            verdicts=len(rows), raw_engine_names=len(engine_universe),
            compatibility_engine_keys=int(all_rows.engine_key.nunique()),
            normalization_note='Case/whitespace/hyphen compatibility only; raw names preserved, aliases not merged',
            report_selection='One frozen selected latest successful retained report per sample; not report time series',
            equal_family_detection_fraction=sum(f['detection_fraction'] for f in family_rows)/len(family_rows) if family_rows else None,
            family_stratum_denominator=len(family_rows),
            av_strata=strata,
            category_counts=category_rows, engine_coverage=engine_rows, family_av=family_rows,
            parser_quality_counts={str(k):int(v) for k,v in rows.parser_quality.value_counts().items() if v},
            recognized_family_verdicts=len(known),
            nonempty_unrecognized_labels=int((rows.raw_label.ne('') & ~rows.known_family).sum()),
            empty_raw_labels=int(rows.raw_label.eq('').sum()),
            engine_observations_min=int(counts.min()) if len(counts) else None,
            engine_observations_max=int(counts.max()) if len(counts) else None,
            complete_global_engine_universe_samples=int((counts==len(engine_universe)).sum()),
            coverage_note='Global raw-engine universe is descriptive; absent engines are missing, not undetected or expected to support every sample',
            raw_claims=[dict(engine=str(e),raw_label=str(l),verdicts=int(n)) for (e,l),n in raw_claims.items()],
            normalized_claims=[dict(engine=str(e),family=str(f),verdicts=int(n)) for (e,f),n in claims.items()],
            canonical_relationships=dict(relationships),
            agreement_note='Recognized parser claims versus retained taxonomy, not independent truth or detector quality',
            generic_note='Nonempty unrecognized labels include generic and unparsed specific labels; no fabricated generic classification',
            families=members.recorded_family.value_counts().to_dict(),
            types=members.malware_type.value_counts().to_dict(),
            label_authority=members.authority_basis.value_counts().to_dict() if 'authority_basis' in members else {},
            source_missing_samples=int(members.source_batch_label.eq('').sum()),
            inferred_lineage_components=int(members.lineage_component.nunique()) if 'lineage_component' in members else None,
            lineage_note='Retained whole-catalog and PI lineage policies differ; neither proves independent acquisition',
            temporal_excluded_samples=int((~members.temporal_eligible.eq(True)).sum()),
            sources=members.source_batch_label.replace('', 'UNAVAILABLE').value_counts().to_dict(),
            first_submission_months=members.loc[members.temporal_eligible.eq(True),'first_submission_month'].value_counts().sort_index().to_dict())

    def _raw_sample(self, member):
        if self.source is None:
            return {'state':'UNAVAILABLE', 'reason':'No hash-bound raw source companion selected'}
        sid, sha = int(member['sample_id']), member['sha256']
        # Scan bounded chunks, preserving exact source identity rather than guessing from shard names.
        for entry in self.source_manifest['chunks']:
            relative = Path(entry['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Source chunk escapes packet')
            compressed = checked_bytes(self.source/relative, entry['sha256'])
            with gzip.GzipFile(fileobj=BytesIO(compressed)) as stream:
                raw = stream.read(64*1024**2+1)
            if len(raw)>64*1024**2 or len(raw)!=entry['json_bytes']:
                raise ValueError('Source decoded bound mismatch')
            chunk = json.loads(raw)
            selected = [m for m in chunk['members'] if m['sample_id']==sid]
            if not selected:
                continue
            reports = [r for r in chunk['reports'] if r['sha256']==sha]
            if len(selected)!=1 or selected[0]['sha256']!=sha or len(reports)!=1:
                raise ValueError('Raw report membership mismatch')
            report = reports[0]
            if (str(report['event_id'])!=str(member['event_id']) or report['payload_hash']!=member['payload_hash'] or
                    hashlib.sha256(report['payload_json'].encode()).hexdigest()!=member['payload_hash']):
                raise ValueError('Raw report source binding mismatch')
            data = json.loads(report['payload_json'])['data']
            attrs = data['attributes']
            if data['id']!=sha or attrs.get('sha256')!=sha:
                raise ValueError('Raw report SHA mismatch')
            verdicts = attrs['last_analysis_results']
            retained = self.av.vendor_claims(sid)
            if set(verdicts) != {r['engine'] for r in retained} or any(
                    str(verdicts[r['engine']].get('category','')).replace('-','_') != r['category'] or
                    (verdicts[r['engine']].get('result') or '') != r['raw_label'] for r in retained):
                raise ValueError('Raw and parsed verdict source mismatch')
            return dict(state='EXACT_RETAINED_REPORT', event_id=report['event_id'], payload_hash=report['payload_hash'],
                fetched_at_utc=member.get('fetched_at_utc'), last_analysis_date=attrs.get('last_analysis_date'),
                engines=[dict(raw_engine=e, **{k:v.get(k) for k in ['engine_name','engine_version','engine_update','category','result','method']})
                         for e,v in attrs['last_analysis_results'].items()])
        raise ValueError('Raw sample source unavailable')

    def describe(self, kind='overview', value=''):
        """Keep catalog, PI and exact-overlap results in explicitly separate views."""
        if kind not in {'overview','engine','family','type','sample','permission','comparison','overlap','export','association','structure'}:
            raise ValueError('Unsupported atlas view')
        if kind == 'export':
            result = self.av.describe('overview')
            result['population'] = 'PRIOR_APPROVED_EXPORT_MEMBERSHIP_IN_CATALOG'
            result['governed_pi_joined'] = False
            return result
        result = dict(evidence='Retained descriptive atlas; no runtime or independent target proof',
            manifest_sha256=self.manifest_sha256, av_manifest_sha256=self.av.manifest_sha256,
            pi_manifest_sha256=self.pi.manifest_sha256, training_authorized=False, production_authorized=False,
            permission_consumer_availability={'mode':'RETAINED_OFFLINE_ONLY','catalog_samples':len(self.av.samples),
                'governed_pi_samples':len(self.pi.samples),'governed_pi_observations':len(self.pi.observations),
                'other_catalog_pi_state':'UNAVAILABLE through this governed view; not zero upstream observations'},
            classification_versions=self.pi.manifest['versions'])
        from .source_context import summarize_context
        context = list(self.source_context.values())
        selected = context
        if kind == 'family':
            selected = [r for r in context if r['family'].casefold() == value.casefold()]
        elif kind == 'sample':
            selected = [r for r in context if str(r['sample_id']) == value or r['sha256'] == value]
        elif kind == 'type':
            type_ids = set(map(str, self.av.samples.loc[
                self.av.samples.malware_type.str.casefold().eq(str(value).casefold()), 'sample_id']))
            selected = [r for r in context if str(r['sample_id']) in type_ids]
        result['research_readiness'] = dict(
            admitted_population='RETAINED_DESCRIPTIVE', admitted_samples=len(self.pi.samples),
            selected_cohort=self.pi_cohort_name,
            available_cohorts=list(self.pi_cohorts),
            expansion='Additional PI evidence requires an exact source-bound retained packet',
            replication='NOT_ESTABLISHED; source-independent same-family identities required',
            source_context=summarize_context(selected), training_authorized=False)
        result['pi_cohort_sources'] = [dict(name=name, samples=len(view.samples),
            observations=len(view.observations), path=str(view.root),
            manifest_sha256=view.manifest_sha256, versions=view.manifest['versions'])
            for name, view in self.pi_cohorts.items()
            if self.pi_cohort_name == 'combined' or name == self.pi_cohort_name]
        if kind in {'family', 'sample'}:
            result['source_context_records'] = selected
        if kind == 'structure':
            from .permission_structure import describe_structure
            result.update(describe_structure(self.pi.samples, self.pi.observations))
            return result
        if kind == 'association':
            from .permission_associations import compare_permission
            result.update(compare_permission(self.pi.samples, self.pi.observations,
                                             self._load_intelligence(), value))
            result['vendor_interpretation'] = self.interpretation_pin
            return result
        if kind in {'overview','engine','family','type','sample'}:
            result.update(self._av_summary(kind,value))
        if kind in {'permission','comparison','overlap','export'}:
            pi = self.pi.describe('comparison' if kind=='overlap' else kind,value)
        elif kind in {'family','type','sample'}:
            pi = self.pi.describe(kind,value)
        else:
            pi = self.pi.describe('overview')
        result['pi_population'] = dict(scope='AUTHORIZED_RETAINED_PI_EXACT_AV_REPORT_OVERLAP',samples=pi['samples'],
                                      observations=pi['observations'], **pi['permission_consumer_availability'])
        for key in ['permission_comparison','permission_totals','authority_and_protection','temporal_permissions',
                    'lineage_signatures','unresolved_evidence','comparison_readiness']:
            result[key] = pi.get(key,[])
        if self._pi_comparison is None:
            self._pi_comparison = self.pi.describe('comparison')['permission_comparison']
        families = set(pi['families'])
        # Family and type views have already narrowed their PI membership. The
        # full-cohort table would silently include other types in a family.
        comparison = pi['permission_comparison'] if kind in {'family', 'type'} else self._pi_comparison
        strata = [r for r in comparison if r['family'] in families
                  and (kind != 'permission' or r['permission'] == str(value))]
        if kind != 'sample':
            result['permission_comparison'] = strata
            for row in result['permission_totals']:
                rates = [r['prevalence'] for r in strata if r['permission'] == row['permission']]
                row['equal_family_prevalence'] = sum(rates)/len(rates) if rates else None
                row['equal_family_denominator'] = len(rates)
        result['pi_source_missing_samples'] = pi['source_missing_samples']
        result['pi_temporal_excluded_samples'] = pi['temporal_excluded_samples']
        if kind in {'permission','comparison','overlap','export'}:
            result['population']='AUTHORIZED_RETAINED_PI_EXACT_AV_REPORT_OVERLAP'
            result['samples']=pi['samples']
            result['observations']=pi['observations']
        if kind=='sample':
            members = self._scope(kind,value).to_dict('records')
            result['records']=members
            result['permission_evidence']=pi['permission_evidence']
            result['vendor_claims']=self.av.vendor_claims(int(members[0]['sample_id'])) if members else []
            result['raw_source']=self._raw_sample(members[0]) if members else {'state':'UNAVAILABLE'}
        governed_ids = {int(m['sample_id']) for m in self.pi.samples}
        export_ids = set(self.av.samples.loc[self.av.samples.permission_covered.eq(True), 'sample_id'])
        result['coverage_populations'] = [
            dict(population='Catalog retained AV',samples=len(self.av.samples)),
            dict(population='Governed retained PI exact AV overlap',samples=len(governed_ids)),
            dict(population='Prior export unresolved provider evidence; separate contract',samples=len(export_ids)),
            dict(population='Overlap of the two PI contracts',samples=len(governed_ids & export_ids)),
            dict(population='Catalog outside both retained PI contracts',samples=len(self.av.samples)-len(governed_ids|export_ids))]
        if self.coverage is not None:
            outside = ~self.coverage.sample_id.isin(governed_ids|export_ids)
            result['coverage_populations'] += [
                dict(population=label,samples=int(mask.sum())) for label,mask in [
                    ('Historical upstream observations',self.coverage.pi_observation_rows.gt(0)),
                    ('Historical accepted canonical identities',self.coverage.pi_canonical_rows.gt(0)),
                    ('Historical observations outside both retained contracts',outside & self.coverage.pi_observation_rows.gt(0)),
                    ('Historical accepted identities outside both retained contracts',outside & self.coverage.pi_canonical_rows.gt(0)),
                    ('Historical no upstream observations',self.coverage.pi_observation_rows.eq(0))]]
            result['coverage_observed_utc'] = self.manifest['coverage']['observed_utc']
        result['restriction_disposition'] = 'Outside retained contracts does not isolate authorization from projection/source defects; exact mutually exclusive cause counts UNAVAILABLE. No live refresh performed.'
        result['missingness_note']='PI positive observations only; unobserved permissions are not proven absent. Latest report correspondence is not original historical-event authority.'
        result['type_basis']='Primary family taxonomy; pooled and equal-family PI frequencies have different denominators.'
        if self.interpretation_pin is not None and kind in {'overview','engine','family','type','sample'}:
            result.update(self.vendor_intelligence(kind,value))
        return result
