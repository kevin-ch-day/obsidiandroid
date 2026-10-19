"""Denominators, source abstention and identity binding for offline reports."""
from copy import deepcopy
import pytest
from obsidiandroid.reporting.permission_descriptive_research import describe_permissions


def fixture():
    members = [dict(sample_id=i, sha256=str(i)*64, family='A', temporal_eligible=i == 1,
                    first_submission_utc='2020-01-01T00:00:00+00:00',
                    last_analysis_utc='2021-01-01T00:00:00+00:00') for i in (1, 2)]
    rows = [dict(obs_id=i, sample_id=i, sha256=str(i)*64, family='A', exact_token='P',
                 source_correspondence_verified=i == 1, accepted_identity=True,
                 canonical_identity='P', resolution_status='RESOLVED_EXACT', protection_base='normal')
            for i in (1, 2)]
    return rows, members


def test_sample_denominator_and_projection_abstention():
    rows, members = fixture()
    duplicate_token = deepcopy(rows[0]); duplicate_token['obs_id'] = 3
    result = describe_permissions(rows + [duplicate_token], members)
    assert result['prevalence'][0]['samples'] == 1
    assert result['prevalence'][0]['sample_denominator'] == 2
    assert result['temporal'][0]['sample_denominator'] == 1
    assert result['families'][0]['observations'] == 3


@pytest.mark.parametrize('mutation', ['sha', 'family', 'duplicate', 'missing', 'timestamp', 'canonical'])
def test_reject_bad_binding_and_invalid_dates(mutation):
    rows, members = fixture()
    if mutation == 'sha': rows[0]['sha256'] = 'x'*64
    if mutation == 'family': rows[0]['family'] = 'B'
    if mutation == 'duplicate': rows.append(deepcopy(rows[0]))
    if mutation == 'missing': rows.pop()
    if mutation == 'timestamp': members[0]['first_submission_utc'] = '2022-01-01T00:00:00+00:00'
    if mutation == 'canonical': rows[0]['canonical_identity'] = None
    with pytest.raises(ValueError): describe_permissions(rows, members)
