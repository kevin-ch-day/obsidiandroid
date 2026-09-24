"""Operational assessment CLI. Storage backend is explicitly selected."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def format_assessment(result: dict) -> str:
    """Present the canonical service result without additional inference."""
    lines = [f"SHA-256: {result['artifact']['sha256']}"]
    for key in ("artifact_label", "type", "family", "variant"):
        item = result["assessment"][key]
        value = item["value"]
        if isinstance(value, dict):
            value = value.get("name") or value.get("slug")
        lines.append(f"{key.replace('_', ' ').title()}: {value or 'Unknown'} [{item['state']}]")
        if item["state"] == "conflict":
            labels = [
                str(c.get("name") or c.get("value", {}).get("name") or c.get("id"))
                for c in item["candidates"]
            ]
            lines.append(
                "  Candidates: " + (", ".join(labels) or "open upstream governance conflict")
            )
    for key in ("erebus", "permissions", "scytale"):
        lines.append(f"Evidence / {key}: {result['evidence'][key]['availability']}")
    if result["processing"]["status"] == "unsupported_artifact":
        lines.append(
            "Catalog identity: "
            f"platform={result['artifact']['platform']['value'] or 'Unknown'}; "
            f"format={result['artifact']['format']['value'] or 'Unknown'}"
        )
        lines.append(
            "Catalog identity does not meet V1 Android/APK support requirements; "
            "this does not establish invalid APK bytes."
        )
        lines.append("Use 'explain' for stored evidence gaps and review steps.")
    lines.extend(
        [
            "Method: governed evidence / explicit rules (no ML)",
            f"Revision: {result['revision']} ({result['assessment_id']})",
            f"Status: {result['processing']['status']}",
        ]
    )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("assess", "current", "history", "by-id", "compare", "explain")
    )
    parser.add_argument("sha256", help="Artifact SHA; immutable assessment ID for by-id/compare")
    parser.add_argument("--against", help="Second immutable assessment ID for compare")
    parser.add_argument(
        "--limit",
        type=int,
        help="Bounded history page size (1-200); JSON uses a page envelope",
    )
    parser.add_argument(
        "--after-revision", type=int, default=0, help="History cursor; requires --limit"
    )
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument(
        "--store",
        type=Path,
        help="Local SQLite assessment sidecar; never a production DSN",
    )
    backend.add_argument(
        "--database", help="Explicit MariaDB assessment catalog (no auto migration)"
    )
    parser.add_argument("--db-option-file", type=Path, help="Private MySQL client option file")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Separate production authorization required",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Frozen exact-hash evidence JSON; required for assess",
    )
    parser.add_argument(
        "--code-version",
        default=None,
        help="Reviewed source fingerprint/Git revision; defaults to an automatic source hash",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the same contract used by future API callers",
    )
    args = parser.parse_args(argv)
    from obsidiandroid.assessment import (
        AssessmentService,
        AssessmentStore,
        FrozenEvidenceSource,
        validate_sha256,
    )
    from obsidiandroid.assessment.mariadb_store import AssessmentPersistenceError

    try:
        sha = validate_sha256(args.sha256)
        if args.action == "compare":
            if not args.against:
                parser.error("compare requires --against")
            validate_sha256(args.against)
        elif args.against:
            parser.error("--against is only valid for compare")
        if args.limit is not None:
            if args.action != "history":
                parser.error("--limit is only valid for history")
            from obsidiandroid.assessment.revisions import validate_page

            validate_page(args.limit, args.after_revision)
        elif args.after_revision:
            parser.error("--after-revision requires --limit")
        if args.action == "assess" and args.snapshot is None:
            parser.error("assess requires --snapshot")
        if args.database:
            import mysql.connector

            from obsidiandroid.assessment.mariadb_store import MariaDBAssessmentStore

            if not args.db_option_file:
                parser.error("--database requires --db-option-file")
            store = MariaDBAssessmentStore(
                lambda: mysql.connector.connect(
                    option_files=str(args.db_option_file),
                    database=args.database,
                    autocommit=False,
                ),
                database=args.database,
                allow_production=args.allow_production,
            )
        else:
            store = AssessmentStore(args.store, read_only=args.action != "assess")
        if args.action == "assess":
            service = AssessmentService(
                FrozenEvidenceSource.load(args.snapshot),
                store,
                code_version=args.code_version,
            )
            result = service.assess(sha)
        else:
            service = AssessmentService(None, store)
            if args.action in ("current", "explain"):
                result = service.current(sha)
            elif args.action == "by-id":
                result = service.by_id(sha)
            elif args.action == "compare":
                result = service.compare(sha, args.against)
            elif args.limit is not None:
                result = service.history_page(
                    sha, limit=args.limit, after_revision=args.after_revision
                )
            else:
                result = service.history(sha)
        if result is None or result == []:
            print(
                json.dumps(
                    {
                        "status": "not_assessed",
                        ("assessment_id" if args.action == "by-id" else "artifact_sha256"): sha,
                    }
                )
                if args.json
                else "No stored assessment."
            )
            return 3
        if args.action == "explain":
            from obsidiandroid.diagnostics.assessment_gaps import (
                explain_assessment,
                format_explanation,
            )

            report = explain_assessment(result)
            print(
                json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False)
                if args.json
                else format_explanation(report)
            )
            return 0
        if args.json:
            print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
        elif args.action == "compare":
            print(f"Conclusions changed: {'yes' if result['conclusions_changed'] else 'no'}")
            for change in result["changes"]:
                if change["category"] != "revision_metadata":
                    print(
                        f"{change['path']} [{change['category']}]: {json.dumps(change['before'], ensure_ascii=False)} -> {json.dumps(change['after'], ensure_ascii=False)}"
                    )
        elif args.limit is not None:
            print(
                "\n\n".join(format_assessment(r) for r in result["records"])
                or "No revisions after this cursor."
            )
            if result["next_after_revision"] is not None:
                print(f"Next cursor: --after-revision {result['next_after_revision']}")
        elif isinstance(result, list):
            print("\n\n".join(format_assessment(r) for r in result))
        else:
            print(format_assessment(result))
        return 0
    except (ValueError, OSError, sqlite3.Error, AssessmentPersistenceError) as exc:
        # Option-file parsers and filesystem exceptions can include secret values
        # or source lines. Keep type/numeric errno, never arbitrary exception text.
        errno = getattr(exc, "errno", None)
        if type(errno) is not int:
            errno = getattr(exc.__cause__, "errno", None)
        error = {
            "status": "error",
            "error_type": type(exc).__name__,
            "errno": errno if type(errno) is int else None,
        }
        print(
            json.dumps(error)
            if args.json
            else f"Assessment input unavailable: {error['error_type']} (errno={error['errno']})",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
