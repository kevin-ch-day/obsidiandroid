"""Target-resolved outer partition shared by PI vocabulary and generic fitting.

The plan is data, not authorization. Existing V2 approval v1 grants feature
acceptance only; production training remains blocked until a separate scope
contract is reviewed. No caller-supplied flag can authorize that extension.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import hashlib
import json
from numbers import Integral
from pathlib import Path

import numpy as np
import pandas as pd

from config import app_config
from obsidiandroid.orchestration import permission_v2_export as v2


class ExperimentIntegrityError(ValueError):
    """A governed fit cannot satisfy its immutable identity contract."""


def _fail(message):
    raise ExperimentIntegrityError('[EXPERIMENT] ' + message)


def canonical(value):
    """Serialize contract data deterministically; reject non-JSON provenance."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _ids(values):
    result = []
    for value in values:
        # Alignment uses canonical decimal strings; never accept floats/bools.
        if isinstance(value, str) and value.isdecimal() and str(int(value)) == value:
            value = int(value)
        if not isinstance(value, Integral) or isinstance(value, bool) or value <= 0:
            _fail('Source sample ID must be an exact positive integer')
        result.append(int(value))
    if len(result) != len(set(result)):
        _fail('Duplicate source sample ID')
    return tuple(result)


def _policy():
    from .model_trainer_factory import _resolve_training_runtime_defaults
    size, seed = _resolve_training_runtime_defaults(None, None)
    names = ('ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT', 'AUTO_ADJUST_TRAIN_TEST_SPLIT',
             'RUNTIME_ABLATION_ACTIVE', 'MIN_TEST_SAMPLES_PER_CLASS',
             'RUNTIME_PROFILE_ID', 'RUNTIME_SUPPORT_FLOOR_MODE', 'RUNTIME_MIN_FAMILY_SUPPORT',
             'MIN_FAMILY_SUPPORT', 'GROUP_LOW_SUPPORT_LABELS', 'PERMISSION_MIN_SUPPORT')
    return canonical({'test_size': size, 'seed': seed,
                      **{name: getattr(app_config, name, None) for name in names}})


def eligibility_digest():
    """Bind the inspected authority/eligibility code, without inventing a release ID."""
    from . import data_alignment
    from obsidiandroid.common import family_label_semantics
    from obsidiandroid.labeling import malware_family_constants
    paths = [Path(__file__), *(Path(m.__file__) for m in
              (data_alignment, family_label_semantics, malware_family_constants))]
    return digest([hashlib.sha256(path.read_bytes()).hexdigest() for path in paths])


def resolve_target(samples, target, minimum_support=None):
    """Reuse family authority alignment, with explicit type/composite exclusions."""
    from .data_alignment import extract_aligned_labels
    v2._sample_identity(samples)
    if target not in {'family_id', 'type_slug', 'family_within_type'}:
        _fail('Unsupported target; declare family_id, type_slug or family_within_type')
    if target in {'family_id', 'family_within_type'} and not {
        'family_id', 'family_canonical'} <= set(samples.columns):
        _fail('Family authority fields are missing')
    dummy = pd.DataFrame({'identity_only': 0}, index=samples.sample_id)
    _, labels = extract_aligned_labels(
        dummy, samples, forced_label_column='family_id' if target == 'family_within_type' else target,
        drop_low_support=False, verbose=False)
    if target in {'family_id', 'family_within_type'}:
        labels = labels[pd.to_numeric(labels, errors='coerce').gt(0)]
    if target in {'type_slug', 'family_within_type'}:
        types = samples.set_index(samples.sample_id.astype(str)).type_slug.reindex(labels.index)
        valid = types.notna() & ~types.astype(str).str.strip().str.lower().isin(
            {'', 'unknown', 'unmapped', 'none', 'null'})
        labels = labels.loc[valid]
        if target == 'family_within_type':
            names = samples.set_index(samples.sample_id.astype(str)).family_canonical
            labels = types.loc[labels.index].astype(str) + '::' + names.loc[labels.index].astype(str)
    if minimum_support is not None:
        if not isinstance(minimum_support, int) or isinstance(minimum_support, bool) or minimum_support < 1:
            _fail('Target support policy must be a positive integer')
        labels = labels[labels.map(labels.value_counts()) >= minimum_support]
    if labels.nunique() < 2:
        _fail('Target eligibility leaves fewer than two classes')
    labels = labels.astype(str)
    labels.name = target
    labels.index = pd.Index(_ids(labels.index), name='sample_id')
    labels = labels.sort_index()
    return labels


