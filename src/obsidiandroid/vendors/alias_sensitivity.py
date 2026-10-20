"""Non-destructive research naming sensitivity on existing vendor slots."""
import re
import pandas as pd
from obsidiandroid.labeling import malware_family_constants as constants
from obsidiandroid.labeling.taxonomy import normalize_family_name


def alias_sensitivity(vendors, sample_ids):
    """Return original labels, analytical names and full tied consensus sets.

    Raw extraction is limited to unique supported tokens consistent with the
    existing interpretation. It is compared with identically extractable slots.
    No new family assignments are written or used as independent truth.
    """
    ids = list(sample_ids)
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate sample population')
    v = vendors.copy()
    if v.duplicated(['sample_id', 'engine']).any() or not set(v.sample_id) <= set(ids):
        raise ValueError('Invalid vendor sample slots')
    for k in v.select_dtypes('category'):
        v[k] = v[k].astype(str)
    v['current'] = v.active_family.where(v.active_recognized, '')
    v['hqwar'] = v.current.eq('trickmo') & v.raw_label.str.contains(r'(?i)(?<![a-z0-9])hqwar(?![a-z0-9])')
    v['spymax'] = v.current.eq('spynote') & v.raw_label.str.contains(r'(?i)(?<![a-z0-9])spymax(?![a-z0-9])')
    lexicon = sorted((set(constants.KNOWN_FAMILIES) | set(constants.FAMILY_ALIASES)) - set(constants.GENERIC_TOKENS), key=lambda t: (-len(t), t))
    rx = re.compile(r'(?<![a-z0-9])(?:' + '|'.join(map(re.escape, lexicon)) + r')(?![a-z0-9])', re.I)
    cache = {}
    for label, family in v.loc[v.current.ne(''), ['raw_label', 'current']].drop_duplicates().itertuples(index=False, name=None):
        tokens = sorted({m.group().casefold() for m in rx.finditer(label) if normalize_family_name(m.group()) == family})
        cache[label, family] = tokens[0] if len(tokens) == 1 else ''
    v['raw_token'] = [cache.get((label, fam), '') for label, fam in zip(v.raw_label, v.current)]
    v['current_extractable'] = v.current.where(v.raw_token.ne(''), '')
    v['alias_rule'] = ''
    v.loc[v.hqwar, 'alias_rule'] = 'hqwar -> trickmo'
    v.loc[v.spymax, 'alias_rule'] = 'spymax -> spynote'
    v['disputed_distinct'] = v.current
    v.loc[v.hqwar, 'disputed_distinct'] = 'hqwar'
    v.loc[v.spymax, 'disputed_distinct'] = 'spymax'
    v['both_unresolved'] = v.current.where(~(v.hqwar | v.spymax), '')
    output = []
    for name in ['current', 'current_extractable', 'raw_token', 'disputed_distinct', 'both_unresolved']:
        counts = v[v[name].ne('')].groupby(['sample_id', name]).size().rename('count').reset_index()
        by_id = {sid: rows for sid, rows in counts.groupby('sample_id')}
        for sid in ids:
            rows = by_id.get(sid)
            tops = [] if rows is None else sorted(rows.loc[rows['count'].eq(rows['count'].max()), name])
            output.append(dict(sample_id=sid, scenario=name, votes=0 if rows is None else int(rows['count'].sum()),
                               families=0 if rows is None else len(rows), dominant_set='|'.join(tops),
                               dominant_unique=tops[0] if len(tops) == 1 else '', tie=len(tops) > 1))
    return v, pd.DataFrame(output)
