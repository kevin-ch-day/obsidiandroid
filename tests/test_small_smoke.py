"""Consolidated smoke coverage for tiny utility scripts and menu hooks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

from config import app_config
import pandas as pd

import obsidiandroid.cli.startup_menu as startup_menu
from obsidiandroid.cli.ui import menu
from scripts.diagnostics import report_logging_engine_usage as report_mod
from scripts.dev import data_fuzzer


def test_generate_fuzz_data_shapes() -> None:
    df, labels = data_fuzzer.generate_fuzz_data(
        n_samples=50,
        n_features=10,
        n_classes=4,
        random_state=1,
    )
    assert isinstance(df, pd.DataFrame)
    assert isinstance(labels, pd.Series)
    assert df.shape == (50, 10)
    assert len(labels) == 50
    assert set(labels.unique()) <= set(range(4))


def test_write_logging_engine_usage_report_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    """Usage audit should emit markdown and CSV artifacts."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(report_mod, "diagnostics_root", lambda: diagnostics_dir)

    md_path, csv_path = report_mod.write_logging_engine_usage_report()
    assert md_path.exists()
    assert csv_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "Logging Engine Usage Audit" in text
    assert "failure-like event calls without explicit `level`" in text


def test_check_doc_hygiene_exits_zero() -> None:
    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "dev" / "check_doc_hygiene.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_resolve_display_mode_defaults_to_compact(monkeypatch) -> None:
    monkeypatch.delenv("OBSIDIANDROID_DISPLAY_MODE", raising=False)
    monkeypatch.setattr(app_config, "DEBUG_MODE", False, raising=False)
    from obsidiandroid.cli.menu import display_mode

    assert display_mode.resolve_display_mode() == "compact"


def test_resolve_display_mode_uses_env_override(monkeypatch) -> None:
    monkeypatch.setenv("OBSIDIANDROID_DISPLAY_MODE", "detailed")
    monkeypatch.setattr(app_config, "DEBUG_MODE", False, raising=False)
    from obsidiandroid.cli.menu import display_mode

    assert display_mode.resolve_display_mode() == "detailed"


def test_mode_max_rows_respects_debug_mode(monkeypatch) -> None:
    monkeypatch.setenv("OBSIDIANDROID_DISPLAY_MODE", "debug")
    from obsidiandroid.cli.menu import display_mode

    assert display_mode.mode_max_rows(compact=3, detailed=8, debug=12) == 12


def test_display_menu_returns_zero_on_keyboard_interrupt(monkeypatch) -> None:
    """Ctrl+C in menu input should return Exit code path (0)."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": (_ for _ in ()).throw(KeyboardInterrupt))
    result = menu.display_menu(["Option A", "Option B"], title="Test Menu")
    assert result == 0


def test_startup_menu_main_returns_130_on_keyboard_interrupt(monkeypatch) -> None:
    """Top-level startup menu should convert Ctrl+C to exit code 130."""
    monkeypatch.setattr(startup_menu, "launch_startup_menu", lambda: (_ for _ in ()).throw(KeyboardInterrupt))
    assert startup_menu.main() == 130
