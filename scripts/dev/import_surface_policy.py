"""Static import-surface policies for :mod:`scripts.dev.check_import_surface`.

AST/file-system checks only (no ``importlib`` of project packages). Repo-root ``utils``
was removed; thin-compat policy tuple is empty but kept for future optional trees.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_UTF8_BOM = b"\xef\xbb\xbf"
CANONICAL_CODE_LEGACY_IMPORT_ROOTS = frozenset(
    {
        "analysis",
        "ml_classification",
    }
)
# First path segment of ``# Filename:`` headers under ``src/`` must not name a legacy tree.
CANONICAL_FILENAME_HEADER_BAD_ROOTS = frozenset(
    {
        *CANONICAL_CODE_LEGACY_IMPORT_ROOTS,
        "database",
    }
)
_CANONICAL_CODE_IMPORT_SCAN_ROOTS = ("src", "scripts")
CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST = frozenset(
    {
        Path("scripts/dev/check_import_surface.py"),
    }
)
NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST = frozenset(
    {
        Path("tests/test_obsidiandroid_package_surface.py"),
    }
)
LEGACY_LEAF_SHIM_ROOTS = ("analysis", "ml_classification")
LEGACY_LEAF_SHIM_MAX_LINES = 16
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


@dataclass(frozen=True)
class ThinCompatShimPolicy:
    """Declarative checks for star-import / re-export compatibility modules."""

    label: str
    relative_parts: tuple[str, ...]
    max_lines: int
    required_substrings: tuple[str, ...]
    relocate_hint: str
    exclude_names: frozenset[str] = frozenset()


THIN_COMPAT_SHIM_POLICIES: tuple[ThinCompatShimPolicy, ...] = ()

__all__ = (
    "CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST",
    "CANONICAL_CODE_LEGACY_IMPORT_ROOTS",
    "CANONICAL_FILENAME_HEADER_BAD_ROOTS",
    "LEGACY_LEAF_SHIM_MAX_LINES",
    "LEGACY_LEAF_SHIM_ROOTS",
    "NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST",
    "THIN_COMPAT_SHIM_POLICIES",
    "ThinCompatShimPolicy",
    "collect_canonical_code_legacy_imports",
    "collect_legacy_leaf_shim_violations",
    "collect_nonparity_test_legacy_imports",
    "collect_stale_canonical_filename_headers",
    "collect_thin_compat_shim_violations",
    "collect_utf8_bom_python_sources",
    "legacy_root_import_violations",
)


def legacy_root_import_violations(tree: ast.AST, rel_posix: str) -> list[str]:
    """Lines like ``path:lineno: ...`` for imports rooted at legacy compatibility packages."""
    bad: list[str] = []
    roots = CANONICAL_CODE_LEGACY_IMPORT_ROOTS
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in roots:
                    bad.append(f"{rel_posix}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in roots:
                bad.append(f"{rel_posix}:{node.lineno}: from {node.module} import ...")
    return bad


def _collect_legacy_imports_under_scan_roots(
    repo_root: Path,
    *,
    scan_roots: tuple[Path, ...],
    path_allowlist: frozenset[Path],
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
            bad.extend(legacy_root_import_violations(tree, rel.as_posix()))
    return bad


def _validate_single_thin_compat_policy(repo_root: Path, policy: ThinCompatShimPolicy) -> list[str]:
    errors: list[str] = []
    shim_dir = repo_root.joinpath(*policy.relative_parts)
    if not shim_dir.is_dir():
        return [f"missing shim directory: {shim_dir.relative_to(repo_root)}"]

    for path in sorted(shim_dir.glob("*.py")):
        if path.name in policy.exclude_names:
            continue
        rel = path.relative_to(repo_root)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{rel}: cannot read file ({exc})")
            continue

        lines = text.splitlines()
        if len(lines) > policy.max_lines:
            errors.append(
                f"{rel}: {len(lines)} lines (max {policy.max_lines}); "
                f"move logic to {policy.relocate_hint}"
            )
            continue

        for sub in policy.required_substrings:
            if sub not in text:
                errors.append(f"{rel}: must contain {sub!r} (canonical import / bootstrap)")

        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error: {exc}")
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                errors.append(
                    f"{rel}: shim must not define {node.name!r} at module level "
                    f"(implement under {policy.relocate_hint})"
                )

    return errors


def collect_thin_compat_shim_violations(repo_root: Path) -> list[str]:
    """Run thin-compat shim policies (none today — repo-root ``utils/`` removed)."""
    out: list[str] = []
    for policy in THIN_COMPAT_SHIM_POLICIES:
        for msg in _validate_single_thin_compat_policy(repo_root, policy):
            out.append(f"[{policy.label}] {msg}")
    return out


def collect_legacy_leaf_shim_violations(repo_root: Path) -> list[str]:
    """Return legacy leaf modules that are no longer thin ModuleType identity shims."""
    errors: list[str] = []
    for root_name in LEGACY_LEAF_SHIM_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            rel = path.relative_to(repo_root)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"{rel}: cannot read file ({exc})")
                continue

            lines = text.splitlines()
            if len(lines) > LEGACY_LEAF_SHIM_MAX_LINES:
                errors.append(
                    f"{rel}: {len(lines)} lines (max {LEGACY_LEAF_SHIM_MAX_LINES}); "
                    "legacy leaf modules must stay thin"
                )
            if "obsidiandroid" not in text:
                errors.append(f"{rel}: must import canonical obsidiandroid implementation")
            if "sys.modules" not in text:
                errors.append(f"{rel}: must register ModuleType identity via sys.modules")

            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError as exc:
                errors.append(f"{rel}: syntax error: {exc}")
                continue

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    errors.append(
                        f"{rel}: shim must not define {node.name!r} at module level "
                        "(implement under src/obsidiandroid)"
                    )
    return errors


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
    )


def collect_nonparity_test_legacy_imports(repo_root: Path) -> list[str]:
    """Return non-parity tests that import legacy compatibility roots directly."""
    return _collect_legacy_imports_under_scan_roots(
        repo_root,
        scan_roots=(repo_root / "tests",),
        path_allowlist=NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST,
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