@dataclass(frozen=True)
class ExperimentPlan:
    """Immutable physical identities and outer fit membership, not a fit permit."""
    version: str
    experiment_id: str
    profile_id: str
    target: str
    source_identity: tuple[tuple[int, str], ...]
    labels: tuple[tuple[int, str], ...]
    excluded_ids: tuple[int, ...]
    minimum_support: int | None
    profile_digest: str
    source_digest: str
    approval_digest: str
    eligibility_digest: str
    sample_metadata_digest: str
    runtime_policy: str
    algorithm: str
    train_ids: tuple[int, ...]
    test_ids: tuple[int, ...]
    test_size: float
    seed: int
    permission_min_support: int

    def __post_init__(self):
        if self.version != 'obsidiandroid-experiment-split-v1':
            _fail('Unsupported experiment plan version')
        if not all(isinstance(value, str) and value for value in (self.experiment_id, self.profile_id)):
            _fail('Experiment/profile identity is missing')
        if self.target not in {'family_id', 'type_slug', 'family_within_type'}:
            _fail('Unsupported experiment target')
        for value in (self.profile_digest, self.source_digest, self.approval_digest, self.eligibility_digest, self.sample_metadata_digest):
            if not v2._hex(value):
                _fail('Required provenance digest is missing or malformed')
        for name in ('source_identity', 'labels', 'excluded_ids', 'train_ids', 'test_ids'):
            if not isinstance(getattr(self, name), tuple):
                _fail('Experiment membership must be immutable tuples')
        if any(not isinstance(row, tuple) or len(row) != 2
               for row in (*self.source_identity, *self.labels)):
            _fail('Source and label identity records are malformed')
        if self.algorithm not in {'stratified_seeded', 'balanced_auto_adjusted_v1',
                                  'group_shuffle_seeded_v1', 'temporal_year_holdout_v1'}:
            _fail('Unsupported partition algorithm')
        source = _ids(x[0] for x in self.source_identity)
        if len({x[1] for x in self.source_identity}) != len(source) or any(
                not v2._hex(x[1]) for x in self.source_identity):
            _fail('Duplicate or invalid SHA-256 source identity')
        eligible = _ids(x[0] for x in self.labels)
        train, test, excluded = _ids(self.train_ids), _ids(self.test_ids), _ids(self.excluded_ids)
        if not train or not test or set(train) & set(test):
            _fail('Training/evaluation membership is empty or overlaps')
        if set(train) | set(test) != set(eligible):
            _fail('Partition does not cover the exact eligible population')
        if set(eligible) & set(excluded) or set(eligible) | set(excluded) != set(source):
            _fail('Eligibility/exclusions do not partition the source population')
        if len({x[1] for x in self.labels}) < 2:
            _fail('Eligible class universe has fewer than two classes')
        if (not isinstance(self.permission_min_support, int)
                or isinstance(self.permission_min_support, bool) or self.permission_min_support < 1):
            _fail('Permission support policy is invalid')

    def to_json(self):
        return canonical(asdict(self))

    @property
    def sha256(self):
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_json(cls, text, expected_digest):
        """Replay exact serialized identity; still requires live source authorization."""
        if hashlib.sha256(text.encode()).hexdigest() != expected_digest:
            _fail('Serialized experiment digest changed')
        data = json.loads(text)
        for name in ('source_identity', 'labels'):
            data[name] = tuple(tuple(row) for row in data[name])
        for name in ('train_ids', 'test_ids', 'excluded_ids'):
            data[name] = tuple(data[name])
        plan = cls(**data)
        if plan.to_json() != text:
            _fail('Experiment serialization is not canonical')
        return plan


