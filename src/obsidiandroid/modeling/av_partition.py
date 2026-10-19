"""Exact AV-only holdout identity consumed by the real generic trainer."""
from dataclasses import dataclass
import hashlib
import re

import pandas as pd


def frame_digest(frame):
    return hashlib.sha256(frame.to_json(orient='split', double_precision=15).encode()).hexdigest()


@dataclass(frozen=True)
class AVPartition:
    source_sha256: str
    feature_digest: str
    label_digest: str
    train_ids: tuple
    test_ids: tuple
    groups: tuple

    def validate(self, features, labels):
        if not re.fullmatch('[a-f0-9]{64}', self.source_sha256):
            raise ValueError('AV partition source digest invalid')
        if not isinstance(labels, pd.Series) or not labels.index.equals(features.index):
            raise ValueError('AV partition label identities differ')
        if (frame_digest(features) != self.feature_digest
                or frame_digest(labels) != self.label_digest):
            raise ValueError('AV partition features or labels changed')
        if not features.columns.is_unique or not all(
                str(c).startswith(('avobs__', 'avdet__')) for c in features):
            raise ValueError('AV partition permits observation/detection predictors only')
        if not features.isin([0, 1]).all().all():
            raise ValueError('AV partition predictors must be binary')
        train, test = set(self.train_ids), set(self.test_ids)
        if (not train or not test or train & test or train | test != set(features.index)
                or len(train) != len(self.train_ids) or len(test) != len(self.test_ids)):
            raise ValueError('AV partition membership invalid')
        groups = dict(self.groups)
        if set(groups) != set(features.index) or len(groups) != len(self.groups):
            raise ValueError('AV partition group evidence incomplete')
        if {groups[i] for i in train} & {groups[i] for i in test}:
            raise ValueError('AV partition lineage overlap')
        classes = set(labels)
        for ids, minimum in ((self.train_ids, 10), (self.test_ids, 5)):
            counts = labels.loc[list(ids)].value_counts()
            if set(counts.index) != classes or counts.min() < minimum:
                raise ValueError('AV partition class support insufficient')

    def partition(self, features, labels, encoded):
        self.validate(features, labels)
        by_id = pd.Series(encoded, index=features.index)
        train, test = list(self.train_ids), list(self.test_ids)
        return (features.loc[train], features.loc[test], by_id.loc[train].to_numpy(),
                by_id.loc[test].to_numpy(), ('retained-av', self.source_sha256,
                                            self.feature_digest, self.label_digest,
                                            self.train_ids, self.test_ids))
