import pytest

from obsidiandroid.pipeline.runner import run_pipeline


def test_legacy_runner_rejects_frozen_abc_experiment_before_any_work():
    with pytest.raises(RuntimeError, match="run_frozen_android_family_av_benchmark"):
        run_pipeline(experiment_id="android_family_av_abc_v1")
