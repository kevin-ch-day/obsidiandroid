"""Shared bootstrap helpers for repo-root ``scripts/`` entrypoints."""

from __future__ import annotations

import sys
from pathlib import Path


def prepare_script_runtime(script_file: str | Path) -> Path:
    """Ensure repository root and ``src/`` are importable for a script entrypoint.

    Args:
        script_file: ``__file__`` from the calling script.

    Returns:
        Resolved repository root.
    """

    script_path = Path(script_file).resolve()
    repo_root = _find_repo_root(script_path)
    for candidate in (repo_root, repo_root / "src"):
        if not candidate.exists():
            continue
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
    return repo_root


def _find_repo_root(script_path: Path) -> Path:
    for parent in [script_path.parent, *script_path.parents]:
        if (parent / "scripts").is_dir() and (parent / "src").is_dir():
            return parent
    return script_path.parents[1]
