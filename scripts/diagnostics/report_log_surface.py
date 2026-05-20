"""Inventory repo/runtime log files and related observability artifacts."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from obsidiandroid.common.output_paths import diagnostics_root, project_logs_root


@dataclass(frozen=True)
class LogSurfaceItem:
    """One discovered log-like artifact on disk."""

    path: Path
    surface: str
    status: str
    size_bytes: int
    note: str


_ROLLING_LOG_NOTES: dict[str, str] = {
    "analysis_summary.log": "Research/evaluation summary logger.",
    "artifact_exports.log": "Workbook/export and artifact copy logger.",
    "database_access.log": "DB connectivity/query logger.",
    "error.log": "Cross-category aggregate sink for error-level events.",
    "label_authority_alerts.log": "Authority-risk alerts from the Erebus family/type authority diagnostic path.",
    "machine_learning.log": "Machine learning and training pipeline logger.",
    "pipeline_orchestration.log": "Top-level pipeline orchestration logger.",
    "profile_preflight.log": "Interactive profile-selection and preflight logger.",
    "temporal_readiness_alerts.log": "Temporal-evaluation risk alerts from the authority coverage diagnostic path.",
}
_LEGACY_SHORT_NAME_LOGS: dict[str, str] = {
    "analysis.log": "Legacy short-name rolling log; superseded by analysis_summary.log.",
    "database.log": "Legacy short-name rolling log; superseded by database_access.log.",
    "export.log": "Legacy short-name rolling log; superseded by artifact_exports.log.",
    "menu.log": "Legacy short-name rolling log; superseded by profile_preflight.log.",
    "ml.log": "Legacy short-name rolling log; superseded by machine_learning.log.",
    "pipeline.log": "Legacy short-name rolling log; superseded by pipeline_orchestration.log.",
}


def _runtime_log_items(runtime_root: Path) -> list[LogSurfaceItem]:
    items: list[LogSurfaceItem] = []
    for path in sorted(runtime_root.glob("*/pipeline_runtime*.log")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        note = "Per-run stdout/stderr tee log."
        if path.name.startswith("pipeline_runtime_console_"):
            note = "Per-run stdout/stderr tee console capture log."
        elif path.name.startswith("pipeline_runtime_"):
            note = "Legacy per-run stdout/stderr tee log."
        items.append(
            LogSurfaceItem(
                path=path,
                surface="runtime_tee_log",
                status="active" if size > 0 else "empty",
                size_bytes=size,
                note=note,
            )
        )
    return items


def _runtime_category_log_items(runtime_root: Path) -> list[LogSurfaceItem]:
    items: list[LogSurfaceItem] = []
    for path in sorted(runtime_root.glob("*/*.log")):
        if not path.is_file() or path.name.startswith("pipeline_runtime"):
            continue
        size = path.stat().st_size
        note = "Per-run structured category log."
        surface = "runtime_category_log"
        if path.name in _LEGACY_SHORT_NAME_LOGS:
            note = f"Legacy runtime category log; superseded by canonical clearer names for run-scoped structured logging."
            surface = "runtime_legacy_category_log"
        elif path.name in _ROLLING_LOG_NOTES:
            note = f"Per-run structured category log. {_ROLLING_LOG_NOTES[path.name]}"
        items.append(
            LogSurfaceItem(
                path=path,
                surface=surface,
                status="active" if size > 0 else "empty",
                size_bytes=size,
                note=note,
            )
        )
    return items


def _rolling_log_items(logs_root: Path) -> list[LogSurfaceItem]:
    items: list[LogSurfaceItem] = []
    for path in sorted(logs_root.glob("*.log")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        note = _ROLLING_LOG_NOTES.get(path.name)
        surface = "rolling_category_log"
        if note is None and path.name in _LEGACY_SHORT_NAME_LOGS:
            note = _LEGACY_SHORT_NAME_LOGS[path.name]
            surface = "legacy_short_name_log"
        items.append(
            LogSurfaceItem(
                path=path,
                surface=surface,
                status="active" if size > 0 else "empty",
                size_bytes=size,
                note=note or "Category-based rolling logger.",
            )
        )
    return items


def _latest_run_observability_items() -> list[LogSurfaceItem]:
    diagnostics_dir = diagnostics_root()
    items: list[LogSurfaceItem] = []
    candidates = [
        diagnostics_dir / "latest_run_pointer.json",
        diagnostics_dir / "logging_audit.md",
        diagnostics_dir / "logging_audit.csv",
        diagnostics_dir / "pipeline_stage_timings.latest.csv",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        items.append(
            LogSurfaceItem(
                path=path,
                surface="global_observability_artifact",
                status="active",
                size_bytes=path.stat().st_size,
                note="Global operator-facing observability artifact.",
            )
        )
    return items


def collect_log_surface() -> list[LogSurfaceItem]:
    """Return the current repo/runtime logging surface."""
    logs_root = project_logs_root()
    logs_root.mkdir(parents=True, exist_ok=True)
    items: list[LogSurfaceItem] = []
    items.extend(_rolling_log_items(logs_root))
    items.extend(_runtime_log_items(logs_root / "runtime"))
    items.extend(_runtime_category_log_items(logs_root / "runtime"))
    items.extend(_latest_run_observability_items())
    return sorted(items, key=lambda item: (item.surface, str(item.path)))


def _recommendations(items: Iterable[LogSurfaceItem]) -> list[str]:
    items = list(items)
    empty_rolling = [
        item
        for item in items
        if item.surface in {"rolling_category_log", "legacy_short_name_log"} and item.status == "empty"
    ]
    active_rolling = [
        item
        for item in items
        if item.surface in {"rolling_category_log", "legacy_short_name_log"} and item.status == "active"
    ]
    legacy_short = [item for item in items if item.surface == "legacy_short_name_log"]
    runtime_logs = [item for item in items if item.surface == "runtime_tee_log"]
    runtime_legacy = [item for item in items if item.surface == "runtime_legacy_category_log"]

    recommendations: list[str] = []
    if empty_rolling:
        recommendations.append(
            f"Prune {len(empty_rolling)} empty rolling logs; delayed file handlers should stop new placeholders."
        )
    if active_rolling:
        recommendations.append("Keep rolling category logs only for active domains; avoid adding more short-lived category logs.")
    if legacy_short:
        recommendations.append(
            f"Prune or archive {len(legacy_short)} legacy short-name logs once the clearer canonical names have replaced them in normal runs."
        )
    if runtime_legacy:
        recommendations.append(
            f"Prune {len(runtime_legacy)} legacy runtime category logs; they obscure the newer per-run canonical log structure."
        )
    if runtime_logs:
        recommendations.append(
            "Keep per-run console tee logs because they capture terminal-only failure context that is not guaranteed to appear in JSONL artifacts."
        )
    recommendations.append(
        "Prefer run-scoped diagnostics or pipeline_events entries before introducing new generic repo-root log categories."
    )
    recommendations.append(
        "Use targeted alert logs for label authority and temporal readiness risk; avoid adding more generic free-form category logs."
    )
    return recommendations


def write_log_surface_report() -> tuple[Path, Path]:
    """Write markdown and CSV inventory under output/diagnostics."""
    diagnostics_dir = diagnostics_root()
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    md_path = diagnostics_dir / "log_surface_inventory_latest.md"
    csv_path = diagnostics_dir / "log_surface_inventory_latest.csv"
    items = collect_log_surface()

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["surface", "status", "size_bytes", "path", "note"],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "surface": item.surface,
                    "status": item.status,
                    "size_bytes": item.size_bytes,
                    "path": str(item.path),
                    "note": item.note,
                }
            )

    surface_counts: dict[str, int] = {}
    for item in items:
        surface_counts[item.surface] = surface_counts.get(item.surface, 0) + 1

    lines = [
        "# Log Surface Inventory",
        "",
        "## Summary",
        "",
        f"- total items: `{len(items)}`",
    ]
    for surface, count in sorted(surface_counts.items()):
        lines.append(f"- {surface}: `{count}`")

    lines.extend(
        [
            "",
            "## Current log files",
            "",
            "| Surface | Status | Size | Path | Note |",
            "|---------|--------|------|------|------|",
        ]
    )
    for item in items:
        lines.append(
            f"| `{item.surface}` | `{item.status}` | `{item.size_bytes}` | `{item.path}` | {item.note} |"
        )

    lines.extend(["", "## Recommendations", ""])
    for recommendation in _recommendations(items):
        lines.append(f"- {recommendation}")

    lines.extend(
        [
            "",
            "## Keep / prune / add guidance",
            "",
            "- Keep: `error.log`, `label_authority_alerts.log`, `temporal_readiness_alerts.log`, `pipeline_runtime_console_<run_id>.log`, `pipeline_events.jsonl`, `pipeline_stage_timings*.csv`, `logging_audit.*`.",
            "- Prune: empty repo-root category logs and legacy short-name log files after the new canonical names are in use.",
            "- Add via diagnostics first, or via targeted risk logs only when the signal directly supports trust, label authority review, or temporal-evaluation readiness.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, csv_path


if __name__ == "__main__":
    md, csv_out = write_log_surface_report()
    print(f"[OK] wrote {md}")
    print(f"[OK] wrote {csv_out}")
