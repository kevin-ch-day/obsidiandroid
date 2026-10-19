"""Descriptive AV/permission comparisons on an already validated offline cohort."""
from collections import defaultdict
from itertools import combinations

STATES = ('conflicting', 'recognized_nonconflicting', 'detected_no_recognized',
          'no_detected')


def compare_permission(members, observations, vendors, permission):
    """Compare observed positives using pooled and common-stratum denominators.

    Standardization gives equal weight to eligible strata in both groups. Missing
    source/time keys are displayed but never establish common support.
    """
    accepted = {r['canonical_identity'] for r in observations
                if r['accepted_identity'] and r['source_correspondence_verified']}
    if permission not in accepted:
        raise ValueError('Select an exact accepted canonical permission identity')
    ids = {int(m['sample_id']) for m in members}
    if len(ids) != len(members):
        raise ValueError('Duplicate comparison membership')
    frame = vendors[vendors.sample_id.isin(ids)]
    claims = frame[frame.active_recognized.eq(True)].groupby(
        'sample_id', observed=True).active_family.nunique().to_dict()
    detected = set(frame.loc[frame.category.isin(['malicious', 'suspicious']), 'sample_id'])
    observed_av = set(frame.sample_id)
    if observed_av != ids:
        raise ValueError('Comparison requires observed AV evidence for every member')
    positive = {r['sample_id'] for r in observations
                if r['canonical_identity'] == permission and r['accepted_identity']
                and r['source_correspondence_verified']}
    unresolved = {r['sample_id'] for r in observations
                  if not r['source_correspondence_verified'] or r['resolution_status'] == 'UNRESOLVED'}
    groups = defaultdict(list)
    sample_rows = []
    for m in members:
        sid = int(m['sample_id'])
        n = claims.get(sid, 0)
        state = ('conflicting' if n > 1 else 'recognized_nonconflicting' if n == 1
                 else 'detected_no_recognized' if sid in detected else 'no_detected')
        batch = m.get('source_batch_label', '')
        period = m.get('first_submission_month', '') if str(m.get('temporal_eligible', '')).lower() == 'true' else ''
        row = dict(sample_id=sid, sha256=m['sha256'], family=m['family'],
                   event_id=m['event_id'], payload_hash=m['payload_hash'],
                   vendor_stratum=state, accepted_positive=sid in positive,
                   unresolved_evidence=sid in unresolved,
                   lineage_component=m.get('lineage_component', ''),
                   source_batch=batch or None, submission_month=period or None)
        sample_rows.append(row)
        for dimension, key in [('pooled', ()), ('family', (m['family'],)),
                               ('family_source', (m['family'], batch)),
                               ('family_period', (m['family'], period))]:
            groups[dimension, key, state].append(row)
    tables = []
    for dimension, key in sorted({(d, k) for d, k, _ in groups}):
        for state in STATES:
            rows = groups[dimension, key, state]
            n = len(rows)
            tables.append(dict(dimension=dimension, stratum=list(key), vendor_stratum=state,
                positive_samples=sum(r['accepted_positive'] for r in rows), sample_denominator=n,
                frequency=sum(r['accepted_positive'] for r in rows) / n if n else None,
                unresolved_samples=sum(r['unresolved_evidence'] for r in rows),
                inferred_components=len({r['lineage_component'] for r in rows if r['lineage_component']}),
                positive_inferred_components=len({r['lineage_component'] for r in rows
                                                 if r['lineage_component'] and r['accepted_positive']}),
                missing_lineage_samples=sum(not r['lineage_component'] for r in rows),
                missing_source_samples=sum(r['source_batch'] is None for r in rows),
                missing_period_samples=sum(r['submission_month'] is None for r in rows)))
    def population(keys, dimension, state):
        rows = [r for k in keys for r in groups[dimension, k, state]]
        positives = sum(r['accepted_positive'] for r in rows)
        return dict(sample_ids=sorted(r['sample_id'] for r in rows),
                    samples=len(rows), positive_samples=positives,
                    inferred_components=len({r['lineage_component'] for r in rows if r['lineage_component']}),
                    frequency=positives / len(rows) if rows else None)

    comparisons = []
    for dimension in ('pooled', 'family', 'family_source', 'family_period'):
        keys = {k for d, k, _ in groups if d == dimension and all(k)}
        for left, right in combinations(STATES, 2):
            shared = sorted(k for k in keys if groups[dimension, k, left] and groups[dimension, k, right])
            counts = [sum(len(groups[dimension, k, state]) for k in shared) for state in (left, right)]
            rates = [sum(sum(r['accepted_positive'] for r in groups[dimension, k, state]) /
                         len(groups[dimension, k, state]) for k in shared) / len(shared)
                     if shared else None for state in (left, right)]
            totals = [sum(r['vendor_stratum'] == state for r in sample_rows) for state in (left, right)]
            supported = [k for k in shared if min(len(groups[dimension, k, state])
                         for state in (left, right)) >= 5]
            sensitivity = [sum(sum(r['accepted_positive'] for r in groups[dimension, k, state]) /
                           len(groups[dimension, k, state]) for k in supported) / len(supported)
                           if supported else None for state in (left, right)]
            common = [population(shared, dimension, state) for state in (left, right)]
            screened = [population(supported, dimension, state) for state in (left, right)]
            comparisons.append(dict(dimension=dimension, left=left, right=right,
                common_population=dict(left=common[0], right=common[1]),
                common_population_pooled_difference=(common[0]['frequency']-common[1]['frequency']) if shared else None,
                min5_population=dict(left=screened[0], right=screened[1]),
                min5_population_pooled_difference=(screened[0]['frequency']-screened[1]['frequency']) if supported else None,
                min5_stratum_keys=[list(k) for k in supported],
                shared_stratum_keys=[list(k) for k in shared],
                minimum_cell_samples=min((len(groups[dimension, k, state])
                    for k in shared for state in (left, right)), default=None),
                min5_shared_strata=len(supported),
                min5_left_included=sum(len(groups[dimension, k, left]) for k in supported),
                min5_right_included=sum(len(groups[dimension, k, right]) for k in supported),
                min5_difference=sensitivity[0]-sensitivity[1] if supported else None,
                shared_strata=len(shared), left_included=counts[0], right_included=counts[1],
                left_excluded=totals[0]-counts[0], right_excluded=totals[1]-counts[1],
                left_frequency=rates[0], right_frequency=rates[1],
                difference=rates[0]-rates[1] if shared else None,
                state='DESCRIPTIVE_COMMON_SUPPORT' if shared else 'UNAVAILABLE_NO_COMMON_SUPPORT'))
    return dict(permission_query=permission, samples=len(members), observations=len(observations),
        exact_source_observations=sum(r['source_correspondence_verified'] for r in observations),
        projection_abstentions=sum(not r['source_correspondence_verified'] for r in observations),
        association_method='Equal weight per shared stratum; pooled uses one stratum. Difference is left minus right.',
        association_limits='Exploratory observed declarations, not runtime behavior or independent family truth. '
            'Nonpositive is not proven absence. No detected verdict does not mean benign. '
            'Missing source/time cannot establish shared support. Inferred components are not independent sources. '
            'No confidence interval or causal estimate; min5 is an arbitrary sensitivity screen requiring five samples '
            'per side, not a sufficiency or independence threshold. Small strata remain visible. '
            'Capability definitions unavailable.',
        association_strata=tables, association_contrasts=comparisons,
        association_samples=sample_rows)
