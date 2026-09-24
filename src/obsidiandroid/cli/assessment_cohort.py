"""Offline verification, exact-hash inspection and follow-ups for sealed cohorts."""

from __future__ import annotations
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--expect-checksums-sha256", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--sha256")
    mode.add_argument("--followups", action="store_true")
    args = parser.parse_args(argv)
    from obsidiandroid.assessment_batch.cohort import FrozenCohort

    try:
        cohort = FrozenCohort(
            args.packet, expected_checksums_sha256=args.expect_checksums_sha256
        )
        result = (
            cohort.inspect(args.sha256)
            if args.sha256
            else cohort.followups()
            if args.followups
            else cohort.summary()
        )
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(
            json.dumps(
                {
                    "status": "verification_failed",
                    "error_type": type(exc).__name__,
                    "mutations_performed": False,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
