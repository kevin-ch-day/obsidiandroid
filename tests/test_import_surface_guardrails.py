"""Focused tests for import-surface migration guard collectors."""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

import pytest
from scripts.dev.compatibility_retirement_manifest import (
    CANONICAL_CODE_COMPATIBILITY_IMPORT_ROOTS,
    CANONICAL_FILENAME_HEADER_BAD_ROOTS,
    CANONICAL_RELOCATION_COMPLETE_DOMAINS,
    EARLY_DEPRECATION_READY_TREES,
    LEGACY_SUBTREE_RETIREMENT_BUCKETS,
    LEGACY_TREE_RETIREMENT_MATRIX,
    LEGACY_COMPATIBILITY_IMPORT_ROOTS,
    NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST,
    RETIRED_COMPATIBILITY_ROOTS,
    RETIRED_ROOT_COMPATIBILITY_FILES,
)
from scripts.dev import import_surface_policy as policy
from scripts.dev.compatibility_retirement_audit import (
    canonical_target_exists,
    collect_legacy_subtree_python_files,
    collect_ready_now_bucket_callers,
)


def test_collect_canonical_code_legacy_imports_flags_src_and_scripts(write_text_file) -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        write_text_file(repo / "src" / "obsidiandroid" / "bad.py", "import analysis.pipeline.runner\n")
        write_text_file(repo / "scripts" / "bad_script.py", "import analysis.pipeline.runner\n")
        write_text_file(repo / "src" / "obsidiandroid" / "bad_main.py", "from main import run_pipeline\n")
        write_text_file(
            repo / "scripts" / "dev" / "check_import_surface.py",
            "import analysis.pipeline.runner\n",
        )

        assert policy.collect_canonical_code_legacy_imports(repo) == [
            "src/obsidiandroid/bad.py:1: import analysis.pipeline.runner",
            "src/obsidiandroid/bad_main.py:1: from main import ...",
            "scripts/bad_script.py:1: import analysis.pipeline.runner",
        ]


def test_guardrail_constants_are_sourced_from_retirement_manifest() -> None:
    assert policy.CANONICAL_CODE_LEGACY_IMPORT_ROOTS == frozenset(CANONICAL_CODE_COMPATIBILITY_IMPORT_ROOTS)
    assert policy.RETIRED_COMPATIBILITY_ROOTS == frozenset(RETIRED_COMPATIBILITY_ROOTS)
    assert policy.RETIRED_ROOT_COMPATIBILITY_FILES == frozenset(RETIRED_ROOT_COMPATIBILITY_FILES)
    assert policy.NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST == frozenset(NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST)
    assert policy.CANONICAL_FILENAME_HEADER_BAD_ROOTS == frozenset(CANONICAL_FILENAME_HEADER_BAD_ROOTS)
    assert policy.READY_NOW_LEGACY_SHIM_BATCHES == frozenset(EARLY_DEPRECATION_READY_TREES)
    assert "pipeline" in CANONICAL_RELOCATION_COMPLETE_DOMAINS
    assert "feature_engineering" in CANONICAL_RELOCATION_COMPLETE_DOMAINS


def test_legacy_tree_retirement_matrix_has_no_remaining_compatibility_roots() -> None:
    roots = {entry.root for entry in LEGACY_TREE_RETIREMENT_MATRIX}
    assert roots == set()
    for entry in LEGACY_TREE_RETIREMENT_MATRIX:
        assert entry.file_count > 0
        assert entry.blockers
        assert entry.next_step


def test_legacy_subtree_retirement_buckets_cover_core_legacy_surfaces() -> None:
    trees = {entry.tree for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS}
    assert "analysis/pipeline" not in trees
    assert "database/split_db_health.py" not in trees
    assert "ml_classification/builder" not in trees
    assert "ml_classification/engine_weights" not in trees
    assert "ml_classification/inference" not in trees
    assert "ml_classification/labeling" not in trees
    assert "analysis/diagnostics" not in trees
    assert "analysis/evaluation" not in trees
    assert "analysis/execution" not in trees
    assert "analysis/vendor_processing" not in trees
    for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        assert entry.canonical_target.startswith("obsidiandroid.")
        assert entry.file_count > 0
        assert entry.bucket
        assert entry.readiness
        assert entry.next_step


def test_legacy_subtree_retirement_targets_exist_and_ready_batches_have_files() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        assert canonical_target_exists(repo_root, entry.canonical_target), entry.canonical_target
        files = collect_legacy_subtree_python_files(repo_root, entry.tree)
        assert len(files) == entry.file_count


