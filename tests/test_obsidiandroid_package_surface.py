"""Checks for the canonical ``obsidiandroid.*`` package surface."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile

import pytest


def test_vendors_and_evaluation_public_entrypoints_exist() -> None:
    import importlib

    import obsidiandroid.evaluation as eval_pkg
    import obsidiandroid.vendors as vendors_pkg

    vcp = importlib.import_module("obsidiandroid.evaluation.vendor_classification_parser")
    generic = importlib.import_module("obsidiandroid.vendors.parsing.generic_label_parser")

    assert eval_pkg.parse_vendor_classifications is vcp.parse_vendor_classifications
    assert vendors_pkg.parse_generic_classification is generic.parse_generic_classification

    # Evaluation return contract: named result object that still supports tuple unpacking.
    assert eval_pkg.VendorClassificationParseResult is vcp.VendorClassificationParseResult


def test_observability_package_reexports_logging() -> None:
    """``obsidiandroid.observability`` re-exports ``get_logger`` / ``log_event``."""
    import obsidiandroid.observability as obs
    import obsidiandroid.observability.logging as olog

    assert obs.get_logger is olog.get_logger
    assert obs.log_event is olog.log_event


def test_common_repo_paths_ensure_is_idempotent() -> None:
    """Repeated calls must not duplicate the checkout ``src`` entry."""
    import sys
    from pathlib import Path

    from obsidiandroid.common import repo_paths

    here = Path(repo_paths.__file__).resolve()
    if len(here.parents) < 3 or here.parents[2].name != "src":
        pytest.skip("repo_paths not loaded from a checkout tree under src/")
    src = str(here.parents[2])
    repo_paths.ensure_repo_src_on_sys_path()
    repo_paths.ensure_repo_src_on_sys_path()
    assert sys.path.count(src) == 1


def test_repo_operator_script_resolves_under_repo_root() -> None:
    from pathlib import Path

    from obsidiandroid.common import repo_paths

    here = Path(repo_paths.__file__).resolve()
    if len(here.parents) < 4 or here.parents[2].name != "src":
        pytest.skip("repo_paths not loaded from a checkout tree under src/")
    root = here.parents[3]
    p = repo_paths.repo_operator_script("dev", "check_import_surface.py")
    assert p == root / "scripts" / "dev" / "check_import_surface.py"
    assert p.is_file()


def test_prepare_script_runtime_prepends_repo_root_and_src() -> None:
    import sys
    from pathlib import Path

    from obsidiandroid.common import repo_paths
    from scripts._bootstrap import prepare_script_runtime

    here = Path(repo_paths.__file__).resolve()
    if len(here.parents) < 4 or here.parents[2].name != "src":
        pytest.skip("repo_paths not loaded from a checkout tree under src/")
    root = here.parents[3]
    src = str((root / "src").resolve())
    root_s = str(root.resolve())
    while root_s in sys.path:
        sys.path.remove(root_s)
    while src in sys.path:
        sys.path.remove(src)
    assert prepare_script_runtime(root / "scripts" / "diagnostics" / "check_run_integrity.py") == root
    assert root_s in sys.path
    assert src in sys.path


def test_setuptools_package_discovery_excludes_retired_analysis_tree() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    with (repo_root / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)

    include = metadata["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "analysis*" not in include


def test_python_sources_have_no_utf8_bom_prefix() -> None:
    """BOM-prefixed ``*.py`` files break ast.parse and CI shim checks (see check_import_surface)."""
    from pathlib import Path

    from scripts.dev.import_surface_policy import collect_utf8_bom_python_sources

    repo_root = Path(__file__).resolve().parents[1]
    bad = collect_utf8_bom_python_sources(repo_root)
    assert not bad, "UTF-8 BOM at start of:\n" + "\n".join(bad)


@pytest.mark.contract
def test_production_wheel_excludes_source_checkout_operator_scripts(tmp_path: Path) -> None:
    """The installable package must not turn dev/diagnostic scripts into a public API."""
    repo_root = Path(__file__).resolve().parents[1]
    source_root = tmp_path / "source"
    source_root.mkdir()

    for name in ("pyproject.toml", "README.md", "requirements.txt", "main.py"):
        shutil.copy2(repo_root / name, source_root / name)
    ignored = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        "*.egg-info",
        ".pytest_cache",
        ".pytest_tmp",
        ".ruff_cache",
        "build",
        "dist",
    )
    for name in ("src", "config", "database", "profiles", "scripts"):
        shutil.copytree(repo_root / name, source_root / name, ignore=ignored)

    wheel_dir = tmp_path / "wheel"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--no-cache-dir",
            "--wheel-dir",
            str(wheel_dir),
            str(source_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_dir.glob("*.whl"))
    with ZipFile(wheel) as archive:
        names = archive.namelist()

    assert not any(name.startswith("scripts/") for name in names)
    assert not any(name.startswith("analysis/") for name in names)
    assert not any(name.startswith("database/") for name in names)
    assert any(name.startswith("obsidiandroid/") for name in names)
    assert any(name.startswith("config/") for name in names)
    assert any(name.startswith("profiles/") for name in names)
