"""Descriptive lineage sensitivity; inferred components are not proven independence."""
from collections import defaultdict
import numpy as np


def lineage_signature(population, positive_ids, *, seed=20261019, draws=2000):
    """Compare sample and equal-component support, with bootstrap sensitivity.

    Percentiles resample inferred components, not verified independent families.
    Missing component IDs are excluded from group estimates and counted explicitly.
    """
    groups = defaultdict(list)
    seen = set()
    for row in population:
        sid = int(row['sample_id'])
        if sid in seen:
            raise ValueError('Duplicate sample identity')
        seen.add(sid)
        if row.get('lineage_component'):
            groups[row['lineage_component']].append(sid in positive_ids)
    if not population or draws < 100 or draws > 10000:
        raise ValueError('Population or bootstrap bound')
    rates = np.array([np.mean(v) for _, v in sorted(groups.items())])
    positives = len(seen & positive_ids)
    n = len(population)
    sizes = [len(v) for v in groups.values()]
    result = dict(samples=n, positive_samples=positives, sample_prevalence=positives/n,
                  components=len(groups), positive_components=sum(any(v) for v in groups.values()),
                  missing_lineage_samples=n-sum(sizes), largest_component_samples=max(sizes, default=0),
                  largest_positive_component=max((sum(v) for v in groups.values()), default=0),
                  equal_component_prevalence=None, bootstrap_low=None, bootstrap_high=None,
                  leave_one_out_low=None, leave_one_out_high=None,
                  bootstrap_scope='EXPLORATORY_INFERRED_COMPONENT_SENSITIVITY_NOT_POPULATION_CI')
    if len(rates):
        result['equal_component_prevalence'] = float(rates.mean())
    if len(rates) > 1:
        boot = np.random.default_rng(seed).choice(rates, (draws, len(rates)), replace=True).mean(axis=1)
        result['bootstrap_low'], result['bootstrap_high'] = map(float, np.quantile(boot, [.025, .975]))
        loo = [(positives-sum(v))/(n-len(v)) for v in groups.values() if n > len(v)]
        result['leave_one_out_low'], result['leave_one_out_high'] = min(loo), max(loo)
    return result
