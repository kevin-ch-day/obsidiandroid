import pandas as pd

from obsidiandroid.modeling import dataset_splitter


def test_balanced_train_test_split_keeps_singleton_classes_out_of_test() -> None:
    X = pd.DataFrame({"f": range(10)})
    y = pd.Series(
        [
            0,
            0,
            0,
            1,
            1,
            1,
            2,
            2,
            3,
            4,
        ],
        index=X.index,
    )

    X_train, X_test, y_train, y_test = dataset_splitter.balanced_train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        min_test_per_class=1,
    )

    assert 3 in set(y_train.tolist())
    assert 4 in set(y_train.tolist())
    assert 3 not in set(y_test.tolist())
    assert 4 not in set(y_test.tolist())
    assert set(y_test.tolist()) <= {0, 1, 2}


def test_balanced_train_test_split_stratifies_non_singleton_remainder() -> None:
    X = pd.DataFrame({"f": range(9)})
    y = pd.Series([0, 0, 1, 1, 2, 2, 3, 3, 4], index=X.index)

    X_train, X_test, y_train, y_test = dataset_splitter.balanced_train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=7,
        min_test_per_class=1,
    )

    assert 4 in set(y_train.tolist())
    assert 4 not in set(y_test.tolist())
    for klass in (0, 1, 2, 3):
        assert klass in set(y_train.tolist())
        assert klass in set(y_test.tolist())
