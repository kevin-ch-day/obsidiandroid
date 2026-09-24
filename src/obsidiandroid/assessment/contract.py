"""Validation at the local assessment persistence boundary."""

from __future__ import annotations

from datetime import datetime

from .composition import CONTRACT_VERSION, validate_sha256

STATUSES = {
    "complete",
    "complete_with_unresolved_fields",
    "complete_with_conflict",
    "insufficient_evidence",
    "unsupported_artifact",
    "error",
}


def validate_body(body: dict, assessed_at_utc: str) -> None:
    """Reject malformed records before allocating an immutable revision.

    Args:
        body: Revision-free result returned by the shared composer.
        assessed_at_utc: ISO 8601 time with an explicit UTC offset.

    Raises:
        ValueError: The contract or field provenance is incomplete.
    """
    try:
        if body["contract_version"] != CONTRACT_VERSION:
            raise ValueError("Unsupported assessment contract")
        sha = body["artifact"]["sha256"]
        if sha != validate_sha256(sha):
            raise ValueError("Stored SHA must be lowercase")
        when = datetime.fromisoformat(assessed_at_utc.replace("Z", "+00:00"))
        if when.utcoffset() is None or when.utcoffset().total_seconds() != 0:
            raise ValueError("Assessment timestamp requires UTC")
        if body["processing"]["status"] not in STATUSES:
            raise ValueError("Unknown processing status")
        provenance = body["provenance"]
        if not all(
            provenance[k]
            for k in ("engine_version", "code_version", "rule_id", "evidence_digest")
        ):
            raise ValueError("Assessment provenance is incomplete")
        references = provenance["references"]
        fields = [
            body["artifact"][k]
            for k in ("platform", "format", "package_name", "version")
        ]
        fields += [
            body["assessment"][k]
            for k in ("artifact_label", "type", "family", "variant")
        ]
        for item in fields:
            if item["state"] not in {
                "supported",
                "unresolved",
                "conflict",
                "unsupported",
            }:
                raise ValueError("Unknown field state")
            if item["state"] == "supported" and (
                item["value"] is None or not item["evidence_refs"]
            ):
                raise ValueError(
                    "Supported field requires a value and source references"
                )
            if (
                item["state"] in {"conflict", "unresolved"}
                and item["value"] is not None
            ):
                raise ValueError(
                    "Unresolved/conflicting field cannot claim a selected value"
                )
            if not set(item["evidence_refs"]) <= references.keys():
                raise ValueError("Field references missing from provenance")
        for source in ("erebus", "permissions", "scytale"):
            if not body["evidence"][source]["availability"]:
                raise ValueError("Source availability is required")
        if body["confidence"]["model_probability"] is not None:
            raise ValueError("V1 does not produce model probabilities")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Incomplete assessment contract") from exc
