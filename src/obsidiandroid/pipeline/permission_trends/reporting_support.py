"""Lightweight I/O and label helpers for permission-trends reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import app_config
from obsidiandroid.cli.ui import display as du

from obsidiandroid.pipeline.permission_trends.constants import PERMISSION_PREFIX


def handle_reporting_exception(context: str, exc: Exception, fail_in_paper: bool = False) -> None:
    """Centralized exception policy for permission-trends reporting helpers."""
    du.print_warning(f"[REPORT] {context} failed: {exc}")
    if fail_in_paper and bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
        raise


def write_run_scoped_permission_artifacts() -> bool:
    """Legacy compatibility shim for run-suffixed permission-trend artifacts."""
    return False


def compact_permission_label(permission_name: str) -> str:
    """Shorten Android permission labels for chart readability."""
    value = str(permission_name).strip()
    if value.lower().startswith(PERMISSION_PREFIX):
        return value[len(PERMISSION_PREFIX) :]
    return value


def read_snapshot_meta() -> dict[str, str]:
    """Parse key=value lines from the active analysis snapshot meta file."""
    meta_path = Path(
        getattr(
            app_config,
            "ANALYSIS_SNAPSHOT_META_FILE",
            getattr(app_config, "COHORT_SNAPSHOT_META_FILE", ""),
        )
    )
    if not meta_path.exists():
        return {}
    parsed: dict[str, str] = {}
    try:
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip()
    except Exception as exc:
        handle_reporting_exception("read_snapshot_meta", exc, fail_in_paper=False)
        return {}
    return parsed


def read_dataset_time_contract() -> dict[str, Any]:
    """Read dataset time contract exported by sample stage."""
    path = Path(
        str(
            getattr(
                app_config,
                "DATASET_TIME_CONTRACT_FILE",
                "output/diagnostics/dataset_time_contract.latest.json",
            )
        )
    )
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        handle_reporting_exception("read_dataset_time_contract", exc, fail_in_paper=False)
        return {}