def assert_training_authorized(plan, export_path):
    """Do not reinterpret feature-acceptance v1 as target-specific fit authority."""
    export_bytes, anchor_bytes, _ = v2._checked_export(Path(export_path))
    if hashlib.sha256(export_bytes).hexdigest() != plan.source_digest or hashlib.sha256(
            anchor_bytes).hexdigest() != plan.approval_digest:
        _fail('Source export or approval changed after planning')
    _fail('PI V2 approval v1 authorizes feature acceptance, not this target-specific '
          'training partition; a separately reviewed training-scope contract is required')


@dataclass
class ExperimentBinding:
    """Run-local verified inputs; never recovered from untrusted dataframe attrs."""
    plan: ExperimentPlan
    samples: pd.DataFrame
    export_path: Path
    permission_frame: pd.DataFrame | None = None

    def __post_init__(self):
        self._plan_digest = self.plan.sha256

    def validate_source(self):
        self.plan.__post_init__()
        if eligibility_digest() != self.plan.eligibility_digest:
            _fail('Eligibility implementation changed after planning')
        if self.plan.sha256 != self._plan_digest:
            _fail('Experiment plan changed after binding')
        if hashlib.sha256(self.samples.to_json(orient='split', date_format='iso').encode()).hexdigest() != self.plan.sample_metadata_digest:
            _fail('Source metadata, eligibility or grouping/time evidence changed')
        if tuple(v2._sample_identity(self.samples)) != self.plan.source_identity:
            _fail('Sample ID/SHA source identity changed')
        labels = resolve_target(self.samples, self.plan.target, self.plan.minimum_support)
        if tuple(labels.items()) != self.plan.labels:
            _fail('Target eligibility or label authority changed')
        if _policy() != self.plan.runtime_policy:
            _fail('Split policy changed after experiment planning')
        assert_training_authorized(self.plan, self.export_path)

    def bind_permission_frame(self, frame):
        self.validate_source()
        v2.assert_verified_v2_frame(frame, samples=self.samples,
                                   training_sample_ids=self.plan.train_ids,
                                   min_support=self.plan.permission_min_support)
        self.permission_frame = frame.copy(deep=True)

    def align(self, features, samples):
        self.validate_source()
        if tuple(v2._sample_identity(samples)) != self.plan.source_identity:
            _fail('Alignment source ID/SHA membership differs from plan')
        if tuple(resolve_target(samples, self.plan.target, self.plan.minimum_support).items()) != self.plan.labels:
            _fail('Alignment target eligibility changed')
        features = features.copy()
        if 'sample_id' in features.columns:
            features = features.set_index('sample_id')
        features.index = pd.Index(_ids(features.index), name='sample_id')
        if set(features.index) != {x[0] for x in self.plan.source_identity}:
            _fail('Feature assembly lost or added source samples')
        labels = pd.Series(dict(self.plan.labels), name=self.plan.target)
        labels.index.name = 'sample_id'
        return features.loc[labels.index], labels

    def validate_features(self, features, labels):
        self.validate_source()
        if not isinstance(labels, pd.Series) or labels.name != self.plan.target:
            _fail('Target metadata is missing or incompatible')
        ids = _ids(features.index)
        if ids != _ids(labels.index):
            _fail('Feature and target rows are misaligned')
        if dict(zip(ids, labels.astype(str))) != dict(self.plan.labels):
            _fail('Eligible membership or target labels differ from experiment')
        if self.permission_frame is None:
            _fail('Verified permission vocabulary receipt is missing')
        v2.assert_verified_v2_frame(self.permission_frame, samples=self.samples,
                                   training_sample_ids=self.plan.train_ids,
                                   min_support=self.plan.permission_min_support)
        expected = self.permission_frame.set_index('sample_id')
        columns = list(expected.columns)
        if not set(columns) <= set(features.columns):
            _fail('Permission features or evidence-status columns are missing')
        actual = features[columns].copy()
        actual.index = ids
        if not np.array_equal(actual.to_numpy(), expected.loc[list(ids), columns].to_numpy()):
            _fail('Permission feature values no longer align with source sample rows')

    def partition(self, features, labels, encoded, size, seed, kwargs):
        from .model_trainer_factory import _runtime_training_state
        self.validate_features(features, labels)
        if (size, seed) != (self.plan.test_size, self.plan.seed):
            _fail('Trainer partition parameters differ from plan')
        if {'X_train', 'X_test', 'y_train', 'y_test', 'sample_ids', 'label_encoder'} & set(kwargs):
            _fail('Trainer arguments cannot override governed arrays')
        key = ('experiment', self.plan.sha256)
        expected = {'train_index': list(self.plan.train_ids), 'test_index': list(self.plan.test_ids),
                    'split_algorithm': self.plan.algorithm, 'plan_digest': self.plan.sha256}
        cache = _runtime_training_state().setdefault('split_cache', {})
        if key in cache and cache[key] != expected:
            _fail('Stale or corrupted cached experiment partition')
        cache[key] = expected
        x = features.copy(); x.index = _ids(features.index)
        y = pd.Series(encoded, index=x.index)
        tr, te = list(self.plan.train_ids), list(self.plan.test_ids)
        setattr(app_config, 'RUNTIME_LAST_SPLIT_ALGORITHM', self.plan.algorithm)
        return x.loc[tr], x.loc[te], y.loc[tr].to_numpy(), y.loc[te].to_numpy(), key

    def resampling_receipt(self, original_x, original_y, fit_x, fit_y, *, enabled):
        n = len(original_x)
        if _ids(original_x.index) != self.plan.train_ids:
            _fail('Preprocessing fit membership differs from vocabulary membership')
        if len(fit_x) < n or len(fit_x) != len(fit_y) or (
            not enabled and len(fit_x) != n):
            _fail('Unsupported augmentation membership')
        if not np.array_equal(np.asarray(fit_x)[:n], np.asarray(original_x)) or not np.array_equal(
                np.asarray(fit_y)[:n], np.asarray(original_y)):
            _fail('Augmentation changed original source rows or label alignment')
        resampling = None
        if enabled:
            resampling = getattr(app_config, 'RUNTIME_SMOTE_AUDIT_LAST', None)
            if (not isinstance(resampling, dict)
                or resampling.get('original_train_n') != n
                or resampling.get('post_resample_train_n') != len(fit_x)
                or resampling.get('method') not in {'SMOTE', 'ROS_fallback', 'ROS_rare_class_replication'}):
                _fail('Training augmentation provenance is missing or incompatible')
            if not set(np.asarray(fit_y)) <= set(np.asarray(original_y)):
                _fail('Augmentation introduced an unapproved class')
        return {'plan_digest': self.plan.sha256, 'target': self.plan.target,
                'source_train_ids': list(self.plan.train_ids),
                'evaluation_ids': list(self.plan.test_ids),
                'vocabulary_fit_ids': list(self.plan.train_ids),
                'estimator_preprocessing_fit_ids': list(self.plan.train_ids),
                'feature_selection_fit_ids': list(self.plan.train_ids),
                'additional_training_rows': len(fit_x) - n,
                'additional_rows_are_catalog_identities': False,
                'resampling': dict(resampling) if resampling is not None else None}


