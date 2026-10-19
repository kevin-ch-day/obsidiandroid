"""Coverage provenance must not become permission consumption authority."""
import copy
import hashlib
import json

import pandas as pd
import pytest

from obsidiandroid.reporting.permission_coverage import (
    FORMAT, METRICS, coverage_summary, validate_coverage, consumer_availability,
)


def fixture():
    samples = pd.DataFrame({'sample_id': [1, 2], 'sha256': ['a' * 64, 'b' * 64],
                            'permission_covered': [False, True]})
    coverage = samples[['sample_id', 'sha256']].copy()
    for column in METRICS:
        coverage[column] = [1, 0]
    metadata = {'format': FORMAT, 'purpose': 'AUDIT_ONLY_NOT_CONSUMER_AUTHORITY',
                'dimensions': {column: {'state': 'OBSERVED', 'observed_utc': '2026-10-18T21:00:00Z',
                                        'source': 'fixture'} for column in METRICS}}
    return samples, coverage, metadata


def test_old_packet_unknown_is_not_zero():
    samples, _, _ = fixture()
    result = coverage_summary(samples)
    assert result[0]['state'] == 'NOT_INSPECTED'
    assert result[0]['covered_samples'] is None
    assert result[0]['no_rows_in_inspected_surface'] is None
    assert result[-1]['covered_samples'] == 1


def test_upstream_coverage_does_not_change_export_membership():
    samples, coverage, metadata = fixture()
    validate_coverage(samples, coverage, metadata)
    result = coverage_summary(samples.iloc[:1], coverage, metadata)
    assert result[0]['covered_samples'] == result[0]['denominator'] == 1
    assert result[-1]['covered_samples'] == 0
    assert samples.permission_covered.tolist() == [False, True]


def test_inaccessible_is_not_absent():
    samples, coverage, metadata = fixture()
    metadata['dimensions']['pi_canonical_rows'] = {'state': 'INACCESSIBLE'}
    coverage['pi_canonical_rows'] = ''
    validate_coverage(samples, coverage, metadata)
    result = coverage_summary(samples, coverage, metadata)[1]
    assert result['state'] == 'INACCESSIBLE' and result['covered_samples'] is None
    coverage['pi_canonical_rows'] = 0
    with pytest.raises(ValueError, match='must not contain counts'):
        validate_coverage(samples, coverage, metadata)


def test_wrong_or_partial_identity_population_fails():
    samples, coverage, metadata = fixture()
    for changed in [coverage.iloc[:1], coverage.assign(sha256=['b' * 64, 'a' * 64]),
                    pd.concat([coverage, coverage.iloc[:1]])]:
        with pytest.raises(ValueError, match='identities|disagreement'):
            validate_coverage(samples, changed, metadata)


def test_invalid_counts_and_missing_provenance_fail():
    samples, coverage, metadata = fixture()
    for value in [-1, 0.5, '', float('inf'), 'nan', 'bad', True]:
        changed = coverage.copy().astype({'pi_observation_rows': object})
        changed.loc[0, 'pi_observation_rows'] = value
        with pytest.raises(ValueError, match='counts'):
            validate_coverage(samples, changed, metadata)
    altered = copy.deepcopy(metadata)
    altered['dimensions']['pi_canonical_rows'].pop('source')
    with pytest.raises(ValueError, match='provenance'):
        validate_coverage(samples, coverage, altered)
    coverage.loc[0, 'pi_canonical_rows'] = 2
    with pytest.raises(ValueError, match='exceeds'):
        validate_coverage(samples, coverage, metadata)