def test_early_deprecation_ready_buckets_have_no_external_legacy_import_callers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    callers = collect_ready_now_bucket_callers(repo_root)
    assert set(callers) == set(EARLY_DEPRECATION_READY_TREES)
    assert callers == {}


def test_ready_now_shims_use_shared_helper_and_warning_pattern() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_ready_now_shim_helper_violations(repo_root) == []


def test_retired_root_compatibility_files_stay_deleted() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_retired_compatibility_file_violations(repo_root) == []


def test_retired_compatibility_trees_stay_deleted() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_retired_compatibility_tree_violations(repo_root) == []


def test_analysis_namespace_is_retired() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("analysis")


def test_ml_training_plain_shims_use_shared_helper_pattern() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_ml_training_plain_shim_violations(repo_root) == []


def test_collect_nonparity_test_legacy_imports_flags_retired_imports(write_text_file) -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        write_text_file(repo / "tests" / "test_behavior.py", "import analysis.pipeline.runner\n")
        write_text_file(repo / "tests" / "test_legacy_shim_parity.py", "import analysis.pipeline.runner\n")

        assert policy.collect_nonparity_test_legacy_imports(repo) == [
            "tests/test_behavior.py:1: import analysis.pipeline.runner",
            "tests/test_legacy_shim_parity.py:1: import analysis.pipeline.runner",
        ]


def test_collect_stale_canonical_filename_headers_flags_legacy_roots(write_text_file) -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        write_text_file(
            repo / "src" / "obsidiandroid" / "labeling" / "bad.py",
            "# Filename: ml_classification/labeling/bad.py\n",
        )
        write_text_file(
            repo / "src" / "obsidiandroid" / "labeling" / "good.py",
            "# Filename: src/obsidiandroid/labeling/good.py\n",
        )

        assert policy.collect_stale_canonical_filename_headers(repo) == [
            "src/obsidiandroid/labeling/bad.py: stale filename header "
            "'ml_classification/labeling/bad.py'",
        ]


def test_collect_retired_compatibility_file_violations_flags_reintroduced_files(write_text_file) -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        write_text_file(repo / "database" / "__init__.py", '"""Retired compatibility root."""\n')
        write_text_file(repo / "database" / "split_db_health.py", '"""Retired compatibility entrypoint."""\n')

        assert policy.collect_retired_compatibility_file_violations(repo) == [
            "database/__init__.py: retired compatibility file should not exist on disk",
            "database/split_db_health.py: retired compatibility file should not exist on disk",
        ]


def test_collect_retired_compatibility_tree_violations_flags_reintroduced_roots(write_text_file) -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        write_text_file(repo / "analysis" / "pipeline" / "runner.py", '"""Legacy shim."""\n')
        write_text_file(repo / "ml_classification" / "__init__.py", '"""Legacy shim."""\n')

        assert policy.collect_retired_compatibility_tree_violations(repo) == [
            "analysis: retired compatibility tree should not exist on disk",
            "ml_classification: retired compatibility tree should not exist on disk",
        ]


def test_collect_ml_training_plain_shim_violations_flags_bespoke_patterns(write_text_file) -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        write_text_file(
            repo / "ml_classification" / "training" / "pipeline_core.py",
            '"""Legacy shim."""\n'
            "import importlib\n"
            '_mod = importlib.import_module("obsidiandroid.modeling.pipeline_core")\n',
        )
        write_text_file(
            repo / "ml_classification" / "training" / "model_prediction.py",
            "from obsidiandroid.legacy_shim_lazy import import_legacy_shim\n"
            '_canonical = import_legacy_shim("obsidiandroid.modeling.model_prediction", __name__)\n',
        )

        violations = policy.collect_ml_training_plain_shim_violations(repo)
        assert (
            "ml_classification/training/pipeline_core.py: plain ml_classification.training shim must use "
            "import_legacy_shim(...)" in violations
        )
        assert (
            "ml_classification/training/pipeline_core.py: plain ml_classification.training shim must register "
            "sys.modules[__name__] alias" in violations
        )
        assert (
            "ml_classification/training/pipeline_core.py: plain ml_classification.training shim should not use "
            "direct importlib import patterns" in violations
        )
        assert (
            "ml_classification/training/model_prediction.py: plain ml_classification.training shim must register "
            "sys.modules[__name__] alias" in violations
        )
