"""Focused tests for import-surface migration guard collectors."""

from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.dev.compatibility_retirement_manifest import (
    CANONICAL_FILENAME_HEADER_BAD_ROOTS,
    CANONICAL_RELOCATION_COMPLETE_DOMAINS,
    EARLY_DEPRECATION_READY_TREES,
    LEGACY_SUBTREE_RETIREMENT_BUCKETS,
    LEGACY_TREE_RETIREMENT_MATRIX,
    LEGACY_COMPATIBILITY_IMPORT_ROOTS,
    LEGACY_LEAF_SHIM_ROOTS,
    NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST,
)
from scripts.dev import import_surface_policy as policy
from scripts.dev.compatibility_retirement_audit import (
    canonical_target_exists,
    collect_legacy_subtree_python_files,
    collect_ready_now_bucket_callers,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_collect_canonical_code_legacy_imports_flags_src_and_scripts() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(repo / "src" / "obsidiandroid" / "bad.py", "import analysis.pipeline.runner\n")
        _write(repo / "scripts" / "bad_script.py", "import analysis.pipeline.runner\n")
        _write(
            repo / "scripts" / "dev" / "check_import_surface.py",
            "import analysis.pipeline.runner\n",
        )

        assert policy.collect_canonical_code_legacy_imports(repo) == [
            "src/obsidiandroid/bad.py:1: import analysis.pipeline.runner",
            "scripts/bad_script.py:1: import analysis.pipeline.runner",
        ]


def test_guardrail_constants_are_sourced_from_retirement_manifest() -> None:
    assert policy.CANONICAL_CODE_LEGACY_IMPORT_ROOTS == frozenset(LEGACY_COMPATIBILITY_IMPORT_ROOTS)
    assert policy.ANALYSIS_PIPELINE_PLAIN_IDENTITY_SHIMS == frozenset()
    assert policy.ANALYSIS_PIPELINE_RETIRED_PACKAGE_BRIDGES
    assert policy.ANALYSIS_PIPELINE_RETIRED_PLAIN_IDENTITY_SHIMS
    assert tuple(policy.LEGACY_LEAF_SHIM_ROOTS) == LEGACY_LEAF_SHIM_ROOTS
    assert policy.NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST == frozenset(NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST)
    assert policy.CANONICAL_FILENAME_HEADER_BAD_ROOTS == frozenset(CANONICAL_FILENAME_HEADER_BAD_ROOTS)
    assert policy.READY_NOW_LEGACY_SHIM_BATCHES == frozenset(EARLY_DEPRECATION_READY_TREES)
    assert "pipeline" in CANONICAL_RELOCATION_COMPLETE_DOMAINS
    assert "feature_engineering" in CANONICAL_RELOCATION_COMPLETE_DOMAINS


def test_legacy_tree_retirement_matrix_covers_remaining_compatibility_roots() -> None:
    roots = {entry.root for entry in LEGACY_TREE_RETIREMENT_MATRIX}
    assert roots == {"analysis", "database"}
    for entry in LEGACY_TREE_RETIREMENT_MATRIX:
        assert entry.file_count > 0
        assert entry.blockers
        assert entry.next_step


def test_legacy_subtree_retirement_buckets_cover_core_legacy_surfaces() -> None:
    trees = {entry.tree for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS}
    assert "analysis/pipeline" in trees
    assert "database/split_db_health.py" in trees
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


def test_database_shims_use_shared_helper_pattern() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_database_shim_helper_violations(repo_root) == []


def test_analysis_pipeline_plain_shims_use_shared_helper_pattern() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_analysis_pipeline_plain_shim_violations(repo_root) == []


def test_retired_analysis_pipeline_plain_shims_stay_deleted() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_analysis_pipeline_retired_shim_violations(repo_root) == []


def test_retired_analysis_pipeline_package_bridges_stay_deleted() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_analysis_pipeline_retired_package_bridge_violations(repo_root) == []


def test_ml_training_plain_shims_use_shared_helper_pattern() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_ml_training_plain_shim_violations(repo_root) == []


def test_collect_nonparity_test_legacy_imports_respects_parity_allowlist() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(repo / "tests" / "test_behavior.py", "import analysis.pipeline.runner\n")
        _write(repo / "tests" / "test_legacy_shim_parity.py", "import analysis.pipeline.runner\n")

        assert policy.collect_nonparity_test_legacy_imports(repo) == [
            "tests/test_behavior.py:1: import analysis.pipeline.runner",
        ]


def test_collect_stale_canonical_filename_headers_flags_legacy_roots() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(
            repo / "src" / "obsidiandroid" / "labeling" / "bad.py",
            "# Filename: ml_classification/labeling/bad.py\n",
        )
        _write(
            repo / "src" / "obsidiandroid" / "labeling" / "good.py",
            "# Filename: src/obsidiandroid/labeling/good.py\n",
        )

        assert policy.collect_stale_canonical_filename_headers(repo) == [
            "src/obsidiandroid/labeling/bad.py: stale filename header "
            "'ml_classification/labeling/bad.py'",
        ]


def test_collect_legacy_leaf_shim_violations_requires_thin_identity_shims() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(
            repo / "analysis" / "pipeline" / "good.py",
            '"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.good``."""\n'
            "\n"
            "from __future__ import annotations\n"
            "\n"
            "import importlib\n"
            "import sys\n"
            "\n"
            '_mod = importlib.import_module("obsidiandroid.pipeline.good")\n'
            "sys.modules[__name__] = _mod\n",
        )
        _write(
            repo / "analysis" / "pipeline" / "bad_leaf.py",
            "def duplicate_logic():\n"
            "    return 1\n",
        )

        assert policy.collect_legacy_leaf_shim_violations(repo) == [
            "analysis/pipeline/bad_leaf.py: must import canonical obsidiandroid implementation",
            "analysis/pipeline/bad_leaf.py: must register ModuleType identity via sys.modules",
            "analysis/pipeline/bad_leaf.py: shim must not define 'duplicate_logic' at module level "
            "(implement under src/obsidiandroid)",
        ]


def test_collect_database_shim_helper_violations_flags_bespoke_patterns() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(
            repo / "database" / "db_utils.py",
            '"""Legacy shim."""\n'
            "import importlib\n"
            '_mod = importlib.import_module("obsidiandroid.database.db_utils")\n',
        )
        _write(
            repo / "database" / "split_db_health.py",
            "from obsidiandroid.legacy_shim_lazy import import_legacy_shim\n"
            '_canon = import_legacy_shim("obsidiandroid.database.split_db_health", "database.split_db_health")\n',
        )

        assert sorted(policy.collect_database_shim_helper_violations(repo)) == sorted(
            [
                "database/db_utils.py: database shim must use import_legacy_shim(...)",
                "database/db_utils.py: database leaf shim must register sys.modules[__name__] = _mod",
                "database/db_utils.py: database shim should not call importlib.import_module directly",
                "database/split_db_health.py: split_db_health shim must register database.split_db_health alias",
            ]
        )


def test_collect_analysis_pipeline_retired_shim_violations_flags_reintroduced_files() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(
            repo / "analysis" / "pipeline" / "artifacts" / "paths.py",
            '"""Legacy shim."""\n'
            "import importlib\n"
            '_mod = importlib.import_module("obsidiandroid.pipeline.artifacts.paths")\n',
        )
        _write(
            repo / "analysis" / "pipeline" / "manifest" / "builder.py",
            "from obsidiandroid.legacy_shim_lazy import import_legacy_shim\n"
            '_mod = import_legacy_shim("obsidiandroid.pipeline.manifest.builder", __name__)\n',
        )

        violations = policy.collect_analysis_pipeline_retired_shim_violations(repo)
        assert (
            "analysis/pipeline/artifacts/paths.py: retired plain analysis.pipeline shim should not exist on disk"
            in violations
        )
        assert (
            "analysis/pipeline/manifest/builder.py: retired plain analysis.pipeline shim should not exist on disk"
            in violations
        )


def test_collect_analysis_pipeline_retired_package_bridge_violations_flags_reintroduced_bridges() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(repo / "analysis" / "pipeline" / "artifacts" / "__init__.py", 'X = 1\n')
        _write(repo / "analysis" / "pipeline" / "manifest" / "__init__.py", 'Y = 2\n')

        violations = policy.collect_analysis_pipeline_retired_package_bridge_violations(repo)
        assert (
            "analysis/pipeline/artifacts/__init__.py: retired analysis.pipeline package bridge should not exist on disk"
            in violations
        )
        assert (
            "analysis/pipeline/manifest/__init__.py: retired analysis.pipeline package bridge should not exist on disk"
            in violations
        )


def test_collect_ml_training_plain_shim_violations_flags_bespoke_patterns() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(
            repo / "ml_classification" / "training" / "pipeline_core.py",
            '"""Legacy shim."""\n'
            "import importlib\n"
            '_mod = importlib.import_module("obsidiandroid.modeling.pipeline_core")\n',
        )
        _write(
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
