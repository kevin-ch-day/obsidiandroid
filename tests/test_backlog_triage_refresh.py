"""Tests for portable backlog triage export refresh."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.diagnostics.backlog_triage_refresh import (
    refresh_stale_backlog_triage_exports,
    run_backlog_triage_script,
)


def test_run_backlog_triage_script_returns_nonzero_for_missing_script(tmp_path: Path) -> None:
    rc = run_backlog_triage_script(
        "android_missing_resolution",
        operator_script_resolver=lambda *_parts: tmp_path / "missing.py",
    )
    assert rc == 1


def test_refresh_stale_backlog_triage_exports_runs_only_requested_keys(tmp_path: Path) -> None:
    calls: list[str] = []

    def _resolver(*parts: str) -> Path:
        return tmp_path / "/".join(parts)

    def _subprocess_run(cmd, check=False):  # noqa: ANN001, ARG001
        script = Path(cmd[-1])
        calls.append(script.name)
        script.write_text("print('ok')\n", encoding="utf-8")
        return type("Proc", (), {"returncode": 0})()

    (tmp_path / "diagnostics").mkdir(parents=True)
    (tmp_path / "diagnostics/report_android_missing_resolution_triage.py").write_text(
        "print('android')\n",
        encoding="utf-8",
    )
    (tmp_path / "diagnostics/report_backlog_debt_operator_summary.py").write_text(
        "print('summary')\n",
        encoding="utf-8",
    )

    rc, refreshed = refresh_stale_backlog_triage_exports(
        output_root=tmp_path,
        operator_script_resolver=_resolver,
        subprocess_run=_subprocess_run,
        refresh_exports=["android_missing_resolution"],
    )

    assert rc == 0
    assert refreshed == ["android_missing_resolution", "operator_summary"]
    assert "report_android_missing_resolution_triage.py" in calls
    assert "report_backlog_debt_operator_summary.py" in calls
