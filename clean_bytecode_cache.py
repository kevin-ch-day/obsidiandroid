"""Cleanup utility for ObsidianDroid repository artifacts."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from fnmatch import fnmatch
from pathlib import Path


CLEAN_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".bak",
    ".tmp",
    ".~",
    ".log",
    ".orig",
    ".rej",
    ".out",
    ".dump",
}
CLEAN_DIRECTORY_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".tox",
    ".eggs",
    "htmlcov",
    "build",
    "dist",
}
CLEAN_DIRECTORY_PATTERNS = (".pytest_tmp*", "*.egg-info")
ROOT_FILE_NAMES = {".coverage", "coverage.xml", "pytestdebug.log"}
TARGET_DIR_EXTENSIONS = {
    "logs": CLEAN_EXTENSIONS | {".txt"},
    "output": CLEAN_EXTENSIONS | {".txt", ".xlsx", ".csv", ".json"},
}


def remove_file(path: Path) -> bool:
    """Remove a single file and report the result."""
    try:
        path.unlink()
        print("[REMOVED FILE ]", path)
        return True
    except Exception as exc:  # pragma: no cover - exercised only on filesystem failure
        print("[ERROR        ] Could not remove file:", path, "| Reason:", exc)
        return False


def remove_dir(path: Path) -> bool:
    """Remove a directory tree and report the result."""
    try:
        shutil.rmtree(path)
        print("[REMOVED DIR  ]", path)
        return True
    except Exception as exc:  # pragma: no cover - exercised only on filesystem failure
        print("[ERROR        ] Could not remove dir :", path, "| Reason:", exc)
        return False


def _relative_parts(path: Path, root_path: Path) -> tuple[str, ...]:
    """Return path parts relative to the cleanup root."""
    return path.absolute().relative_to(root_path).parts


def _is_excluded(path: Path, root_path: Path, exclude_dirs: set[str]) -> bool:
    """Return whether a path lives under an excluded directory name."""
    if not exclude_dirs:
        return False
    return any(part in exclude_dirs for part in _relative_parts(path, root_path))


def _matches_cleanup_dir(path: Path) -> bool:
    """Return whether a directory should be pruned."""
    if path.name in CLEAN_DIRECTORY_NAMES:
        return True
    return any(fnmatch(path.name, pattern) for pattern in CLEAN_DIRECTORY_PATTERNS)


def _collect_cleanup_dirs(root_path: Path, exclude_dirs: set[str]) -> list[Path]:
    """Collect removable directories while avoiding nested duplicates."""
    candidates = [
        path
        for path in root_path.rglob("*")
        if path.is_dir() and not _is_excluded(path, root_path, exclude_dirs) and _matches_cleanup_dir(path)
    ]
    selected: list[Path] = []
    for path in sorted(candidates, key=lambda item: (len(item.parts), str(item))):
        if any(parent in selected for parent in path.parents):
            continue
        selected.append(path)
    return selected


def _collect_extension_files(
    root_path: Path,
    exclude_dirs: set[str],
    removed_dirs: set[Path],
) -> list[Path]:
    """Collect removable files that are not already covered by removed dirs."""
    files_to_remove: list[Path] = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path, root_path, exclude_dirs):
            continue
        if any(parent in removed_dirs for parent in path.parents):
            continue
        if path.suffix.lower() in CLEAN_EXTENSIONS:
            files_to_remove.append(path)
            continue
        if path.parent == root_path and path.name in ROOT_FILE_NAMES:
            files_to_remove.append(path)
    return files_to_remove


def _collect_target_dir_files(root_path: Path, exclude_dirs: set[str]) -> list[Path]:
    """Collect output and log files that are safe to prune from the target root."""
    files_to_remove: list[Path] = []
    for dir_name, extensions in TARGET_DIR_EXTENSIONS.items():
        if dir_name in exclude_dirs:
            continue
        target_dir = root_path / dir_name
        if not target_dir.exists() or not target_dir.is_dir():
            continue
        for child in target_dir.iterdir():
            if child.is_file() and child.suffix.lower() in extensions:
                files_to_remove.append(child)
    return files_to_remove


def clean_bytecode_cache(root_dir: str | Path = ".", exclude_dirs: list[str] | None = None) -> None:
    """Remove cache, build, test, and transient output artifacts.

    Args:
        root_dir: Repository root or subdirectory to clean.
        exclude_dirs: Directory names to skip anywhere below ``root_dir``.
    """
    root_path = Path(root_dir).resolve()
    exclude_set = set(exclude_dirs or [])

    print("\n============================================================")
    print(" OBSIDIANDROID PROJECT CLEANUP UTILITY")
    print(" Removes caches, test scratch dirs, build traces, logs, and temp files")
    print("============================================================")
    print(" Cleaning Target:", root_path, "\n")

    start_time = time.time()
    count_dirs = 0
    count_files = 0

    dirs_to_remove = _collect_cleanup_dirs(root_path, exclude_set)
    removed_dir_set = set(dirs_to_remove)
    files_to_remove = _collect_extension_files(root_path, exclude_set, removed_dir_set)
    files_to_remove.extend(_collect_target_dir_files(root_path, exclude_set))

    for directory in dirs_to_remove:
        if remove_dir(directory):
            count_dirs += 1

    seen_files: set[Path] = set()
    for file_path in sorted(files_to_remove):
        if file_path in seen_files or not file_path.exists():
            continue
        seen_files.add(file_path)
        if remove_file(file_path):
            count_files += 1

    elapsed = round(time.time() - start_time, 2)
    print("\n------------------------------------------------------------")
    print(" CLEANUP SUMMARY")
    print("------------------------------------------------------------")
    print(f" Directories removed : {count_dirs}")
    print(f" Files removed       : {count_files}")
    print(f" Time elapsed        : {elapsed:.2f} seconds")
    print("------------------------------------------------------------\n")


def _build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the cleanup utility."""
    parser = argparse.ArgumentParser(description="Cleanup build and cache artifacts.")
    parser.add_argument("path", nargs="?", default=".", help="Directory to clean.")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory name to exclude from search (can be used multiple times).",
    )
    return parser


if __name__ == "__main__":
    parser = _build_argument_parser()
    args = parser.parse_args()

    if not Path(args.path).exists():
        print("[FATAL] The path does not exist:", args.path)
        sys.exit(1)

    clean_bytecode_cache(args.path, exclude_dirs=args.exclude)
