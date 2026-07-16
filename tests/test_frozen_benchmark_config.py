import pytest

from obsidiandroid.governance.frozen_benchmark_config import load_frozen_cohort_profile, load_frozen_experiment
from obsidiandroid.governance.frozen_benchmark_sources import DatabaseFrozenBenchmarkSourceProvider


def test_frozen_profile_and_experiment_are_complete_and_explicit():
    profile = load_frozen_cohort_profile()
    experiment = load_frozen_experiment()
    assert profile["cohort_policy"]["min_total_support"] == 20
    assert experiment["parser_policy"] == "disabled"
    assert experiment["evaluation_plan"]["arms"] == ["A", "B", "C"]


def test_live_provider_is_blocked_before_schema_preflight():
    with pytest.raises(RuntimeError, match="LIVE_SCHEMA_UNVERIFIED"):
        DatabaseFrozenBenchmarkSourceProvider()
