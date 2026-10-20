"""Exact-source descriptive permissions from explicitly pinned local evidence.

Historical PI strings remain a comparison surface. Source records do not assert
original-event linkage, manifest verification, runtime behavior, or training use.
"""
from collections import Counter, defaultdict
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

import pandas as pd

FORMAT = 'obsidiandroid-source-permission-view-v1'


class SourcePermissionResearch:
    """Read-only research consumer with exact source and dictionary identities."""

    supports_permission_queries = True

    def __init__(self, directory):
        self.root = Path(directory).resolve()
        path = self.root / 'SOURCE_PERMISSION_MANIFEST.json'
        if path.is_symlink() or path.stat().st_size > 1024**2:
            raise ValueError('Invalid source permission manifest')
        raw = path.read_bytes()
        self.manifest_sha256 = hashlib.sha256(raw).hexdigest()
        self.manifest = json.loads(raw)
        if self.manifest.get('format') != FORMAT:
            raise ValueError('Unsupported source permission format')
        self.samples = self._read('samples').set_index('sample_id')
        if (not self.samples.index.is_unique or self.samples.sha256.duplicated().any()
                or not all(re.fullmatch('[0-9a-f]{64}', s) for s in self.samples.sha256)):
            raise ValueError('Duplicate or invalid sample identity')
        self.tokens = self._read('tokens')
        bindings = self._read('bindings').set_index('sample_id')
        dictionary = self._read('dictionary')
        versions = dictionary[['catalog_release_id', 'catalog_digest']].drop_duplicates()
        if len(versions) != 1 or versions.iloc[0].to_dict() != self.manifest['dictionary']:
            raise ValueError('Dictionary version mismatch')
        if dictionary.canonical_permission.duplicated().any():
            raise ValueError('Conflicting canonical dictionary identity')
        self.canonical = set(dictionary.loc[dictionary.identity_status.eq('ACCEPTED'), 'canonical_permission'])
        self.definitions = dictionary.set_index('canonical_permission').to_dict('index')
        if not bindings.index.is_unique:
            raise ValueError('Duplicate source report identity')
        if self.tokens.duplicated(['sample_id', 'exact_provider_token']).any():
            raise ValueError('Multiple source observations need an explicit report selection')
        for field, target in [('sha256', self.samples.sha256),
                              ('event_id', bindings.event_id),
                              ('payload_hash', bindings.payload_hash_retained)]:
            if not self.tokens[field].eq(self.tokens.sample_id.map(target)).all():
                raise ValueError('Source sample/report binding mismatch')
        if not self.tokens.sha256.eq(self.tokens.sample_id.map(bindings.sha256_retained)).all():
            raise ValueError('Report SHA mismatch')
        if not self.tokens.payload_hash.map(lambda s: bool(re.fullmatch('[0-9a-f]{64}', s))).all():
            raise ValueError('Invalid payload digest')
        if not self.tokens.current_accepted_exact_identity.eq(self.tokens.exact_provider_token.isin(self.canonical)).all():
            raise ValueError('Retained acceptance contradicts exact dictionary')
        self.source = self.tokens.groupby('sample_id').exact_provider_token.agg(set).to_dict()
        self.accepted = {sid: tokens & self.canonical for sid, tokens in self.source.items()}
        self.history = self._read('stored')
        self.stored = self.history.groupby('sample_id').permission_string.agg(set).to_dict()
        self._history = {sid: rows.to_dict('records') for sid, rows in self.history.groupby('sample_id')}
        facts = self._read('authority')
        facts = facts[facts.is_current_best.eq(1) & facts.protection_level.ne('')]
        self.protection = facts.groupby('permission_string').protection_level.agg(lambda s: sorted(set(s))).to_dict()
        self._rows = {sid: rows for sid, rows in self.tokens.groupby('sample_id')}

    def _read(self, key):
        entry = self.manifest['inputs'][key]
        path = Path(entry['path'])
        if not path.is_absolute():
            path = self.root / path
        if path.is_symlink() or path.stat().st_size != entry['bytes']:
            raise ValueError('Source input size or path mismatch')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Source input digest mismatch')
        if path.suffix == '.gz':
            with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                raw = stream.read(entry['decoded_bytes'] + 1)
        if len(raw) != entry['decoded_bytes']:
            raise ValueError('Source input decoded bound mismatch')
        frame = pd.read_csv(BytesIO(raw), keep_default_na=False, dtype=str)
        for column in ['sample_id', 'event_id', 'is_current_best']:
            if column in frame:
                if not frame[column].str.fullmatch(r'[0-9]+').all():
                    raise ValueError('Invalid numeric source identity')
                frame[column] = frame[column].astype('int64')
        if 'current_accepted_exact_identity' in frame:
            if not frame.current_accepted_exact_identity.isin(['True', 'False']).all():
                raise ValueError('Invalid retained acceptance boolean')
            frame['current_accepted_exact_identity'] = frame.current_accepted_exact_identity.eq('True')
        if len(frame) != entry['rows']:
            raise ValueError('Source input row count mismatch')
        return frame

    def profile(self, sample_id):
        """Return exact source keys or unavailable; never infer missing keys."""
        sid = int(sample_id)
        if sid not in self.samples.index:
            raise ValueError('Unknown sample')
        if sid not in self.source:
            return dict(sample_id=sid, sha256=self.samples.loc[sid, 'sha256'],
                        state='UNAVAILABLE', accepted_count=None, records=[])
        records = []
        stored = self.stored.get(sid, set())
        for row in self._rows[sid].to_dict('records'):
            token = row['exact_provider_token']
            candidates = sorted(t for t in stored if t.casefold() == token.casefold())
            row.update(canonical_identity=token if token in self.canonical else None,
                       identity_status='ACCEPTED' if token in self.canonical else 'UNRESOLVED',
                       canonical_definition=self.definitions.get(token) if token in self.canonical else None,
                       stored_exact_present=token in stored,
                       historical_observations=[r for r in self._history.get(sid, []) if r['permission_string'] == token],
                       diagnostic_casefold_candidates=candidates,
                       correspondence='EXACT_TOKEN' if token in stored else 'CASEFOLD_ONLY' if candidates else 'SOURCE_ONLY',
                       historical_relationship='LATEST_REPORT_CORRESPONDENCE_ONLY',
                       original_observation_event_id=None,
                       current_protection_assertions=self.protection.get(token),
                       historical_effective_protection=None,
                       dictionary_version=self.manifest['dictionary'],
                       authority_snapshot_sha256=self.manifest['inputs']['authority']['sha256'],
                       evidence_level='PROVIDER_REPORTED', capabilities=None)
            records.append(row)
        return dict(sample_id=sid, sha256=self.samples.loc[sid, 'sha256'],
                    state='SOURCE_REPORTED', accepted_count=len(self.accepted[sid]), records=records,
                    stored_only_tokens=sorted(stored-self.source[sid]),
                    stored_only_accepted_tokens=sorted((stored-self.source[sid]) & self.canonical))

    def prevalence(self, sample_ids=None, permission=None):
        """Covered-only denominators plus explicitly unavailable sample counts."""
        ids = set(self.samples.index if sample_ids is None else sample_ids)
        if not ids <= set(self.samples.index):
            raise ValueError('Unknown sample in population')
        covered = ids & self.source.keys()
        counts = Counter(token for sid in covered for token in self.accepted[sid])
        tokens = [permission] if permission is not None else sorted(counts)
        return [dict(permission=t, positive=counts[t] if t in self.canonical else None,
                     identity_status='ACCEPTED' if t in self.canonical else 'UNRESOLVED',
                     exact_source_positive=sum(t in self.source[sid] for sid in covered),
                     sample_denominator=len(covered),
                     selected_samples=len(ids), unavailable_samples=len(ids)-len(covered),
                     prevalence=counts[t]/len(covered) if covered and t in self.canonical else None) for t in tokens]

    def feature_matrix(self, permissions, sample_ids=None):
        """Descriptive nullable membership matrix; no model execution or imputation."""
        permissions = list(permissions)
        if len(set(permissions)) != len(permissions):
            raise ValueError('Duplicate permission identity')
        if not set(permissions) <= self.canonical:
            raise ValueError('Descriptive matrix requires accepted canonical identities')
        ids = list(self.samples.index if sample_ids is None else sample_ids)
        if len(set(ids)) != len(ids) or not set(ids) <= set(self.samples.index):
            raise ValueError('Invalid feature population')
        return pd.DataFrame({t: pd.array([t in self.accepted[sid] if sid in self.accepted
                                         else pd.NA for sid in ids], dtype='boolean')
                             for t in permissions}, index=ids)

    def similarity(self, left, right):
        """Exact accepted-token Jaccard, unavailable for absent or empty union."""
        if left not in self.accepted or right not in self.accepted:
            return None
        a, b = self.accepted[left], self.accepted[right]
        return len(a & b)/len(a | b) if a | b else None

    def cooccurrence(self, first, second, *, strata=()):
        if not {first, second} <= self.canonical:
            raise ValueError('Cooccurrence requires accepted canonical identities')
        groups = defaultdict(list)
        for sid in self.source:
            key = tuple(self.samples.loc[sid, k] for k in strata)
            groups[key].append(sid)
        rows = []
        for key, ids in groups.items():
            a = sum(first in self.accepted[sid] for sid in ids)
            b = sum(second in self.accepted[sid] for sid in ids)
            both = sum(first in self.accepted[sid] and second in self.accepted[sid] for sid in ids)
            rows.append(dict(stratum=key, samples=len(ids), first=a, second=b,
                             both=both, expected=a*b/len(ids)))
        return rows

    def _availability(self, ids):
        ids = set(ids)
        covered = len(ids & self.source.keys())
        return dict(mode='RETAINED_OFFLINE_SOURCE', selected_samples=len(ids),
                    source_covered_samples=covered, unavailable_samples=len(ids)-covered)

    def describe(self, kind='overview', value=''):
        """Normal application research entry point, using source evidence explicitly."""
        result = dict(evidence='Provider-reported static keys; no manifest/runtime verification',
                      representation='EXACT_SOURCE_PERMISSION', training_authorized=False,
                      permission_consumer_availability=self._availability(self.samples.index),
                      classification_versions=self.manifest['dictionary'])
        if kind == 'sample':
            value = str(value)
            if re.fullmatch('[0-9a-f]{64}', value):
                ids = self.samples.index[self.samples.sha256.eq(value)].tolist()
            else:
                ids = [int(value)] if value.isascii() and value.isdigit() else []
            if len(ids) != 1:
                raise ValueError('Unknown sample')
            result['permission_consumer_availability'] = self._availability(ids)
            return dict(result, **self.profile(ids[0]))
        ids = self.samples.index
        if kind in {'family', 'type'}:
            column = 'family_label' if kind == 'family' else 'classification_primary'
            ids = self.samples.index[self.samples[column].eq(value)]
        elif kind not in {'overview', 'permission', 'comparison'}:
            raise ValueError('Unsupported source permission view')
        result['permission_consumer_availability'] = self._availability(ids)
        result['permission_totals'] = self.prevalence(ids, value if kind == 'permission' else None)
        return result
