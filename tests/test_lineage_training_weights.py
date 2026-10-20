import pandas as pd
import pytest

from obsidiandroid.modeling.lineage_training_weights import lineage_class_weights


def test_equal_family_and_within_family_lineage_mass():
    data = pd.DataFrame({'recorded_family': ['A'] * 5 + ['B'],
                         'lineage_component': [1, 1, 1, 1, 2, 3]},
                        index=[11, 12, 13, 14, 15, 16])
    weights = lineage_class_weights(data)
    assert weights.index.equals(data.index)
    assert weights.sum() == pytest.approx(6)
    assert weights.loc[11:15].sum() == pytest.approx(weights.loc[16])
    assert weights.loc[11:14].sum() == pytest.approx(weights.loc[15])


def test_only_passed_training_rows_define_mass_and_mixed_labels_are_kept():
    data = pd.DataFrame({'recorded_family': ['A', 'A', 'B', 'B'],
                         'lineage_component': [1, 2, 2, 3]}, index=[1, 2, 3, 4])
    first = lineage_class_weights(data.loc[[1, 2, 3]])
    data.loc[4] = ['UNSEEN', 999]
    pd.testing.assert_series_equal(first, lineage_class_weights(data.loc[[1, 2, 3]]))
    assert first.loc[1] == pytest.approx(first.loc[2])
    assert first.loc[3] == pytest.approx(first.loc[1] + first.loc[2])


@pytest.mark.parametrize('data', [
    pd.DataFrame(),
    pd.DataFrame({'recorded_family': ['A', 'B'], 'lineage_component': [1, 2]}, index=[1, 1]),
    pd.DataFrame({'recorded_family': ['A'], 'lineage_component': [None]}),
    pd.DataFrame({'recorded_family': [''], 'lineage_component': [1]}),
])
def test_invalid_training_membership_fails(data):
    with pytest.raises(ValueError):
        lineage_class_weights(data)
