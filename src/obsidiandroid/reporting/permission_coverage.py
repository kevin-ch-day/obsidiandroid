"""Frozen upstream coverage diagnostics, separate from permission consumption."""
from __future__ import annotations

from datetime import datetime

import pandas as pd


FORMAT = 'obsidiandroid-pi-coverage-audit-v1'
METRICS = {
    'pi_observation_rows': 'Retained PI observations',
    'pi_canonical_rows': 'Exact accepted catalog identity',
    'pi_classified_rows': 'Current non-UNKNOWN operational classification',
    'pi_stamped_rows': 'Stored recovery authority stamp',
    'pi_source_members': 'Exact V2 source members',
    'pi_manifest_rows': 'Observations labeled apk_manifest',
}
LEVEL_METRICS = {
    'pi_protection_rows': 'Current explicit protection base',
    'pi_governed_permission_rows': 'Scoped permission authority interpretation',
    'pi_source_asserted_rows': 'Source-asserted evidence (verification separate)',
    'pi_pattern_rows': 'Pattern-only evidence',
    'pi_provisional_rows': 'Provisional evidence',
    'pi_unresolved_rows': 'Unresolved identity interpretation',
    'pi_nonpermission_rows': 'Governed non-permission interpretation',
    'pi_adapter_gap_rows': 'Governed concept omitted by coarse adapter',
    'pi_replay_changed_rows': 'Stored versus token-only replay difference',
}
STATES = {'OBSERVED', 'INACCESSIBLE', 'NOT_INSPECTED'}


def validate_coverage(samples, coverage, metadata):
    """Require complete identity alignment and explicit per-dimension provenance.

    Checksums are checked by the packet reader. Neither checksums nor this
    structural validation confer permission feature or source authority.
    """
    if (not isinstance(metadata, dict) or metadata.get('format') != FORMAT
            or metadata.get('purpose') != 'AUDIT_ONLY_NOT_CONSUMER_AUTHORITY'):
        raise ValueError('Unsupported permission coverage contract')
    if not isinstance(metadata.get('dimensions'), dict):
        raise ValueError('Permission coverage dimensions missing')
    dimensions = metadata['dimensions']
    if set(dimensions) - (METRICS.keys() | LEVEL_METRICS.keys()):
        raise ValueError('Unsupported permission coverage dimension')
    optional = LEVEL_METRICS.keys() & (set(coverage.columns) | dimensions.keys())
    requested = METRICS.keys() | optional
    required = {'sample_id', 'sha256', *requested}
    if not required.issubset(coverage.columns):
        raise ValueError('Incomplete permission coverage columns')
    if coverage.sample_id.duplicated().any() or coverage.sha256.duplicated().any():
        raise ValueError('Duplicate permission coverage identities')
    if set(zip(coverage.sample_id, coverage.sha256)) != set(zip(samples.sample_id, samples.sha256)):
        raise ValueError('Permission coverage ID/SHA population disagreement')
    for column in requested:
        source = metadata.get('dimensions', {}).get(column, {})
        if not isinstance(source, dict):
            raise ValueError('Invalid permission coverage provenance')
        state = source.get('state')
        if state not in STATES:
            raise ValueError('Unknown permission coverage access state')
        values = coverage[column]
        if state == 'OBSERVED':
            if not isinstance(source.get('source'), str) or not source['source'].strip():
                raise ValueError('Permission coverage provenance missing')
            try:
                at = datetime.fromisoformat(source['observed_utc'].replace('Z', '+00:00'))
                if at.utcoffset() is None or at.utcoffset().total_seconds() != 0:
                    raise ValueError('UTC timestamp required')
            except (KeyError, AttributeError, TypeError, ValueError) as exc:
                raise ValueError('Permission coverage UTC provenance missing') from exc
            numeric = pd.to_numeric(values, errors='coerce')
            if (values.map(lambda value: isinstance(value, bool)).any()
                    or numeric.isna().any() or (numeric < 0).any()
                    or (numeric > 2**63 - 1).any()
                    or (numeric % 1 != 0).any()):
                raise ValueError('Invalid permission coverage counts')
            coverage[column] = numeric.astype('int64')
        elif not values.eq('').all():
            raise ValueError('Unavailable coverage must not contain counts')
    observations = metadata['dimensions']['pi_observation_rows']['state']
    for column in requested - {'pi_observation_rows', 'pi_source_members'}:
        if observations == metadata['dimensions'][column]['state'] == 'OBSERVED':
            if (coverage[column] > coverage.pi_observation_rows).any():
                raise ValueError('Permission coverage exceeds observation population')


def coverage_summary(samples, coverage=None, metadata=None):
    """Report selected sample denominators; unavailable evidence stays unknown."""
    rows = []
    for column, label in {**METRICS, **LEVEL_METRICS}.items():
        source = (metadata or {}).get('dimensions', {}).get(column, {})
        state = source.get('state', 'NOT_INSPECTED')
        count = total = absent = None
        if coverage is not None and state == 'OBSERVED':
            selected = coverage[coverage.sample_id.isin(samples.sample_id)]
            count = int(selected[column].gt(0).sum())
            total = int(selected[column].sum())
            absent = len(selected) - count
        rows.append({'dimension': label, 'state': state,
                     'covered_samples': count, 'denominator': len(samples),
                     'no_rows_in_inspected_surface': absent, 'evidence_rows': total,
                     'source': source.get('source', ''),
                     'observed_utc': source.get('observed_utc', '')})
    approved = int(samples.permission_covered.eq(True).sum())
    rows.append({'dimension': 'Approved PI export membership', 'state': 'FROZEN_EXPORT',
                 'covered_samples': approved, 'denominator': len(samples),
                 'outside_export': len(samples) - approved,
                 'meaning': 'Outside export does not establish absent upstream evidence'})
    return rows


def consumer_availability(samples, coverage=None, metadata=None):
    """Explain frozen export exclusion without inventing current approval.

    Upstream audit authority and export membership are independent. An absent
    canonical definition does not mean an APK has no permission usage.
    """
    approved = samples.permission_covered.eq(True)
    result = {
        'catalog_samples': len(samples),
        'frozen_export_members': int(approved.sum()),
        'outside_frozen_export': int((~approved).sum()),
        'upstream_observed_outside_export': None,
        'no_rows_in_inspected_upstream_outside_export': None,
        'upstream_state': 'NOT_INSPECTED',
        'current_approval': 'NOT_CHECKED_BY_FROZEN_BROWSER',
        'permission_training_authorized': False,
        'reason': 'Frozen export membership does not establish current approval; audit coverage grants no consumer authority.',
    }
    state = (metadata or {}).get('dimensions', {}).get('pi_observation_rows', {}).get('state', 'NOT_INSPECTED')
    result['upstream_state'] = state
    if coverage is not None and state == 'OBSERVED':
        subset = samples[['sample_id', 'sha256', 'permission_covered']].merge(
            coverage[['sample_id', 'sha256', 'pi_observation_rows']],
            on=['sample_id', 'sha256'], validate='one_to_one')
        outside = subset[~subset.permission_covered.eq(True)]
        result['upstream_observed_outside_export'] = int(outside.pi_observation_rows.gt(0).sum())
        result['no_rows_in_inspected_upstream_outside_export'] = int(outside.pi_observation_rows.eq(0).sum())
        if result['upstream_observed_outside_export']:
            result['reason'] = (
                'Upstream observations exist outside the frozen approved export. '
                'A separately approved, identity-bound descriptive consumer contract '
                'is required; canonical resolution or a replay label cannot substitute for approval.')
    return result
