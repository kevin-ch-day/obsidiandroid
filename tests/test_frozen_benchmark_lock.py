import pandas as pd
import pytest

from obsidiandroid.common.family_label_semantics import is_family_placeholder_token
from obsidiandroid.governance.frozen_benchmark_lock import create_frozen_group_split, freeze_cohort


def _frame() -> pd.DataFrame:
    rows = []
    for family_id, prefix in [(1, "a"), (2, "b")]:
        for index in range(20):
            rows.append({
                "sample_id": family_id * 100 + index,
                "sha256": f"{family_id:02x}{index:02x}".ljust(64, "0"),
                "family_id": family_id,
                "family_canonical": f"group_{prefix}",
                "android_package_name": f"com.example.{prefix}{index}",
            })
    return pd.DataFrame(rows)


def test_freeze_and_group_split_are_deterministic() -> None:
    lock = freeze_cohort(_frame())
    split = create_frozen_group_split(lock)
    assert set(split.split_role) == {"train", "test"}
    assert (split.groupby("family_id").size() >= 20).all()
    assert split.groupby("family_id").apply(lambda part: (part.split_role == "test").sum()).min() >= 4


def test_cross_family_package_component_fails_lock() -> None:
    frame = _frame()
    frame.loc[0, "android_package_name"] = frame.loc[20, "android_package_name"]
    with pytest.raises(ValueError, match="CROSS_FAMILY_COMPONENT"):
        freeze_cohort(frame)


def test_numeric_placeholder_fails_lock() -> None:
    frame = _frame()
    frame.loc[0, "family_canonical"] = "123"
    with pytest.raises(ValueError, match="placeholder"):
        freeze_cohort(frame)


@pytest.mark.parametrize("value", ["123", "family_123", "family_id_123", "unresolved_family_123", "unresolved_family_id_123"])
def test_declared_placeholder_forms_are_rejected(value: str) -> None:
    assert is_family_placeholder_token(value)
