"""Inspect Python file and function complexity hotspots.

This script provides lightweight static complexity indicators without external
linters or analyzers. It is intended for refactor planning and architecture
reviews.
"""

from __future__ import annotations

from argparse import ArgumentParser
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "output",
}


@dataclass(frozen=True)
class FileHotspot:
    """Container for per-file structural metrics.

    Attributes:
        path: Repository-relative file path.
        line_count: Number of lines in the source file.
        function_count: Count of functions and methods in the file.
        max_function_lines: Largest function length in lines.
        broad_except_count: Number of ``except Exception`` handlers.
    """

    path: str
    line_count: int
    function_count: int
    max_function_lines: int
    broad_except_count: int


@dataclass(frozen=True)
class FunctionHotspot:
    """Container for per-function complexity indicators.

    Attributes:
        path: Repository-relative file path.
        name: Function name.
        line_start: Function start line number.
        line_count: Function size in lines.
        branch_nodes: Count of branch-like AST nodes.
        broad_except_count: Number of ``except Exception`` handlers in function.
    """

    path: str
    name: str
    line_start: int
    line_count: int
    branch_nodes: int
    broad_except_count: int


def _should_skip(path: Path) -> bool:
    """Return True when path should be excluded from analysis."""
    return any(part in DEFAULT_EXCLUDE_DIRS for part in path.parts)


def _iter_python_files(root: Path) -> Iterable[Path]:
    """Yield Python files under root while applying default exclusions."""
    for path in root.rglob("*.py"):
        if _should_skip(path):
            continue
        yield path


def _node_end_line(node: ast.AST) -> int:
    """Return best-effort end line for AST node."""
    return int(getattr(node, "end_lineno", getattr(node, "lineno", 0)))


def _is_broad_exception(handler: ast.ExceptHandler) -> bool:
    """Return True when handler catches the broad ``Exception`` type."""
    if handler.type is None:
        return False
    if isinstance(handler.type, ast.Name):
        return handler.type.id == "Exception"
    return False


def _collect_metrics_for_file(path: Path, root: Path) -> tuple[FileHotspot, list[FunctionHotspot]] | None:
    """Parse and collect file/function complexity metrics.

    Args:
        path: Absolute file path.
        root: Analysis root used to compute relative paths.

    Returns:
        Tuple of file-level and function-level metrics, or ``None`` when parse
        fails.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None

    lines = source.splitlines()
    function_hotspots: list[FunctionHotspot] = []
    broad_except_count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad_exception(node):
            broad_except_count += 1

        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        line_start = int(getattr(node, "lineno", 0))
        line_end = _node_end_line(node)
        line_count = max(1, line_end - line_start + 1)

        branch_nodes = sum(
            isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.Match, ast.IfExp, ast.BoolOp))
            for child in ast.walk(node)
        )
        function_broad_excepts = sum(
            _is_broad_exception(handler)
            for child in ast.walk(node)
            if isinstance(child, ast.Try)
            for handler in child.handlers
        )

        function_hotspots.append(
            FunctionHotspot(
                path=str(path.relative_to(root)),
                name=node.name,
                line_start=line_start,
                line_count=line_count,
                branch_nodes=int(branch_nodes),
                broad_except_count=int(function_broad_excepts),
            )
        )

    file_hotspot = FileHotspot(
        path=str(path.relative_to(root)),
        line_count=len(lines),
        function_count=len(function_hotspots),
        max_function_lines=max((item.line_count for item in function_hotspots), default=0),
        broad_except_count=broad_except_count,
    )
    return file_hotspot, function_hotspots


def _build_parser() -> ArgumentParser:
    """Create command-line parser."""
    parser = ArgumentParser(description="Inspect Python complexity hotspots.")
    parser.add_argument("--top-files", type=int, default=20, help="Number of file hotspots to print.")
    parser.add_argument("--top-functions", type=int, default=30, help="Number of function hotspots to print.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root directory to scan.",
    )
    return parser


def main() -> int:
    """Run complexity hotspot inspection and print ranked results."""
    parser = _build_parser()
    args = parser.parse_args()
    root = args.root.resolve()

    file_hotspots: list[FileHotspot] = []
    function_hotspots: list[FunctionHotspot] = []

    for path in _iter_python_files(root):
        metrics = _collect_metrics_for_file(path, root)
        if metrics is None:
            continue
        file_item, function_items = metrics
        file_hotspots.append(file_item)
        function_hotspots.extend(function_items)

    ranked_files = sorted(
        file_hotspots,
        key=lambda item: (
            item.line_count,
            item.max_function_lines,
            item.broad_except_count,
        ),
        reverse=True,
    )
    ranked_functions = sorted(
        function_hotspots,
        key=lambda item: (
            item.line_count,
            item.branch_nodes,
            item.broad_except_count,
        ),
        reverse=True,
    )

    print("=== File hotspots ===")
    for item in ranked_files[: max(1, args.top_files)]:
        print(
            f"{item.line_count:5d} lines | max_fn={item.max_function_lines:4d} | "
            f"functions={item.function_count:3d} | broad_except={item.broad_except_count:3d} | {item.path}"
        )

    print("\n=== Function hotspots ===")
    for item in ranked_functions[: max(1, args.top_functions)]:
        print(
            f"{item.line_count:4d} lines | branches={item.branch_nodes:3d} | "
            f"broad_except={item.broad_except_count:2d} | {item.path}:{item.line_start} {item.name}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
