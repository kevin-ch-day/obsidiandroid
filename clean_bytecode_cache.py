#!/usr/bin/env python3
"""Remove bytecode caches and common ephemeral build/test artifacts under a tree root."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def clean_bytecode_cache(
    target_root: Path | str,
    *,
    exclude_dirs: list[str] | None = None,
) -> None:
    """Delete ``__pycache__`` trees, log files under ``target_root``, and local junk artifacts.

    Args:
        target_root: Directory to clean (must exist).
        exclude_dirs: Path components under ``target_root`` for which ``__pycache__`` removal
            is skipped (e.g. ``["venv", ".venv"]``).
    """
    root = Path(target_root).resolve()
    if not root.is_dir():
        return
    excluded = {str(x).strip() for x in (exclude_dirs or []) if str(x).strip()}

    def _is_under_excluded(path: Path) -> bool:
        try:
            rel = path.relative_to(root)
        except ValueError:
            return False
        return bool(excluded.intersection(rel.parts))

    # Remove __pycache__ directories from leaves upward so parents can be pruned.
    for pycache in sorted(root.rglob("__pycache__"), key=lambda p: len(p.parts), reverse=True):
        if _is_under_excluded(pycache):
            continue
        try:
            shutil.rmtree(pycache)
        except OSError:
            pass

    logs_dir = root / "logs"
    if logs_dir.is_dir():
        for log_file in logs_dir.glob("*.log"):
            try:
                log_file.unlink()
            except OSError:
                pass
        try:
            if not any(logs_dir.iterdir()):
                logs_dir.rmdir()
        except OSError:
            pass

    for name in ("build",):
        candidate = root / name
        if candidate.is_dir():
            try:
                shutil.rmtree(candidate)
            except OSError:
                pass

    for egg in root.glob("*.egg-info"):
        if egg.is_dir():
            try:
                shutil.rmtree(egg)
            except OSError:
                pass

    pytest_tmp = root / ".pytest_tmp_quickmenu"
    if pytest_tmp.is_dir():
        try:
            shutil.rmtree(pytest_tmp)
        except OSError:
            pass

    coverage_file = root / ".coverage"
    if coverage_file.is_file():
        try:
            coverage_file.unlink()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    """CLI entry: clean the current directory or a given path."""
    parser = argparse.ArgumentParser(description="Remove __pycache__ and common artifact dirs.")
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root directory to clean (default: current directory).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="Path component under root to skip for __pycache__ removal (repeatable).",
    )
    args = parser.parse_args(argv)
    clean_bytecode_cache(args.path, exclude_dirs=list(args.exclude))
    return 0


if __name__ == "__main__":
    sys.exit(main())