def test_packet_loader_requires_checksum_and_coverage_metadata(tmp_path):
    from obsidiandroid.reporting.integrated_research import FORMAT as PACKET_FORMAT, ResearchPacket

    samples, coverage, metadata = fixture()
    samples.to_csv(tmp_path / 'SAMPLES.csv', index=False)
    samples[['sample_id', 'sha256']].iloc[:0].to_csv(tmp_path / 'PERMISSIONS.csv', index=False)
    coverage.to_csv(tmp_path / 'PI_COVERAGE.csv', index=False)
    manifest = {'format': PACKET_FORMAT, 'permission_coverage_audit': metadata,
                'files': {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                          for name in ('SAMPLES.csv', 'PERMISSIONS.csv', 'PI_COVERAGE.csv')}}
    manifest_path = tmp_path / 'RESEARCH_MANIFEST.json'
    manifest_path.write_text(json.dumps(manifest))
    assert ResearchPacket(tmp_path).coverage.pi_observation_rows.tolist() == [1, 0]
    (tmp_path / 'PI_COVERAGE.csv').write_text('changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        ResearchPacket(tmp_path)
    manifest.pop('permission_coverage_audit')
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='metadata missing'):
        ResearchPacket(tmp_path)


def test_optional_levels_need_counts_and_provenance_together():
    samples, coverage, metadata = fixture()
    coverage['pi_adapter_gap_rows'] = [1, 0]
    with pytest.raises(ValueError, match='access state'):
        validate_coverage(samples, coverage, metadata)
    metadata['dimensions']['pi_adapter_gap_rows'] = dict(metadata['dimensions']['pi_observation_rows'])
    validate_coverage(samples, coverage, metadata)
    matrix = coverage_summary(samples, coverage, metadata)
    gap = next(row for row in matrix if row['dimension'] == 'Governed concept omitted by coarse adapter')
    assert gap['covered_samples'] == gap['evidence_rows'] == 1
    assert samples.permission_covered.tolist() == [False, True]
    with pytest.raises(ValueError, match='columns'):
        validate_coverage(samples, coverage.drop(columns='pi_adapter_gap_rows'), metadata)
    coverage['pi_adapter_gap_rows'] = [2, 0]
    with pytest.raises(ValueError, match='exceeds'):
        validate_coverage(samples, coverage, metadata)


def test_consumer_exclusion_is_independent_of_resolution():
    samples, coverage, metadata = fixture()
    validate_coverage(samples, coverage, metadata)
    result = consumer_availability(samples.iloc[:1], coverage, metadata)
    assert result['upstream_observed_outside_export'] == 1
    assert result['frozen_export_members'] == 0
    assert result['current_approval'] == 'NOT_CHECKED_BY_FROZEN_BROWSER'
    assert result['permission_training_authorized'] is False
    assert 'separately approved' in result['reason']
    absent = consumer_availability(samples.iloc[:0], coverage, metadata)
    assert absent['catalog_samples'] == absent['upstream_observed_outside_export'] == 0
    member = consumer_availability(samples.iloc[1:], coverage, metadata)
    assert member['frozen_export_members'] == 1
    assert member['permission_training_authorized'] is False


def test_unknown_upstream_cannot_be_presented_as_no_evidence():
    samples, coverage, metadata = fixture()
    assert consumer_availability(samples)['upstream_observed_outside_export'] is None
    metadata['dimensions']['pi_observation_rows'] = {'state': 'INACCESSIBLE'}
    coverage['pi_observation_rows'] = ''
    validate_coverage(samples, coverage, metadata)
    result = consumer_availability(samples, coverage, metadata)
    assert result['upstream_state'] == 'INACCESSIBLE'
    assert result['no_rows_in_inspected_upstream_outside_export'] is None


def test_bad_metadata_and_count_overflow_abstain():
    samples, coverage, metadata = fixture()
    altered = copy.deepcopy(metadata)
    altered['dimensions']['unknown_dimension'] = {'state': 'OBSERVED'}
    with pytest.raises(ValueError, match='Unsupported'):
        validate_coverage(samples, coverage, altered)
    altered = copy.deepcopy(metadata)
    altered['dimensions']['pi_observation_rows']['observed_utc'] = '2026-10-18'
    with pytest.raises(ValueError, match='UTC provenance'):
        validate_coverage(samples, coverage, altered)
    coverage['pi_observation_rows'] = [1e30, 0]
    with pytest.raises(ValueError, match='counts'):
        validate_coverage(samples, coverage, metadata)
