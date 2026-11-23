"""Regression checks for the source checkout and installed CLI boundaries."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "scripts" / "dev"


@pytest.mark.parametrize(
    ("args", "code", "message"),
    [
        ([str(ROOT / "main.py"), "--help"], 0, "--allow-global-artifacts"),
        ([str(ROOT / "main.py"), "--dry-run"], 2, "unrecognized arguments"),
        (["-m", "obsidiandroid.cli.main", "--help"], 0, "--allow-global-artifacts"),
        (["-m", "obsidiandroid.cli", "--help"], 0, "Commands: analysis, pi-v2"),
        (["-m", "obsidiandroid.cli", "analysis", "--help"], 0, "obsidiandroid analysis"),
        (["-m", "obsidiandroid.cli", "pi-v2", "--help"], 0, "obsidiandroid pi-v2"),
        (["-m", "obsidiandroid.cli", "invalid"], 2, "unrecognized arguments"),
    ],
)
def test_help_and_invalid_arguments_need_no_runtime_packages(tmp_path, args, code, message):
    checkout_cwd = tmp_path / "cwd"
    checkout_cwd.mkdir()
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-S", *args], cwd=checkout_cwd, env=env, capture_output=True, text=True,
        timeout=15,
    )
    assert result.returncode == code, result.stderr
    assert message in (result.stdout if code == 0 else result.stderr)
    assert not list(checkout_cwd.iterdir())


def test_manifest_and_contract_imports_do_not_initialize_sibling_modules(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    program = """
import sys
from obsidiandroid.database import facade_manifest
import obsidiandroid.diagnostics
from obsidiandroid.governance import evidence_mode_resolver
from obsidiandroid.modeling import modeling_facade_manifest
from obsidiandroid.pipeline.permission_trends import constants
import obsidiandroid.reporting
import obsidiandroid.database as database
assert set(facade_manifest.FACADE_EXPORT_NAMES) <= set(dir(database))
assert 'obsidiandroid.database.db_engine' not in sys.modules
assert 'obsidiandroid.governance.run_manifest' not in sys.modules
assert 'obsidiandroid.modeling.pipeline_core' not in sys.modules
assert 'obsidiandroid.reporting.confusion_matrix_exporter' not in sys.modules
assert 'obsidiandroid.pipeline.permission_trends.sample_permission_data' not in sys.modules
assert 'pandas' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", program], cwd=tmp_path, env=env, capture_output=True,
        text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_model_menu_does_not_import_training_pipeline(tmp_path):
    program = """
import sys
from obsidiandroid.cli.startup_menu import _build_model_menu
assert 'random_forest' in _build_model_menu().values()
assert 'obsidiandroid.modeling.pipeline_core' not in sys.modules
assert 'sklearn' not in sys.modules
assert 'matplotlib.pyplot' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT)])),
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_operator_dispatch_preserves_subcommand_options(monkeypatch):
    from obsidiandroid.cli import analysis, entrypoint

    calls = []

    def run_analysis(argv, *, prog):
        calls.append((argv, prog))
        return 7

    monkeypatch.setattr(analysis, "main", run_analysis)
    assert entrypoint.main(["analysis", "verify", "--run-id", "fixture"]) == 7
    assert calls == [(["verify", "--run-id", "fixture"], "obsidiandroid analysis")]


@pytest.fixture
def git_checkout(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("Git is required by checkout tooling")

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "commit.gpgsign", "false")
    return git


def test_changed_tests_include_uncommitted_and_nested_paths(tmp_path, git_checkout):
    scripts = tmp_path / "scripts" / "dev"
    scripts.mkdir(parents=True)
    shutil.copy(DEV / "run_tests_changed.sh", scripts)
    runner = scripts / "run_pytest.sh"
    runner.write_text("#!/bin/bash\nprintf 'ARG=%s\\n' \"$@\"\n")
    runner.chmod(0o755)

    source = tmp_path / "src" / "obsidiandroid" / "reporting" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text("count = 1\n")
    nested_tests = tmp_path / "tests" / "reporting"
    nested_tests.mkdir(parents=True)
    (nested_tests / "test_example.py").write_text("# Baseline\n")
    edited_test = nested_tests / "test_changed.py"
    edited_test.write_text("# Baseline\n")
    git_checkout("add", "scripts", "src", "tests")
    git_checkout("commit", "-qm", "Fixture")
    source.write_text("count = 2\n")
    edited_test.write_text("# Updated\n")
    (nested_tests / "test_new.py").write_text("# Untracked\n")
    command = ["bash", str(scripts / "run_tests_changed.sh")]
    result = subprocess.run(
        [*command, "HEAD"], cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    selected = {line.removeprefix("ARG=") for line in result.stdout.splitlines()
                if line.startswith("ARG=")}
    assert selected == {
        "tests/reporting/test_changed.py",
        "tests/reporting/test_example.py",
        "tests/reporting/test_new.py",
    }
    bad_base = subprocess.run(
        [*command, "does-not-exist"], cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert bad_base.returncode == 2
    assert "Cannot resolve base ref" in bad_base.stderr


def test_linked_worktree_uses_primary_venv_until_local_venv_exists(tmp_path, git_checkout):
    resolver = Path("scripts/dev/checkout_venv.sh")
    (tmp_path / resolver.parent).mkdir(parents=True)
    shutil.copy(DEV / resolver.name, tmp_path / resolver)
    git_checkout("add", str(resolver))
    git_checkout("commit", "-qm", "Fixture")
    linked = tmp_path / "linked"
    git_checkout("worktree", "add", "--detach", str(linked), "HEAD")

    def create_venv_bin(checkout):
        venv_bin = checkout / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        python = venv_bin / "python"
        python.touch()
        python.chmod(0o755)
        return venv_bin

    def selected_venv_bin():
        result = subprocess.run(
            ["bash", str(linked / resolver)], cwd=tmp_path, check=True, capture_output=True,
            text=True, timeout=15,
        )
        return Path(result.stdout.strip())

    primary_bin = create_venv_bin(tmp_path)
    assert selected_venv_bin() == primary_bin
    local_bin = create_venv_bin(linked)
    assert selected_venv_bin() == local_bin
