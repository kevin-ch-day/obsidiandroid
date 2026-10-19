"""Profile control for the train/test split grouping policy."""

from __future__ import annotations

import pytest

from obsidiandroid.pipeline import runtime_policy


def test_profiles_without_split_grouping_keep_ungrouped_default() -> None:
    assert runtime_policy.resolve_split_grouping({}) == "none"


def test_profile_can_request_package_grouping() -> None:
    assert runtime_policy.resolve_split_grouping({"split_grouping": "Package"}) == "package"


def test_profile_split_grouping_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="split_grouping"):
        runtime_policy.resolve_split_grouping({"split_grouping": "lineage"})


def test_split_grouping_is_restored_after_each_run() -> None:
    assert "TRAIN_TEST_SPLIT_GROUPING" in runtime_policy.build_mutable_config_keys()
