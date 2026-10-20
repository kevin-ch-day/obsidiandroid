"""Bounded structural sensitivity on validated retained permission evidence."""
from collections import defaultdict
from itertools import combinations

import numpy as np
from scipy.spatial.distance import jensenshannon


def profile_distance(left, right):
    """Base-2 Jensen-Shannon distance; zero-mass profiles are unavailable."""
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if (left.ndim != 1 or left.shape != right.shape or not np.isfinite(left).all()
            or not np.isfinite(right).all() or (left < 0).any() or (right < 0).any()):
        raise ValueError('Invalid permission profile')
    if not left.sum() or not right.sum():
        return None
    return float(jensenshannon(left, right, base=2))


def describe_structure(members, observations):
    """Describe normalized positive mass, preserving evidence and support limits.

    Upstream PermissionResearchView owns exact provenance/version validation.
    Components and batches here are sensitivity units, not independent sources.
    """
    if not members or len(members) > 3000 or len(observations) > 100000:
        raise ValueError('Structural analysis population bound')
    ids = [int(m['sample_id']) for m in members]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate structure membership')
    index = {sid: i for i, sid in enumerate(ids)}
    if any(r['sample_id'] not in index for r in observations):
        raise ValueError('Observation outside structure population')
    accepted = [r for r in observations if r['accepted_identity'] and r['source_correspondence_verified']]
    vocabulary = sorted({r['canonical_identity'] for r in accepted})
    families = sorted({m['family'] for m in members})
    if not vocabulary or len(vocabulary) > 2048 or len(families) > 50:
        raise ValueError('Structural vocabulary/family bound')
    columns = {v: i for i, v in enumerate(vocabulary)}
    matrix = np.zeros((len(ids), len(vocabulary)), dtype=bool)
    for row in accepted:
        matrix[index[row['sample_id']], columns[row['canonical_identity']]] = True
    unresolved_ids = {r['sample_id'] for r in observations
                      if not r['source_correspondence_verified'] or r['resolution_status'] == 'UNRESOLVED'}
    family_indices = {f: [i for i, m in enumerate(members) if m['family'] == f] for f in families}

    def profile(indices, mode='sample'):
        if not indices:
            return np.zeros(len(vocabulary))
        if mode == 'sample':
            return matrix[indices].mean(axis=0)
        components = defaultdict(list)
        for i in indices:
            if members[i].get('lineage_component'):
                components[members[i]['lineage_component']].append(i)
        return (np.mean([matrix[g].mean(axis=0) for g in components.values()], axis=0)
                if components else np.zeros(len(vocabulary)))

    def support(indices):
        timing = {}
        for field in ('fetched_at_utc', 'last_analysis_utc'):
            values = sorted(str(members[i][field]) for i in indices if members[i].get(field))
            timing[field] = dict(earliest=values[0] if values else None,
                                 latest=values[-1] if values else None,
                                 missing_samples=len(indices)-len(values))
        return dict(retained_report_timing=timing,
            supported_acquisition_origins=None,
            acquisition_origin_state='UNESTABLISHED_BY_BATCH_OR_COMPONENT',
            samples=len(indices), positive_profile_samples=sum(bool(matrix[i].any()) for i in indices),
            inferred_components=len({members[i]['lineage_component'] for i in indices
                                     if members[i].get('lineage_component')}),
            missing_lineage_samples=sum(not members[i].get('lineage_component') for i in indices),
            known_source_batches=len({members[i]['source_batch_label'] for i in indices
                                      if members[i].get('source_batch_label')}),
            missing_source_samples=sum(not members[i].get('source_batch_label') for i in indices),
            unresolved_samples=sum(ids[i] in unresolved_ids for i in indices))

    profiles, pairs, contributions, sensitivity, annual, temporal = [], [], [], [], [], []
    coverage, component_sensitivity = [], []
    for family, indices in family_indices.items():
        for mode in ('sample', 'equal_component'):
            vector = profile(indices, mode)
            group_support = support(indices)
            for permission, rate in zip(vocabulary, vector):
                profiles.append(dict(family=family, weighting=mode, permission=permission,
                    observed_frequency=float(rate) if mode == 'sample' or group_support['inferred_components'] else None,
                    normalized_positive_mass=float(rate/vector.sum()) if vector.sum() else None,
                    positive_samples=int(matrix[indices, columns[permission]].sum()), **group_support))
    for left, right in combinations(families, 2):
        li, ri = family_indices[left], family_indices[right]
        for mode in ('sample', 'equal_component'):
            a, b = profile(li, mode), profile(ri, mode)
            pairs.append(dict(left=left, right=right, weighting=mode, distance=profile_distance(a,b),
                              left_support=support(li), right_support=support(ri)))
        for family, indices, other in [(left, li, ri), (right, ri, li)]:
            components = defaultdict(list)
            for i in indices:
                if members[i].get('lineage_component'):
                    components[members[i]['lineage_component']].append(i)
            baseline = profile_distance(profile(indices), profile(other))
            distances = []
            for component, group in sorted(components.items()):
                remaining_mass = matrix[indices].sum(axis=0) - matrix[group].sum(axis=0)
                distance = profile_distance(remaining_mass, profile(other))
                if distance is not None:
                    distances.append((distance, component, len(group)))
            strongest = (max(distances, key=lambda item: abs(item[0]-baseline))
                         if distances and baseline is not None else None)
            component_sensitivity.append(dict(left=left, right=right, omitted_family=family,
                inferred_components=len(components), estimable_omissions=len(distances),
                unavailable_omissions=len(components)-len(distances),
                minimum_distance=min((x[0] for x in distances), default=None),
                maximum_distance=max((x[0] for x in distances), default=None),
                largest_shift=abs(strongest[0]-baseline) if strongest else None,
                largest_shift_component=strongest[1] if strongest else None,
                largest_shift_removed_samples=strongest[2] if strongest else None))
        a, b = profile(li), profile(ri)
        if a.sum() and b.sum():
            p, q = a/a.sum(), b/b.sum(); midpoint=(p+q)/2
            terms=np.zeros(len(vocabulary))
            for x in (p,q):
                nonzero=x>0
                terms[nonzero] += .5*x[nonzero]*np.log2(x[nonzero]/midpoint[nonzero])
            for j in sorted(range(len(vocabulary)),key=lambda j:(-terms[j],vocabulary[j])):
                contributions.append(dict(left=left,right=right,permission=vocabulary[j],
                    js_divergence_contribution=float(terms[j]),left_frequency=float(a[j]),right_frequency=float(b[j])))
        # Omit one known batch from one family at a time; missing is not a batch.
        for family, indices, other in [(left,li,ri),(right,ri,li)]:
            batches=sorted({members[i]['source_batch_label'] for i in indices if members[i].get('source_batch_label')})
            for batch in batches:
                remaining=[i for i in indices if members[i].get('source_batch_label') != batch]
                distance=profile_distance(profile(remaining),profile(other))
                sensitivity.append(dict(left=left,right=right,omitted_family=family,omitted_batch=batch,
                    omitted_samples=len(indices)-len(remaining),remaining_samples=len(remaining),distance=distance,
                    remaining_known_source_batches=support(remaining)['known_source_batches'],
                    remaining_missing_source_samples=support(remaining)['missing_source_samples'],
                    state='DESCRIPTIVE_OMISSION' if distance is not None else 'UNAVAILABLE_NO_POSITIVE_MASS'))
    for family, indices in family_indices.items():
        years=defaultdict(list); missing=0
        for i in indices:
            member=members[i]; month=member.get('first_submission_month','')
            if str(member.get('temporal_eligible','')).lower() == 'true' and len(month)==7 and month[:4].isdigit():
                years[month[:4]].append(i)
            else:
                missing+=1
        coverage.append(dict(family=family, missing_period_samples=missing,
                             observed_years=sorted(years), **support(indices)))
        for year, group in sorted(years.items()):
            for permission, rate in zip(vocabulary,profile(group)):
                annual.append(dict(family=family,year=year,permission=permission,observed_frequency=float(rate),
                    positive_samples=int(matrix[group,columns[permission]].sum()),
                    family_missing_period_samples=missing,**support(group)))
        for (year_a,group_a),(year_b,group_b) in zip(sorted(years.items()),sorted(years.items())[1:]):
            for mode in ('sample','equal_component'):
                temporal.append(dict(family=family,earlier_year=year_a,later_year=year_b,year_gap=int(year_b)-int(year_a),weighting=mode,
                    distance=profile_distance(profile(group_a,mode),profile(group_b,mode)),
                    earlier_support=support(group_a),later_support=support(group_b),
                    min5_samples_each=min(len(group_a),len(group_b))>=5,
                    shared_inferred_components=len({members[i].get('lineage_component') for i in group_a} &
                        {members[i].get('lineage_component') for i in group_b} - {None,''})))
    return dict(samples=len(ids),observations=len(observations),accepted_permission_identities=len(vocabulary),
        exact_source_observations=sum(r['source_correspondence_verified'] for r in observations),
        projection_abstentions=sum(not r['source_correspondence_verified'] for r in observations),
        structure_method='Base-2 Jensen-Shannon distance (sqrt divergence). Normalize positive-frequency vectors to sum one; fixed full-cohort vocabulary. No smoothing.',
        structure_limits='Current retained cohort, not paper reproduction. Observed declarations, not execution; nonpositive is not proven absence. '
            'Similarity does not establish lineage or shared behavior. Equal-component weighting excludes missing lineage. '
            'Batch omission is sensitivity, not independent replication or confidence bounds. First-submission years are proxies, not emergence dates. '
            'Adjacent observed years may have gaps. Five samples is a descriptive screen, not adequate power. No training authority.',
        structure_component_sensitivity=component_sensitivity,structure_coverage=coverage,structure_pairs=pairs,structure_profiles=profiles,structure_contributions=contributions,
        structure_source_sensitivity=sensitivity,structure_annual=annual,structure_temporal=temporal)
