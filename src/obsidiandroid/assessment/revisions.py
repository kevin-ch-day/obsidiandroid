"""Bounded history navigation and deterministic explanation of revision changes."""

from __future__ import annotations

from .composition import canonical_json


def validate_page(limit: int, after_revision: int) -> None:
    """Bound the work and use a stable revision cursor instead of SQL offsets."""
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("History limit must be an integer between 1 and 200")
    if type(after_revision) is not int or not 0 <= after_revision < 2**63:
        raise ValueError("History cursor must be a nonnegative signed 64-bit revision")


def history_page(sha: str, rows: list[dict], limit: int) -> dict:
    """Build an envelope without altering the V1 record objects inside it."""
    records = rows[:limit]
    return {
        "artifact_sha256": sha,
        "records": records,
        "next_after_revision": records[-1]["revision"] if len(rows) > limit else None,
    }


def compare_revisions(before: dict, after: dict) -> dict:
    """Separate changed conclusions from evidence, code and persistence metadata.

    List order is significant in already canonical assessment records. Lists are
    compared as values so changed candidates/references stay understandable.
    """
    if before["artifact"]["sha256"] != after["artifact"]["sha256"]:
        raise ValueError("Revision comparison requires the same artifact SHA")
    changes = []
    missing = object()
    metadata = {
        "assessment_id",
        "revision",
        "previous_assessment_id",
        "assessed_at_utc",
    }

    def walk(left, right, parts):
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() | right.keys()):
                walk(left.get(key, missing), right.get(key, missing), [*parts, key])
            return
        if (
            left is not missing
            and right is not missing
            and canonical_json(left) == canonical_json(right)
        ):
            return
        top = parts[0]
        category = "assessment"
        if top in metadata:
            category = "revision_metadata"
        elif top == "provenance":
            category = (
                "engine_and_code"
                if len(parts) > 1
                and parts[1] in {"code_version", "engine_version", "rule_id"}
                else "provenance"
            )
        elif top == "evidence":
            category = "evidence"
        elif top == "processing":
            category = "processing"
        elif top == "confidence":
            category = "confidence"
        elif len(parts) < 3 or parts[2] not in {"state", "value", "candidates"}:
            category = "field_support"
        path = "/" + "/".join(p.replace("~", "~0").replace("/", "~1") for p in parts)
        changes.append(
            {
                "path": path,
                "category": category,
                "before_present": left is not missing,
                "after_present": right is not missing,
                "before": None if left is missing else left,
                "after": None if right is missing else right,
            }
        )

    walk(before, after, [])
    return {
        "artifact_sha256": before["artifact"]["sha256"],
        "before_assessment_id": before["assessment_id"],
        "after_assessment_id": after["assessment_id"],
        "same_record": not changes,
        "conclusions_changed": any(c["category"] == "assessment" for c in changes),
        "changes": changes,
    }
