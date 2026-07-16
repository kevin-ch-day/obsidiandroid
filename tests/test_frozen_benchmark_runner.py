import pandas as pd
import pytest

from obsidiandroid.governance.frozen_benchmark_sources import SyntheticFrozenBenchmarkSourceProvider, SealedSnapshotFrozenBenchmarkSourceProvider
from obsidiandroid.governance.frozen_source_snapshot import create_synthetic_sealed_snapshot
from obsidiandroid.pipeline.frozen_benchmark_runner import evaluate_synthetic_frozen_benchmark, run_frozen_android_family_av_benchmark


def _provider():
    cohort, metadata, permissions, verdicts = [], [], [], []
    for family in range(3):
        for index in range(20):
            sample_id = family * 100 + index
            cohort.append({"sample_id": sample_id, "sha256": f"{family:02x}{index:02x}".ljust(64, "0"), "family_id": family, "family_canonical": ("alpha", "bravo", "charlie")[family], "android_package_name": f"com.synthetic.f{family}.p{index}"})
            metadata.append({"sample_id": sample_id, "meta__target_min_version": 21 if index % 2 else None, "meta__target_sdk_version": 30 if index % 3 else None})
            permissions.append({"sample_id": sample_id, "permission_string": "android.permission.CAMERA", "permission_source": "AOSP", "is_aosp_dict_match": 1, "protection_level": "DANGEROUS"})
            verdicts.extend([{"sample_id": sample_id, "engine_name": "alpha", "result": "undetected", "report_id": f"r{sample_id}", "updated_at": "2026-01-01"}, {"sample_id": sample_id, "engine_name": "beta", "result": "Trojan.X" if family else "harmless", "report_id": f"r{sample_id}", "updated_at": "2026-01-01"}])
    taxonomy = pd.DataFrame({"family_id": [0, 1, 2], "family_canonical": ["alpha", "bravo", "charlie"], "active": [True, True, True]})
    return SyntheticFrozenBenchmarkSourceProvider(pd.DataFrame(cohort), pd.DataFrame(metadata), pd.DataFrame(permissions), pd.DataFrame(verdicts), pd.DataFrame({"engine_name": ["alpha", "beta"], "active": [1, 1], "readiness_eligible_flag": [0, 0]}), taxonomy)


def test_dedicated_runner_locks_contracts_without_legacy_pipeline(tmp_path, monkeypatch):
    from obsidiandroid.features.vectorization import feature_vector_builder
    monkeypatch.setattr(feature_vector_builder, "build_feature_vector", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("parser path called")))
    context = run_frozen_android_family_av_benchmark(_provider(), run_root=tmp_path)
    assert context.lifecycle.payload["state"] == "MODELS_LOCKED"
    assert set(context.features) == {"A", "B", "C"}
    assert {"perm__android_permission_camera", "perm__known_dangerous_count"}.issubset(context.features["A"].columns)


@pytest.mark.integration
def test_synthetic_runner_executes_only_the_complete_atomic_plan(tmp_path):
    snapshot_root = tmp_path / "sealed_snapshot"
    create_synthetic_sealed_snapshot(snapshot_root)
    provider = SealedSnapshotFrozenBenchmarkSourceProvider(snapshot_root)
    context = run_frozen_android_family_av_benchmark(provider, run_root=tmp_path)
    result = evaluate_synthetic_frozen_benchmark(context, provider)
    assert result["state"] == "HELDOUT_EVALUATED"
    assert context.lifecycle.payload["classification"] == "synthetic_validation"
    assert len(result["results"]) == 15
    assert len(result["comparisons"]) == 15
    assert {entry["comparison"] for entry in result["comparisons"]} == set(context.experiment["evaluation_plan"]["paired_comparisons"])
