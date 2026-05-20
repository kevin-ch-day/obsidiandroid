"""Static audit of structured logging engine usage across source modules."""

from __future__ import annotations

import ast
import csv
from dataclasses import dataclass
from pathlib import Path

from obsidiandroid.common.output_paths import diagnostics_root
from obsidiandroid.common.repo_paths import repo_root


@dataclass(frozen=True)
class LoggerBinding:
    """One module-level ``get_logger`` binding."""

    module_path: str
    variable_name: str
    category: str


@dataclass(frozen=True)
class EventCall:
    """One ``log_event`` call found in the AST."""

    module_path: str
    event_name: str
    has_event_id: bool
    has_level: bool
    level_value: str
    logger_symbol: str


def _module_files() -> list[Path]:
    src_root = repo_root() / "src" / "obsidiandroid"
    return sorted(path for path in src_root.rglob("*.py") if path.is_file())


def _literal_str(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _parse_module(path: Path) -> tuple[list[LoggerBinding], list[EventCall]]:
    module_rel = str(path.relative_to(repo_root()))
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bindings: list[LoggerBinding] = []
    events: list[EventCall] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "get_logger" and len(call.args) >= 2:
                category = _literal_str(call.args[1])
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bindings.append(
                            LoggerBinding(
                                module_path=module_rel,
                                variable_name=target.id,
                                category=category or "<dynamic>",
                            )
                        )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "log_event":
            event_name = _literal_str(node.args[1]) if len(node.args) >= 2 else "<dynamic>"
            logger_symbol = ""
            if node.args and isinstance(node.args[0], ast.Name):
                logger_symbol = node.args[0].id
            kw_map = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            level_value = _literal_str(kw_map.get("level")) if "level" in kw_map else ""
            events.append(
                EventCall(
                    module_path=module_rel,
                    event_name=event_name,
                    has_event_id="event_id" in kw_map,
                    has_level="level" in kw_map,
                    level_value=level_value or ("<dynamic>" if "level" in kw_map else ""),
                    logger_symbol=logger_symbol or "<unknown>",
                )
            )

    return bindings, events


def _failure_like(event_name: str) -> bool:
    token = str(event_name).lower()
    return any(flag in token for flag in ("fail", "error", "skip", "warning"))


def write_logging_engine_usage_report() -> tuple[Path, Path]:
    """Write markdown and CSV usage inventory under output/diagnostics."""
    bindings: list[LoggerBinding] = []
    events: list[EventCall] = []
    for path in _module_files():
        b, e = _parse_module(path)
        bindings.extend(b)
        events.extend(e)

    diagnostics_dir = diagnostics_root()
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    md_path = diagnostics_dir / "logging_engine_usage_latest.md"
    csv_path = diagnostics_dir / "logging_engine_usage_latest.csv"

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "module_path",
                "logger_symbol",
                "event_name",
                "has_event_id",
                "has_level",
                "level_value",
            ],
        )
        writer.writeheader()
        for event in events:
            writer.writerow(
                {
                    "module_path": event.module_path,
                    "logger_symbol": event.logger_symbol,
                    "event_name": event.event_name,
                    "has_event_id": event.has_event_id,
                    "has_level": event.has_level,
                    "level_value": event.level_value,
                }
            )

    categories: dict[str, int] = {}
    for binding in bindings:
        categories[binding.category] = categories.get(binding.category, 0) + 1

    missing_event_ids = [event for event in events if not event.has_event_id]
    failure_without_level = [
        event for event in events if _failure_like(event.event_name) and not event.has_level
    ]

    lines = [
        "# Logging Engine Usage Audit",
        "",
        "## Summary",
        "",
        f"- logger bindings: `{len(bindings)}`",
        f"- structured event calls: `{len(events)}`",
        f"- event calls without `event_id`: `{len(missing_event_ids)}`",
        f"- failure-like event calls without explicit `level`: `{len(failure_without_level)}`",
        "",
        "## Logger categories",
        "",
        "| Category | Bindings |",
        "|----------|----------|",
    ]
    for category, count in sorted(categories.items()):
        lines.append(f"| `{category}` | `{count}` |")

    lines.extend(["", "## Modules using structured logging", ""])
    for binding in bindings:
        lines.append(
            f"- `{binding.module_path}`: `{binding.variable_name}` -> category `{binding.category}`"
        )

    lines.extend(["", "## High-value gaps", ""])
    for event in failure_without_level[:20]:
        lines.append(
            f"- `{event.module_path}` event `{event.event_name}` has failure/warning semantics but no explicit `level`."
        )
    for event in missing_event_ids[:20]:
        lines.append(
            f"- `{event.module_path}` event `{event.event_name}` does not emit an `event_id`."
        )

    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            "- Prefer explicit `level=` on failure, degraded, skip, and warning events.",
            "- Prefer stable `event_id=` on operator-critical stage transitions and scoring/training failures.",
            "- Keep using broad categories (`pipeline`, `ml`, `database`, `export`) and add precision through event names and context fields, not more log files.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, csv_path


if __name__ == "__main__":
    md, csv_out = write_logging_engine_usage_report()
    print(f"[OK] wrote {md}")
    print(f"[OK] wrote {csv_out}")