ACTIVE = ContextVar('obsidiandroid_experiment_split', default=None)


@contextmanager
def experiment_scope(binding=None):
    """Prevent experiment state leaking across runs, failures or nested callers."""
    token = ACTIVE.set(binding)
    try:
        yield
    finally:
        ACTIVE.reset(token)


def validate_fit_boundary(features, labels):
    binding = ACTIVE.get()
    has_v2 = any(str(c).startswith(('perm_provider_unresolved__',
                                  'perm_status__provider_reported_unresolved_count')) for c in features)
    if binding is None:
        if has_v2 or features.attrs.get('permission_feature_contract_version') == v2.CONTRACT_VERSION:
            _fail('PI V2 training requires a runner-owned experiment plan and vocabulary receipt')
        return None
    if not isinstance(binding, ExperimentBinding):
        _fail('Experiment binding is malformed')
    binding.validate_features(features, labels)
    return binding


def prepare_experiment(samples, profile, experiment_id):
    """Resolve eligibility then reuse the generic splitter before feature fitting."""
    from .model_trainer_factory import resolve_training_partition, _resolve_training_runtime_defaults
    from sklearn.preprocessing import LabelEncoder
    flags = profile.get('feature_flags', {})
    if flags.get('permission_feature_contract_version') != v2.CONTRACT_VERSION:
        return None
    path = Path(flags.get('permission_v2_export_path', ''))
    data, anchor, export = v2._checked_export(path)
    identities = tuple(v2._sample_identity(samples))
    exported = tuple(sorted((x['sample_id'], x['sha256']) for x in export['samples']))
    if identities != exported:
        _fail('Source cohort is outside exact PI V2 export coverage')
    target = profile.get('training_label_field', 'family_id')
    mode = str(getattr(app_config, 'RUNTIME_SUPPORT_FLOOR_MODE', 'membership_gate'))
    if getattr(app_config, 'GROUP_LOW_SUPPORT_LABELS', False):
        _fail('Grouping sparse labels would change governed target identity; unsupported')
    minimum = (None if mode == 'diagnostic_only' or
               (mode == 'benchmark_eligibility' and target == 'type_slug') else
               int(getattr(app_config, 'RUNTIME_MIN_FAMILY_SUPPORT',
                           getattr(app_config, 'MIN_FAMILY_SUPPORT', 3)) or 3))
    labels = resolve_target(samples, target, minimum)
    dummy = pd.DataFrame({'identity_only': 0}, index=labels.index.rename(None))
    size, seed = _resolve_training_runtime_defaults(None, None)
    setattr(app_config, 'RUNTIME_SPLIT_SAMPLE_METADATA', samples.copy(deep=True))
    tr, te, _, _, _ = resolve_training_partition(dummy, labels, LabelEncoder().fit_transform(labels),
                                                size, seed, strict=True)
    algorithm = str(getattr(app_config, 'RUNTIME_LAST_SPLIT_ALGORITHM', ''))
    eligibility = eligibility_digest()
    plan = ExperimentPlan('obsidiandroid-experiment-split-v1', experiment_id,
                          profile.get('profile_id', ''), target, identities, tuple(labels.items()),
                          tuple(sorted(set(x[0] for x in identities) - set(labels.index))), minimum,
                          digest(profile), hashlib.sha256(data).hexdigest(), hashlib.sha256(anchor).hexdigest(),
                          eligibility, hashlib.sha256(samples.to_json(orient='split', date_format='iso').encode()).hexdigest(), _policy(), algorithm, _ids(tr.index), _ids(te.index), size, seed,
                          int(getattr(app_config, 'PERMISSION_MIN_SUPPORT', 2)))
    declared = flags.get('permission_training_sample_ids')
    if declared is not None and set(_ids(declared)) != set(plan.train_ids):
        _fail('Configured vocabulary membership differs from target plan; acceptance split cannot be reused')
    binding = ExperimentBinding(plan, samples.copy(deep=True), path)
    binding.validate_source()
    ACTIVE.set(binding)
    return binding
