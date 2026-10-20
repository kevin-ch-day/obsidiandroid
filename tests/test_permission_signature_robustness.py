"""Lineage weighting must expose duplicate dominance rather than create support."""
import pytest
from obsidiandroid.reporting.permission_signature_robustness import lineage_signature


def test_dominant_related_samples_do_not_become_independent_support():
    population = [dict(sample_id=i, lineage_component='a' if i < 9 else 'b') for i in range(10)]
    result = lineage_signature(population, set(range(9)))
    assert result['sample_prevalence'] == .9
    assert result['equal_component_prevalence'] == .5
    assert result['positive_components'] == 1
    assert result['leave_one_out_low'] == 0
    assert result['leave_one_out_high'] == 1
    assert result == lineage_signature(population, set(range(9)))


def test_missing_group_does_not_count_as_independence():
    result = lineage_signature([dict(sample_id=1, lineage_component=''),
                                dict(sample_id=2, lineage_component='a')], {1})
    assert result['missing_lineage_samples'] == 1
    assert result['components'] == 1 and result['bootstrap_low'] is None
    assert result['equal_component_prevalence'] == 0


def test_duplicate_identity_fails():
    with pytest.raises(ValueError):
        lineage_signature([dict(sample_id=1)]*2, {1})
