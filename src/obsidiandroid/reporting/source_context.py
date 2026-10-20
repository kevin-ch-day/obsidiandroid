"""Identity-bound retained source context; never an acquisition-independence claim."""
from collections import Counter
import hashlib
import json
from pathlib import Path

IDENTITY = ('sample_id', 'sha256', 'event_id', 'payload_hash')


def identity(row):
    """Compare exact catalog and selected-report identities as strings."""
    return tuple(str(row[k]) for k in IDENTITY)


def load_context(raw, members):
    """Validate an overlay against catalog identities and retained source bytes.

    This version admits only catalog context, not inferred acquisition origins.
    Supported origins require a future independently evidenced source contract.
    """
    if len(raw) > 4 * 1024**2:
        raise ValueError('Source context bound')
    overlay = json.loads(raw)
    if set(overlay) != {'format', 'sources', 'rows'} or overlay['format'] != 'retained-source-context-v1':
        raise ValueError('Unsupported source context')
    records = {}
    for name, entry in overlay['sources'].items():
        path = Path(entry['path'])
        if path.is_symlink() or path.stat().st_size > 4 * 1024**2:
            raise ValueError('Source context evidence bound')
        evidence = path.read_bytes()
        if hashlib.sha256(evidence).hexdigest() != entry['sha256']:
            raise ValueError('Source context evidence digest')
        rows = json.loads(evidence)
        records[name] = {str(r['sample_id']): r for r in rows}
        if len(records[name]) != len(rows):
            raise ValueError('Duplicate source context evidence')
    expected = {str(m['sample_id']): m for m in members}
    result = {}
    for row in overlay['rows']:
        if set(row) != set(IDENTITY) | {'source_ref', 'cohort_kind'}:
            raise ValueError('Source overlay cannot override classifications')
        sid = str(row['sample_id'])
        if sid in result or sid not in expected or identity(row) != identity(expected[sid]):
            raise ValueError('Source context sample/report identity mismatch')
        if row['cohort_kind'] not in {'RETAINED_DESCRIPTIVE', 'PROPOSED_EXPANSION'}:
            raise ValueError('Source context cohort kind')
        original = expected[sid]
        source = records[row['source_ref']].get(sid) if row['source_ref'] else None
        if row['source_ref'] and (not source or source['sha256'] != row['sha256']):
            raise ValueError('Source context evidence identity mismatch')
        old = original.get('source_batch_label') or ''
        new = (source.get('source_batch_label') or '') if source else old
        contradiction = bool(old and new and old != new)
        disposition = ('SOURCE_INFORMATION_CONTRADICTORY' if contradiction else
                       'RECORDED_BATCH_ORIGIN_UNESTABLISHED' if new else
                       'NO_SUPPORTED_ACQUISITION_CONTEXT_LOCATED')
        result[sid] = dict(row, family=original.get('recorded_family', original.get('family')),
            original_batch=old or None, retained_batch=new or None,
            source_url=source.get('source_url') if source else None,
            catalog_created_at=source.get('record_created_at_utc') if source else None,
            disposition=disposition, supported_origin=None, independent_acquisition=None,
            evidence_limit='Catalog locator/batch and record creation are not acquisition receipts; absent is unknown.')
    return result


def summarize_context(rows):
    """Report context coverage without promoting a locator to an origin."""
    rows = list(rows)
    return dict(samples=len(rows), dispositions=dict(Counter(r['disposition'] for r in rows)),
                source_locators=sum(bool(r['source_url']) for r in rows),
                recorded_batch_samples=sum(bool(r['retained_batch']) for r in rows),
                supported_acquisition_origins=None, independent_acquisitions=None,
                state='ORIGINS_UNESTABLISHED; locators and components do not prove independence')
