"""Focused tests for import-surface migration guard collectors."""

from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.dev import check_import_surface as surface


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_collect_canonical_code_legacy_imports_flags_src_and_scripts() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(repo / "src" / "obsidiandroid" / "bad.py", "from utils import hash_utils\n")
        _write(repo / "scripts" / "bad_script.py", "import analysis.pipeline.runner\n")
        _write(
            repo / "scripts" / "dev" / "check_import_surface.py",
            "import analysis.pipeline.runner\n",
        )

        assert surface.collect_canonical_code_legacy_imports(repo) == [
            "src/obsidiandroid/bad.py:1: from utils import ...",
            "scripts/bad_script.py:1: import analysis.pipeline.runner",
        ]


def test_collect_nonparity_test_legacy_imports_respects_parity_allowlist() -> None:
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        _write(repo / "tests" / "test_behavior.py", "import ml_classification.training.pipeline_core\n")
        _write(repo / "tests" / "test_obsidiandroid_package_surface.py", "import utils.exporting\n")

        assert surface.collect_nonparity_test_legacy_imports(repo) == [
            "tests/test_behavior.py:1: import ml_classification.training.pipeline_core",
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

        assert surface.collect_stale_canonical_filename_headers(repo) == [
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
            repo / "model" / "core" / "bad.py",
            "def duplicate_logic():\n"
            "    return 1\n",
        )

        assert surface.collect_legacy_leaf_shim_violations(repo) == [
            "model/core/bad.py: must import canonical obsidiandroid implementation",
            "model/core/bad.py: must register ModuleType identity via sys.modules",
            "model/core/bad.py: shim must not define 'duplicate_logic' at module level "
            "(implement under src/obsidiandroid)",
        ]
