#!/usr/bin/env python3
"""Static scan for suspicious ``.predict()`` / ``.predict_proba()`` call sites.

Canonical implementation for :mod:`run_ml_static_scan` (repo-root shim). Writes a
human-readable log under ``logs/`` at the repository root by default. Intended as an optional
pre-commit / CI hygiene step (see ``docs/AGENTS.md``).

Example::

    python run_ml_static_scan.py
    python run_ml_static_scan.py --log /tmp/ml_predict_scan.log --strict
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Python sources for potential .predict() misuse.")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Directory tree to scan (default: repository root).",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=REPO_ROOT / "logs" / "ml_predict_misuse_scan.log",
        help="Path for the detailed log file.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when any warning is reported.",
    )
    args = parser.parse_args()

    from scripts.dev.scan_ml_predict_misuse import run_static_predict_scan

    base = args.root.resolve()
    log_path = args.log
    log_path.parent.mkdir(parents=True, exist_ok=True)

    excludes = [
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        "build",
        "dist",
    ]
    _n_files, n_warn = run_static_predict_scan(str(base), str(log_path), exclude_dirs=excludes)
    if args.strict and n_warn > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
