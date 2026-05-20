"""Read-only authority coverage report for Android sample family/type authority."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.diagnostics.family_type_authority_coverage import (
    DEFAULT_MD,
    DEFAULT_MISSING,
    DEFAULT_UNKNOWN_TYPE,
    DEFAULT_YEAR_TYPE,
    classify_missing_candidate,
    generate_authority_coverage_artifacts,
    temporal_feasibility_label,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD, help="Markdown report output path")
    parser.add_argument("--missing-out", type=Path, default=DEFAULT_MISSING, help="CSV for missing authority-family candidates")
    parser.add_argument("--unknown-type-out", type=Path, default=DEFAULT_UNKNOWN_TYPE, help="CSV for authority families with unknown type")
    parser.add_argument("--year-type-out", type=Path, default=DEFAULT_YEAR_TYPE, help="CSV for authority-typed year/type coverage")
    parser.add_argument(
        "--require-live-view",
        action="store_true",
        help="Fail with a clear warning instead of falling back when the Erebus authority view is unavailable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = generate_authority_coverage_artifacts(
        md_path=args.md_out,
        missing_out=args.missing_out,
        unknown_type_out=args.unknown_type_out,
        year_type_out=args.year_type_out,
        require_live_view=bool(args.require_live_view),
    )
    if not bundle.get("ok", False):
        print(str(bundle.get("warning") or "[WARN] No authority rows returned."))
        return 1

    print(f"[OK] Wrote markdown report: {bundle['md_path']}")
    print(f"[OK] Wrote missing-family candidates: {bundle['missing_out']}")
    print(f"[OK] Wrote unknown-type queue: {bundle['unknown_type_out']}")
    print(f"[OK] Wrote year/type coverage: {bundle['year_type_out']}")
    print(f"[INFO] Source mode: {bundle['source_mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
