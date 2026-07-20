"""Persistence mode must be explicit and fail closed to read-only analysis."""

from __future__ import annotations

import os
import subprocess
import sys


def _mode_from_clean_process(value: str | None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("OBSIDIANDROID_RESULTS_PERSISTENCE_MODE", None)
    if value is not None:
        env["OBSIDIANDROID_RESULTS_PERSISTENCE_MODE"] = value
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from config.settings.methodology import RESULTS_PERSISTENCE_MODE, ENABLE_RESULTS_WAREHOUSE_EXPORT; print(RESULTS_PERSISTENCE_MODE, ENABLE_RESULTS_WAREHOUSE_EXPORT)",
        ],
        cwd=".",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_persistence_mode_defaults_to_read_only() -> None:
    result = _mode_from_clean_process(None)
    assert result.returncode == 0
    assert result.stdout.strip() == "read_only False"


def test_legacy_warehouse_mode_requires_explicit_environment_selection() -> None:
    result = _mode_from_clean_process("legacy_warehouse")
    assert result.returncode == 0
    assert result.stdout.strip() == "legacy_warehouse True"


def test_invalid_persistence_mode_fails_closed() -> None:
    result = _mode_from_clean_process("unexpected")
    assert result.returncode != 0
    assert "OBSIDIANDROID_RESULTS_PERSISTENCE_MODE" in result.stderr
