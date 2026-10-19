"""Offline descriptive tables from retained, already validated PI consumer rows.

No database or training entry points. Prevalence is sample based; source-unverified
observations never contribute to accepted-identity comparisons.
"""
from collections import Counter, defaultdict
from datetime import datetime


def describe_permissions(rows, identities):
    """Return family, identity prevalence and calendar-year descriptive records.

    Callers must verify frozen input hashes before invoking this function. Metadata
    joins require exact sample ID, SHA and family; duplicate observations fail.
    Missing dates are excluded from time cells, not converted to zero prevalence.
    """
    members = {}
    for item in identities:
        sid = int(item['sample_id'])
        if sid in members:
            raise ValueError('duplicate sample identity')
        members[sid] = item
    if not members or len(members) > 1312 or len(rows) > 100000:
        raise ValueError('cohort bounds')
    observed, seen = set(), set()
    families = defaultdict(set)
    years = defaultdict(set)
    for sid, item in members.items():
        families[item['family']].add(sid)
        if str(item.get('temporal_eligible')).lower() == 'true':
            try:
                first = datetime.fromisoformat(item['first_submission_utc'].replace('Z', '+00:00'))
                last = datetime.fromisoformat(item['last_analysis_utc'].replace('Z', '+00:00'))
                if first.tzinfo is None or last.tzinfo is None or first > last:
                    raise ValueError('invalid temporal ordering')
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('invalid eligible timestamp') from exc
            years[item['family'], str(first.year)].add(sid)
    counts = defaultdict(Counter)
    tokens = defaultdict(set)
    primary = defaultdict(set)
    for row in rows:
        sid = int(row['sample_id'])
        member = members.get(sid)
        if not member or (row['sha256'], row['family']) != (member['sha256'], member['family']):
            raise ValueError('sample SHA or family binding mismatch')
        if row['obs_id'] in seen:
            raise ValueError('duplicate observation')
        seen.add(row['obs_id'])
        observed.add(sid)
        family = row['family']
        tokens[family].add(row['exact_token'])
        counter = counts[family]
        counter['observations'] += 1
        counter['raw_exact_observations'] += bool(row['source_correspondence_verified'])
        counter['accepted_observations'] += bool(row['accepted_identity'])
        counter['resolved_observations'] += row['resolution_status'].startswith('RESOLVED')
        counter['unresolved_observations'] += row['resolution_status'] == 'UNRESOLVED'
        counter['protection_known_observations'] += row['protection_base'] is not None
        if row['accepted_identity'] and row['source_correspondence_verified']:
            if not row['canonical_identity']:
                raise ValueError('accepted identity missing canonical value')
            primary[row['canonical_identity']].add(sid)
    if observed != set(members):
        raise ValueError('missing sample observations')
    summary = [dict(family=f, samples=len(ids), exact_tokens=len(tokens[f]), **counts[f])
               for f, ids in sorted(families.items())]
    prevalence, temporal = [], []
    for token, ids in sorted(primary.items()):
        for family, population in sorted(families.items()):
            n = len(ids & population)
            prevalence.append(dict(permission=token, family=family, samples=n,
                                   sample_denominator=len(population), prevalence=n / len(population)))
        for (family, year), population in sorted(years.items()):
            n = len(ids & population)
            temporal.append(dict(permission=token, family=family, year=year, samples=n,
                                 sample_denominator=len(population), prevalence=n / len(population),
                                 small_cell=len(population) < 10))
    return dict(families=summary, prevalence=prevalence, temporal=temporal)
