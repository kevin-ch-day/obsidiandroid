"""Export the canonical paper-facing cohort census and gate-matrix bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from obsidiandroid.governance.cohort_census import (
    TARGET_PROFILE_IDS,
    build_cohort_census_bundle,
    write_cohort_census_exports,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="paper_exports/docs",
        help="Directory for census/gate-matrix exports.",
    )
    parser.add_argument(
        "--profiles",
        nargs="*",
        default=list(TARGET_PROFILE_IDS),
        help="Profile ids to compare. Defaults to the paper-facing census set.",
    )
    args = parser.parse_args()

    bundle = build_cohort_census_bundle(tuple(args.profiles))
    paths = write_cohort_census_exports(output_dir=Path(args.output_dir), bundle=bundle)
    for key, value in paths.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
