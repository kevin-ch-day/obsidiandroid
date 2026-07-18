"""Static import-surface policies for :mod:`scripts.dev.check_import_surface`.

AST/file-system checks only (no ``importlib`` of project packages). Repo-root
compatibility Python trees are retired; the repository-root ``database/``
directory remains only for SQL assets. Thin-compat policy is empty but retained
as an extension point.
"""

from __future__ import annotations

import ast
from pathlib import Path

_UTF8_BOM = b"\xef\xbb\xbf"
CANONICAL_CODE_LEGACY_IMPORT_ROOTS = frozenset({"analysis", "ml_classification", "main"})
# First path segment of ``# Filename:`` headers under ``src/`` must not name a legacy tree.
CANONICAL_FILENAME_HEADER_BAD_ROOTS = frozenset({"analysis", "ml_classification", "database"})
_CANONICAL_CODE_IMPORT_SCAN_ROOTS = ("src", "scripts")
CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST = frozenset({Path("scripts/dev/check_import_surface.py")})
RETIRED_COMPATIBILITY_ROOTS = frozenset({"analysis", "ml_classification"})
RETIRED_ROOT_COMPATIBILITY_FILES = frozenset(
    {Path("database/__init__.py"), Path("database/split_db_health.py")}
)
# Directory name fragments skipped when scanning for UTF-8 BOM (generated / vendor trees).
_BOM_SCAN_SKIP_DIR_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "output",
        "logs",
        ".pytest_tmp",
        "build",
        "dist",
        "htmlcov",
        "wandb",
        "mlruns",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        "node_modules",
        ".cursor",
    }
)

__all__ = (
    "CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST",
    "CANONICAL_CODE_LEGACY_IMPORT_ROOTS",
    "CANONICAL_FILENAME_HEADER_BAD_ROOTS",
    "collect_canonical_code_legacy_imports",
    "collect_retired_compatibility_tree_violations",
    "collect_retired_compatibility_file_violations",
    "collect_nonparity_test_legacy_imports",
    "collect_stale_canonical_filename_headers",
    "collect_utf8_bom_python_sources",
    "legacy_root_import_violations",
)


def legacy_root_import_violations(
    tree: ast.AST,
    rel_posix: str,
    *,
    forbidden_roots: frozenset[str] = CANONICAL_CODE_LEGACY_IMPORT_ROOTS,
) -> list[str]:
    """Lines like ``path:lineno: ...`` for imports rooted at legacy compatibility packages."""
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in forbidden_roots:
                    bad.append(f"{rel_posix}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in forbidden_roots:
                bad.append(f"{rel_posix}:{node.lineno}: from {node.module} import ...")
    return bad


def _collect_legacy_imports_under_scan_roots(
    repo_root: Path,
    *,
    scan_roots: tuple[Path, ...],
    path_allowlist: frozenset[Path],
    forbidden_roots: frozenset[str],
) -> list[str]:
    """Scan ``*.py`` under ``scan_roots`` for imports rooted at legacy compatibility packages."""
    bad: list[str] = []
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in sorted(scan_root.rglob("*.py")):
            rel = path.relative_to(repo_root)
            if rel in path_allowlist:
                continue
            if any(p in _BOM_SCAN_SKIP_DIR_PARTS for p in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                bad.append(f"{rel}: syntax error while scanning imports: {exc}")
                continue
            except OSError as exc:
                bad.append(f"{rel}: cannot read file while scanning imports ({exc})")
                continue
            bad.extend(
                legacy_root_import_violations(
                    tree,
                    rel.as_posix(),
                    forbidden_roots=forbidden_roots,
                )
            )
    return bad


def collect_retired_compatibility_tree_violations(repo_root: Path) -> list[str]:
    """Return retired compatibility roots that were accidentally recreated."""
    return [
        f"{root}: retired compatibility tree should not exist on disk"
        for root in sorted(RETIRED_COMPATIBILITY_ROOTS)
        if (repo_root / root).exists()
    ]


def collect_retired_compatibility_file_violations(repo_root: Path) -> list[str]:
    """Return former root-level compatibility files that were accidentally recreated."""
    return [
        f"{rel.as_posix()}: retired compatibility file should not exist on disk"
        for rel in sorted(RETIRED_ROOT_COMPATIBILITY_FILES)
        if (repo_root / rel).exists()
    ]


def collect_utf8_bom_python_sources(repo_root: Path) -> list[str]:
    """Return repo-relative paths of ``*.py`` files that begin with a UTF-8 BOM byte sequence."""
    bad: list[str] = []
    for path in repo_root.rglob("*.py"):
        if any(p in _BOM_SCAN_SKIP_DIR_PARTS for p in path.parts):
            continue
        if any(p.endswith(".egg-info") for p in path.parts):
            continue
        rel = path.relative_to(repo_root)
        try:
            with path.open("rb") as fh:
                head = fh.read(3)
        except OSError as exc:
            bad.append(f"{rel} (unreadable: {exc})")
            continue
        if head == _UTF8_BOM:
            bad.append(str(rel))
    return bad


def collect_canonical_code_legacy_imports(repo_root: Path) -> list[str]:
    """Return canonical-code imports that point back at legacy compatibility roots."""
    roots = tuple(repo_root.joinpath(name) for name in _CANONICAL_CODE_IMPORT_SCAN_ROOTS)
    return _collect_legacy_imports_under_scan_roots(
        repo_root,
        scan_roots=roots,
        path_allowlist=CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST,
        forbidden_roots=CANONICAL_CODE_LEGACY_IMPORT_ROOTS,
    )


def collect_nonparity_test_legacy_imports(repo_root: Path) -> list[str]:
    """Return non-parity tests that import legacy compatibility roots directly."""
    return _collect_legacy_imports_under_scan_roots(
        repo_root,
        scan_roots=(repo_root / "tests",),
        path_allowlist=frozenset(),
        forbidden_roots=RETIRED_COMPATIBILITY_ROOTS,
    )


def collect_stale_canonical_filename_headers(repo_root: Path) -> list[str]:
    """Return ``src/`` modules whose ``# Filename:`` header starts with a disallowed root.

    Disallowed first segments include legacy compatibility trees and repo-root
    ``database/`` (canonical DB code lives under ``src/obsidiandroid/database/``).
    """
    bad: list[str] = []
    scan_root = repo_root / "src"
    if not scan_root.exists():
        return bad
    for path in sorted(scan_root.rglob("*.py")):
        if any(p in _BOM_SCAN_SKIP_DIR_PARTS for p in path.parts):
            continue
        rel = path.relative_to(repo_root)
        try:
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
        except IndexError:
            continue
        except OSError as exc:
            bad.append(f"{rel}: cannot read file while scanning filename header ({exc})")
            continue

        if not first_line.startswith("# Filename: "):
            continue
        header_path = first_line.removeprefix("# Filename: ").strip()
        header_root = header_path.split("/", 1)[0]
        if header_root in CANONICAL_FILENAME_HEADER_BAD_ROOTS:
            bad.append(f"{rel}: stale filename header {header_path!r}")
    return bad
