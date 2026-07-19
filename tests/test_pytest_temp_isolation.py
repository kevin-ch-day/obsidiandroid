"""Guard against repository-local pytest temporary-directory collisions."""

from __future__ import annotations

from pathlib import Path


def test_pytest_configuration_does_not_force_a_repo_local_basetemp() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    full_runner = Path("scripts/dev/run_tests_full.sh").read_text(encoding="utf-8")

    assert "--basetemp=.pytest_tmp" not in pyproject
    assert "--basetemp=.pytest_tmp" not in full_runner
    assert 'addopts = ["-m"' in pyproject
