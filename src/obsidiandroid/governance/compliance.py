"""Paper-mode compliance checks and report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_compliance_report(
    *,
    run_id: str,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build normalized compliance payload."""
    failed = [item for item in checks if str(item.get("status", "")).lower() != "pass"]
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "overall_status": "fail" if failed else "pass",
        "checks": checks,
    }


def write_compliance_report(path: Path, report: dict[str, Any]) -> Path:
    """Write compliance report JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


__all__ = ["build_compliance_report", "write_compliance_report"]
