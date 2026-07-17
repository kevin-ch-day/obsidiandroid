import os
from pathlib import Path
import pandas as pd
from obsidiandroid.cli.ui.display import clear_console
from obsidiandroid.cli.ui.display import format_elapsed_duration
from obsidiandroid.cli.ui.display import format_console_path
from obsidiandroid.cli.ui.display import print_table
import obsidiandroid.cli.ui.display as du
from obsidiandroid.cli.ui import console as cc


def test_print_table_dataframe(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    print_table(df, title="Test", show_index=False)
    out = capsys.readouterr().out
    assert "Test" in out
    assert "|   a |   b |" in out


def test_print_table_records(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    records = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    print_table(records, show_index=False)
    out = capsys.readouterr().out
    assert "|   a |   b |" in out


def test_print_table_none(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    print_table(None)
    out = capsys.readouterr().out
    assert "No data available to display." in out


def test_clear_console(monkeypatch):
    called = {}

    def fake_system(cmd):
        called['cmd'] = cmd
        return 0

    monkeypatch.setattr(os, "system", fake_system)
    clear_console()
    assert called['cmd'] in {"cls", "clear"}


def test_console_wraps_long_tagged_messages(monkeypatch):
    monkeypatch.setattr(cc, "USE_COLORS", False)
    monkeypatch.setattr(cc, "get_console_width", lambda default=80: 60)
    text = cc.print_note(
        "[PROFILE] Live authority/taxonomy backlog: repair candidates=2, known unresolved families=0, policy-held tokens=67. "
        "New Erebus-side authority fixes may still sit outside this cohort unless the selected profile/snapshot absorbs them.",
        return_str=True,
    )
    assert "\n" in text
    assert "repair candidates=2" in text


def test_console_wraps_long_stat_values(monkeypatch):
    monkeypatch.setattr(cc, "USE_COLORS", False)
    monkeypatch.setattr(cc, "get_console_width", lambda default=80: 60)
    text = cc.print_stat(
        "Benchmark Eligibility",
        "authority=1,231 | benchmark@3=1,229 | support-excluded=2 | non-family-target=0",
        return_str=True,
    )
    assert "\n" in text
    assert "support-excluded=2" in text


def test_format_console_path_uses_repo_relative_path_inside_repo(monkeypatch):
    repo = Path("/tmp/work/obsidiandroid").resolve()
    target = repo / "output" / "runs" / "rid1" / "diagnostics" / "file.txt"
    monkeypatch.setattr(du, "repo_root", lambda: repo)
    assert format_console_path(target) == "obsidiandroid/output/runs/rid1/diagnostics/file.txt"


def test_format_console_path_preserves_absolute_path_outside_repo(monkeypatch):
    repo = Path("/tmp/work/obsidiandroid").resolve()
    target = Path("/tmp/other/file.txt").resolve()
    monkeypatch.setattr(du, "repo_root", lambda: repo)
    assert format_console_path(target) == target.as_posix()


def test_format_elapsed_duration_uses_minutes_after_one_minute():
    assert format_elapsed_duration(59.9) == "59.90s"
    assert format_elapsed_duration(180.70) == "3m 0.70s"
    assert format_elapsed_duration(3661.2) == "1h 1m 1.20s"
