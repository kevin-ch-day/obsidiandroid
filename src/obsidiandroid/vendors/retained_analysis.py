"""Descriptive vendor semantics from validated retained reports, never predictors."""
from collections import Counter
import json

import pandas as pd

from obsidiandroid.features.retained_av_reports import prepare_retained_av
from obsidiandroid.labeling.taxonomy import normalize_family_name, is_known_family_name
from .parsing.vendor_parser_map import get_vendor_parser_map
from .parsing.generic_label_parser import parse_generic_classification


def describe_retained_vendors(snapshot):
    """Preserve verdict categories and distinguish parsed tokens from known families.

    Consensus is an unweighted descriptive plurality, not independent truth or
    lifecycle quality. Missing engines are absent reports, never undetected.
    """
    detections, metadata = prepare_retained_av(snapshot)
    parsers = {}
    for name, entry in get_vendor_parser_map().items():
        for alias in [name, *entry.get('aliases', [])]:
            parsers[alias.casefold().replace('-', '_')] = entry['func']
    members = {r['sha256']: r for r in snapshot['members']}
    rows = []
    for report in snapshot['reports']:
        member = members[report['sha256']]
        results = json.loads(report['payload_json'])['data']['attributes']['last_analysis_results']
        for engine, verdict in results.items():
            label = verdict.get('result')
            row = {'sample_id': member['sample_id'], 'engine': engine,
                   'category': str(verdict['category']).replace('-', '_'),
                   'raw_label': label, 'recorded_family': member['recorded_family'],
                   'family': 'unknown', 'malware_type': 'unknown', 'known_family': False,
                   'parser_quality': 'unavailable', 'parser_error': None}
            if isinstance(label, str) and label.strip():
                parser = parsers.get(engine.casefold().replace('-', '_'), parse_generic_classification)
                row['parser'] = parser.__module__ + '.' + parser.__name__
                try:
                    parsed = parser(label)
                    if not isinstance(parsed, dict):
                        parsed = parsed.to_dict()
                    family = normalize_family_name(parsed.get('family', 'unknown'))
                    row.update(family=family, known_family=is_known_family_name(family),
                               malware_type=parsed.get('malware_type', 'unknown'),
                               parser_quality=parsed.get('parser_quality', 'unknown'))
                except Exception as exc:
                    row['parser_error'] = type(exc).__name__
            rows.append(row)
    frame = pd.DataFrame(rows)
    coverage = frame.groupby(['engine', 'category']).size().unstack(fill_value=0)
    coverage['missing_report'] = len(metadata) - coverage.sum(axis=1)
    consensus = []
    for sample_id, group in frame.groupby('sample_id', sort=True):
        votes = Counter(group.loc[group.known_family, 'family'])
        ranked = votes.most_common()
        top = ranked[0][1] if ranked else 0
        leaders = sorted(f for f, n in ranked if n == top)
        consensus.append({'sample_id': sample_id, 'known_family_votes': sum(votes.values()),
                          'distinct_known_families': len(votes), 'plurality_votes': top,
                          'plurality_family': leaders[0] if len(leaders) == 1 else None,
                          'tied': len(leaders) > 1})
    return frame, coverage, pd.DataFrame(consensus)
