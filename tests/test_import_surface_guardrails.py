"""Focused tests for import-surface migration guard collectors."""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

import pytest
from scripts.dev import import_surface_policy as policy


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


def test_legacy_import_guardrails_have_concrete_retirement_rules() -> None:
    assert policy.CANONICAL_CODE_LEGACY_IMPORT_ROOTS == frozenset(
        {"analysis", "ml_classification", "main"}
    )
    assert policy.RETIRED_COMPATIBILITY_ROOTS == frozenset({"analysis", "ml_classification"})
    assert policy.RETIRED_ROOT_COMPATIBILITY_FILES == frozenset(
        {Path("database/__init__.py"), Path("database/split_db_health.py")}
    )
    assert policy.CANONICAL_FILENAME_HEADER_BAD_ROOTS == frozenset(
        {"analysis", "ml_classification", "database"}
    )


def test_retired_root_compatibility_files_stay_deleted() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_retired_compatibility_file_violations(repo_root) == []


def test_retired_compatibility_trees_stay_deleted() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert policy.collect_retired_compatibility_tree_violations(repo_root) == []


def test_analysis_namespace_is_retired() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("analysis")


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
