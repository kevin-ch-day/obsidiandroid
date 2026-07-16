"""Static import-surface policies for :mod:`scripts.dev.check_import_surface`.

AST/file-system checks only (no ``importlib`` of project packages). Repo-root
compatibility Python trees are retired; the repository-root ``database/``
directory remains only for SQL assets. Thin-compat policy is empty but retained
as an extension point.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from scripts.dev.compatibility_retirement_manifest import (
    CANONICAL_CODE_COMPATIBILITY_IMPORT_ROOTS as _CANONICAL_CODE_COMPATIBILITY_IMPORT_ROOTS,
    CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST as _CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST,
    CANONICAL_FILENAME_HEADER_BAD_ROOTS as _CANONICAL_FILENAME_HEADER_BAD_ROOTS,
    EARLY_DEPRECATION_READY_TREES as _EARLY_DEPRECATION_READY_TREES,
    LEGACY_COMPATIBILITY_IMPORT_ROOTS as _LEGACY_COMPATIBILITY_IMPORT_ROOTS,
    NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST as _NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST,
    RETIRED_COMPATIBILITY_ROOTS as _RETIRED_COMPATIBILITY_ROOTS,
    RETIRED_ROOT_COMPATIBILITY_FILES as _RETIRED_ROOT_COMPATIBILITY_FILES,
)

_UTF8_BOM = b"\xef\xbb\xbf"
CANONICAL_CODE_LEGACY_IMPORT_ROOTS = frozenset(_CANONICAL_CODE_COMPATIBILITY_IMPORT_ROOTS)
# First path segment of ``# Filename:`` headers under ``src/`` must not name a legacy tree.
CANONICAL_FILENAME_HEADER_BAD_ROOTS = frozenset(_CANONICAL_FILENAME_HEADER_BAD_ROOTS)
_CANONICAL_CODE_IMPORT_SCAN_ROOTS = ("src", "scripts")
CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST = frozenset(_CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST)
NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST = frozenset(_NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST)
READY_NOW_LEGACY_SHIM_BATCHES = frozenset(_EARLY_DEPRECATION_READY_TREES)
RETIRED_COMPATIBILITY_ROOTS = frozenset(_RETIRED_COMPATIBILITY_ROOTS)
RETIRED_ROOT_COMPATIBILITY_FILES = frozenset(_RETIRED_ROOT_COMPATIBILITY_FILES)
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
    "NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST",
    "READY_NOW_LEGACY_SHIM_BATCHES",
    "THIN_COMPAT_SHIM_POLICIES",
    "ThinCompatShimPolicy",
    "collect_canonical_code_legacy_imports",
    "collect_retired_compatibility_tree_violations",
    "collect_retired_compatibility_file_violations",
    "collect_ml_training_plain_shim_violations",
    "collect_nonparity_test_legacy_imports",
    "collect_ready_now_shim_helper_violations",
    "collect_stale_canonical_filename_headers",
    "collect_thin_compat_shim_violations",
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


def _ready_now_batch_python_files(repo_root: Path, subtree: str) -> list[Path]:
    if "/*.py" in subtree:
        base = repo_root / subtree.split("/*.py", 1)[0]
        files = sorted(path for path in base.glob("*.py") if path.is_file())
        if subtree.startswith("database/*.py"):
            return [path for path in files if path.name not in {"__init__.py", "split_db_health.py"}]
        return files
    subtree_path = repo_root / subtree
    if subtree_path.is_file():
        return [subtree_path]
    if subtree_path.is_dir():
        return sorted(path for path in subtree_path.rglob("*.py") if path.is_file())
    return []


def collect_ready_now_shim_helper_violations(repo_root: Path) -> list[str]:
    """Return ready-now shim batches that drift from the shared helper/warning pattern."""
    errors: list[str] = []
    for subtree in READY_NOW_LEGACY_SHIM_BATCHES:
        for path in _ready_now_batch_python_files(repo_root, subtree):
            rel = path.relative_to(repo_root)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"{rel}: cannot read file ({exc})")
                continue
            if rel.name == "__init__.py" and rel.parts[0] == "ml_classification":
                if "lazy_legacy_submodule(" not in text and "import_legacy_shim(" not in text:
                    errors.append(
                        f"{rel}: ready-now ml_classification package shim must use "
                        "lazy_legacy_submodule(...) or import_legacy_shim(...)"
                    )
                if "warn=True" not in text:
                    errors.append(f"{rel}: ready-now ml_classification package shim must opt in to warn=True")
                continue
            if "import_legacy_shim(" not in text:
                errors.append(f"{rel}: ready-now legacy shim must use import_legacy_shim(...)")
            if "warn=True" not in text:
                errors.append(f"{rel}: ready-now legacy shim must opt in to warn=True")
            if "importlib.import_module(" in text:
                errors.append(f"{rel}: ready-now legacy shim should not call importlib.import_module directly")
    return errors


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


def collect_ml_training_plain_shim_violations(repo_root: Path) -> list[str]:
    """Return retired ML-training shim violations in synthetic fixtures, if any."""
    errors: list[str] = []
    training_root = repo_root / "ml_classification" / "training"
    if not training_root.exists():
        return errors
    for rel in sorted(
        path.relative_to(repo_root)
        for path in training_root.rglob("*.py")
        if path.is_file() and path.name != "__init__.py"
    ):
        path = repo_root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{rel}: cannot read file ({exc})")
            continue
        if "import_legacy_shim(" not in text:
            errors.append(f"{rel}: plain ml_classification.training shim must use import_legacy_shim(...)")
        if "sys.modules[__name__] = _mod" not in text and "sys.modules[__name__] = _canonical" not in text:
            errors.append(
                f"{rel}: plain ml_classification.training shim must register sys.modules[__name__] alias"
            )
        if "importlib.import_module(" in text or "from importlib import import_module" in text:
            errors.append(
                f"{rel}: plain ml_classification.training shim should not use direct importlib import patterns"
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
        forbidden_roots=CANONICAL_CODE_LEGACY_IMPORT_ROOTS,
    )


def collect_nonparity_test_legacy_imports(repo_root: Path) -> list[str]:
    """Return non-parity tests that import legacy compatibility roots directly."""
    return _collect_legacy_imports_under_scan_roots(
        repo_root,
        scan_roots=(repo_root / "tests",),
        path_allowlist=NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST,
        forbidden_roots=frozenset(_LEGACY_COMPATIBILITY_IMPORT_ROOTS),
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
