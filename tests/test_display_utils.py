import os
import pandas as pd
from utils.display_utils import print_table
from utils.display_utils import clear_console


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
