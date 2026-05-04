"""Inspect Python module and function size hotspots.

This utility scans repository Python files and reports:
1. Largest modules by line count.
2. Largest functions by line count (AST-based).
3. Modules above a configured threshold.

Example:
    python scripts/diagnostics/inspect_module_size_hotspots.py --top-files 30 --top-functions 30
"""

from __future__ import annotations

import argparse
import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileSize:
    """Simple file size record."""

    path: Path
    lines: int


@dataclass(frozen=True)
class FunctionSize:
    """Simple function size record."""

    path: Path
    name: str
    start_line: int
    lines: int


def _list_python_files() -> list[Path]:
    output = subprocess.check_output(["rg", "--files", "-g", "*.py"], text=True)
    return [Path(p.strip()) for p in output.splitlines() if p.strip()]


def _count_file_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)


def _collect_file_sizes(paths: list[Path]) -> list[FileSize]:
    rows = [FileSize(path=p, lines=_count_file_lines(p)) for p in paths]
    return sorted(rows, key=lambda x: x.lines, reverse=True)


def _collect_function_sizes(paths: list[Path], min_lines: int) -> list[FunctionSize]:
    rows: list[FunctionSize] = []
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and hasattr(node, "end_lineno"):
                line_count = int(node.end_lineno - node.lineno + 1)
                if line_count >= min_lines:
                    rows.append(
                        FunctionSize(
                            path=path,
                            name=node.name,
                            start_line=int(node.lineno),
                            lines=line_count,
                        )
                    )
    return sorted(rows, key=lambda x: x.lines, reverse=True)


def _print_file_table(rows: list[FileSize], limit: int) -> None:
    print("\nTop Modules By Line Count")
    print("-" * 72)
    print(f"{'Lines':>8}  File")
    print("-" * 72)
    for row in rows[:limit]:
        print(f"{row.lines:8d}  {row.path}")


def _print_function_table(rows: list[FunctionSize], limit: int) -> None:
    print("\nTop Functions By Line Count")
    print("-" * 72)
    print(f"{'Lines':>8}  {'Location':<55}  Function")
    print("-" * 72)
    for row in rows[:limit]:
        loc = f"{row.path}:{row.start_line}"
        print(f"{row.lines:8d}  {loc:<55}  {row.name}")


def _print_oversized_modules(rows: list[FileSize], threshold: int) -> None:
    oversized = [row for row in rows if row.lines >= threshold]
    print(f"\nModules >= {threshold} Lines")
    print("-" * 72)
    if not oversized:
        print("None")
        return
    for row in oversized:
        print(f"{row.lines:8d}  {row.path}")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Inspect Python module and function size hotspots.")
    parser.add_argument("--top-files", type=int, default=25, help="Number of files to show.")
    parser.add_argument("--top-functions", type=int, default=25, help="Number of functions to show.")
    parser.add_argument(
        "--module-threshold",
        type=int,
        default=400,
        help="Line-count threshold for oversized module reporting.",
    )
    parser.add_argument(
        "--function-threshold",
        type=int,
        default=60,
        help="Minimum lines for function hotspot reporting.",
    )
    args = parser.parse_args()

    paths = _list_python_files()
    file_sizes = _collect_file_sizes(paths)
    function_sizes = _collect_function_sizes(paths, min_lines=args.function_threshold)

    _print_file_table(file_sizes, limit=args.top_files)
    _print_oversized_modules(file_sizes, threshold=args.module_threshold)
    _print_function_table(function_sizes, limit=args.top_functions)
    print(f"\nScanned {len(paths)} Python files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
