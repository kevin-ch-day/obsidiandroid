"""Dry-run or apply a reviewed, bounded Operational Assessment V1 batch."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--database", required=True)
    parser.add_argument("--db-option-file", required=True, type=Path)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--maximum", type=int, default=250)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--plan", type=Path, help="Reviewed plan required for apply")
    parser.add_argument("--expect-plan-digest")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New plan or receipt; existing paths refused",
    )
    args = parser.parse_args(argv)
    if args.apply and (not args.plan or not args.expect_plan_digest):
        parser.error("apply requires --plan and --expect-plan-digest")
    if not args.apply and (args.plan or args.expect_plan_digest):
        parser.error("reviewed plan arguments require --apply")
    from obsidiandroid.assessment_batch import BatchAssessmentService, load_batch
    from obsidiandroid.assessment_batch.repository import ReviewedMariaDBRepository
    import mysql.connector

    try:
        manifest, snapshot = load_batch(args.manifest, args.snapshot)
        repo = ReviewedMariaDBRepository(
            lambda: mysql.connector.connect(
                option_files=str(args.db_option_file),
                database=args.database,
                autocommit=False,
                connection_timeout=5,
            ),
            database=args.database,
            allow_production=args.allow_production,
        )
        service = BatchAssessmentService(manifest, snapshot, repo, maximum=args.maximum)
        # Reserve output before any apply; durable journal preserves interrupted progress.
        with args.output.open("x") as output:
            if args.apply:
                plan = json.loads(args.plan.read_text())
                with args.output.with_suffix(
                    args.output.suffix + ".journal.jsonl"
                ).open("x") as journal:

                    def emit(row):
                        journal.write(json.dumps(row, sort_keys=True) + "\n")
                        journal.flush()
                        os.fsync(journal.fileno())

                    result = service.apply(
                        plan, expected_plan_digest=args.expect_plan_digest, emit=emit
                    )
            else:
                result = service.plan()
            json.dump(result, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        print(
            json.dumps(
                {
                    "status": result.get("status", "dry_run"),
                    "count": len(result["rows"]),
                    "plan_digest": result["plan_digest"],
                    "clean": result.get("clean"),
                }
            )
        )
        return (
            0 if result.get("status") != "stopped" and result.get("clean", True) else 2
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "no_automatic_retry": True,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
