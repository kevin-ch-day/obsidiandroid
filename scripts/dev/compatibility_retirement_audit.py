"""Audit helpers for compatibility-retirement readiness."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.dev.compatibility_retirement_manifest import LEGACY_SUBTREE_RETIREMENT_BUCKETS

_SKIP_DIR_PARTS = frozenset(
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

_DEFAULT_EXCLUDES = frozenset(
    {
        Path("scripts/dev/check_import_surface.py"),
        Path("scripts/dev/import_surface_policy.py"),
        Path("scripts/dev/compatibility_retirement_manifest.py"),
        Path("scripts/dev/compatibility_retirement_audit.py"),
        Path("scripts/dev/report_compatibility_retirement.py"),
        Path("tests/test_legacy_shim_parity.py"),
        Path("tests/test_import_surface_guardrails.py"),
    }
)


def _import_matches_prefix(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def collect_external_legacy_import_callers(
    repo_root: Path,
    prefixes: tuple[str, ...],
    *,
    excluded_paths: frozenset[Path] = _DEFAULT_EXCLUDES,
) -> list[str]:
    """Return import sites outside legacy trees for the given legacy import prefixes."""
    hits: list[str] = []
    for path in sorted(repo_root.rglob("*.py")):
        rel = path.relative_to(repo_root)
        if rel in excluded_paths:
            continue
        if any(part in _SKIP_DIR_PARTS for part in path.parts):
            continue
        if rel.parts and rel.parts[0] in {"analysis", "ml_classification", "database"}:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(_import_matches_prefix(alias.name, prefix) for prefix in prefixes):
                        hits.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(_import_matches_prefix(node.module, prefix) for prefix in prefixes):
                    hits.append(f"{rel}:{node.lineno}: from {node.module} import ...")
    return hits


def collect_ready_now_bucket_callers(repo_root: Path) -> dict[str, list[str]]:
    """Return external legacy-import callers for subtrees marked ready to deprecate now."""
    out: dict[str, list[str]] = {}
    for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        if entry.readiness != "ready to deprecate now":
            continue
        hits = collect_external_legacy_import_callers(repo_root, entry.import_prefixes)
        out[entry.tree] = hits
    return out


def collect_bucket_callers(repo_root: Path) -> dict[str, list[str]]:
    """Return external legacy-import callers for all retirement buckets with import prefixes."""
    out: dict[str, list[str]] = {}
    for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        if not entry.import_prefixes:
            continue
        out[entry.tree] = collect_external_legacy_import_callers(repo_root, entry.import_prefixes)
    return out


def collect_legacy_subtree_python_files(repo_root: Path, subtree: str) -> list[Path]:
    """Return Python files that belong to one legacy subtree bucket."""
    subtree_path = repo_root / subtree
    if "/*.py" in subtree:
        base = repo_root / subtree.split("/*.py", 1)[0]
        files = sorted(path for path in base.glob("*.py") if path.is_file())
        if subtree.startswith("database/*.py"):
            return [path for path in files if path.name not in {"__init__.py", "split_db_health.py"}]
        return files
    if subtree_path.is_file():
        return [subtree_path]
    if subtree_path.is_dir():
        return sorted(path for path in subtree_path.rglob("*.py") if path.is_file())
    return []


def canonical_target_exists(repo_root: Path, canonical_target: str) -> bool:
    """Return whether the canonical module/package target exists under ``src/obsidiandroid``."""
    target = repo_root / "src" / canonical_target.replace(".", "/")
    return target.with_suffix(".py").exists() or target.is_dir()


__all__ = (
    "collect_bucket_callers",
    "canonical_target_exists",
    "collect_external_legacy_import_callers",
    "collect_legacy_subtree_python_files",
    "collect_ready_now_bucket_callers",
)
