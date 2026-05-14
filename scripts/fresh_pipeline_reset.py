#!/usr/bin/env python3
"""Wipe configured pipeline output for a clean next run.

Removes canonical layout under ``DEFAULT_OUTPUT_DIR`` (``runs``, ``bundles``,
``reports``, ``diagnostics``, ``latest``, ``promoted``),
``vendor_raw``, and noisy root-level bundles/legacy filenames. Also removes
legacy log directories ``<output>/diagnostics/runtime_logs`` and
``<output>/diagnostics/logs`` from older layouts (pipeline logs now live in
repository ``logs/`` — see :func:`obsidiandroid.common.output_paths.project_logs_root`).
Optionally preserve the main workbook. Recreates empty layout via
:func:`obsidiandroid.common.output_paths.ensure_output_layout` after deletion.

Destructive operations require ``--yes``. Without it, prints a dry-run plan.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.common import output_cleanup_clutter as occ  # noqa: E402


def _resolve_output_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    from obsidiandroid.common.output_paths import output_root

    return output_root()


def _subdir_map(base: Path) -> dict[str, Path]:
    from config import app_config

    return {
        "runs": base / str(getattr(app_config, "OUTPUT_RUNS_SUBDIR", "runs")),
        "bundles": base / str(getattr(app_config, "OUTPUT_BUNDLES_SUBDIR", "bundles")),
        "reports": base / str(getattr(app_config, "OUTPUT_REPORTS_SUBDIR", "reports")),
        "diagnostics": base / str(getattr(app_config, "OUTPUT_DIAGNOSTICS_SUBDIR", "diagnostics")),
        "latest": base / str(getattr(app_config, "OUTPUT_LATEST_SUBDIR", "latest")),
        "promoted": base / str(getattr(app_config, "OUTPUT_PROMOTED_SUBDIR", "promoted")),
        "vendor_raw": base / "vendor_raw",
    }


def _root_glob_targets(base: Path) -> list[Path]:
    names: list[Path] = []
    for pattern in occ.PAPER_BUNDLE_ARCHIVE_GLOBS + occ.PAPER_BUNDLE_SMOKE_GLOBS:
        names.extend(sorted(base.glob(pattern)))
    for name in occ.LEGACY_OUTPUT_ROOT_FILES:
        path = base / name
        if path.exists():
            names.append(path)
    names.extend(sorted(base.glob(occ.WORKBOOK_CORRUPT_GLOB)))
    return sorted({p.resolve() for p in names}, key=lambda p: str(p))


def _protected_root_paths(base: Path) -> frozenset[str]:
    return frozenset(
        {
            (base / "obsidiandroid_outputs.xlsx").resolve().as_posix(),
            (base / "obsidiandroid_outputs.xlsx.lock").resolve().as_posix(),
        }
    )


def _targets_for_wipe(base: Path, *, purge_workbooks: bool) -> list[Path]:
    protected = frozenset() if purge_workbooks else _protected_root_paths(base)
    resolved_base = base.resolve()

    dirs = _subdir_map(base)
    targets: list[Path] = []
    for path in dirs.values():
        if path.exists():
            targets.append(path.resolve())
    targets.extend(
        [
            p
            for p in _root_glob_targets(base)
            if p.resolve().as_posix() not in protected
        ]
    )

    for segments in occ.LEGACY_OUTPUT_LOG_DIR_SEGMENTS:
        legacy_logs = base.joinpath(*segments)
        if legacy_logs.exists():
            targets.append(legacy_logs.resolve())
    if purge_workbooks:
        for name in ("obsidiandroid_outputs.xlsx", "obsidiandroid_outputs.xlsx.lock"):
            book = resolved_base / name
            if book.exists():
                targets.append(book.resolve())
    uniq: dict[str, Path] = {}
    for path in sorted(targets, key=lambda p: str(p)):
        try:
            path.relative_to(resolved_base)
        except ValueError:
            continue
        key = path.as_posix()
        if key not in uniq:
            uniq[key] = path
    return list(uniq.values())


def rebuild_output_layout_under(base: Path) -> None:
    """Create canonical top-level dirs under arbitrary output root."""
    base.mkdir(parents=True, exist_ok=True)
    for path in _subdir_map(base).values():
        path.mkdir(parents=True, exist_ok=True)


def wipe_output_directory(
    base: Path,
    *,
    apply: bool,
    purge_workbooks: bool,
) -> list[str]:
    """Planning or execute removal under ``base``.

    Args:
        base: Output root directory.
        apply: When True, ``shutil.rmtree`` / unlink; when False, no writes.
        purge_workbooks: When False, skips ``obsidiandroid_outputs*.xlsx`` at root
            (except legacy copies matched by globs).

    Returns:
        Human-readable paths removed or that would be removed.
    """
    base = base.resolve()
    hits = _targets_for_wipe(base, purge_workbooks=purge_workbooks)
    descriptions: list[str] = []

    def _describe(path: Path) -> None:
        if path.is_dir():
            descriptions.append(f"dir : {path}")
        else:
            descriptions.append(f"file: {path}")

    if not apply:
        for path in hits:
            _describe(path)
        return descriptions

    for path in hits:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
            _describe(path)
        elif path.is_file():
            path.unlink(missing_ok=True)
            _describe(path)
        elif path.is_symlink() or path.exists():
            path.unlink(missing_ok=True)
            _describe(path)

    rebuild_output_layout_under(base)
    return descriptions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output root override (default: configured DEFAULT_OUTPUT_DIR).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete artifacts (omit for dry-run).",
    )
    parser.add_argument(
        "--purge-workbooks",
        action="store_true",
        help="Also remove obsidiandroid_outputs.xlsx and .lock under the output root.",
    )
    args = parser.parse_args()
    root = _resolve_output_root(args.output_dir or None)

    sane_root = Path("/").resolve()
    if root.resolve() == sane_root:
        print("Refusing unsafe output root.")
        return 2

    if not root.exists():
        print(f"Nothing to do — output directory does not exist: {root}")
        root.mkdir(parents=True, exist_ok=True)
        rebuild_output_layout_under(root)
        return 0

    plan = wipe_output_directory(root, apply=False, purge_workbooks=args.purge_workbooks)
    if not plan:
        print(f"No known pipeline artifacts found under {root}.")
        if args.yes:
            rebuild_output_layout_under(root)
        return 0

    mode = "APPLY delete" if args.yes else "dry-run only"
    print(f"Fresh pipeline reset ({mode}); root={root}")
    for line in plan:
        print(f" - {line}")
    if args.yes:
        removed = wipe_output_directory(root, apply=True, purge_workbooks=args.purge_workbooks)
        print(f"\nRemoved {len(removed)} path(s); empty layout recreated.")
    else:
        print("\nRe-run with --yes to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
