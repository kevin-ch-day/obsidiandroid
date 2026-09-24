"""Explain stored V1 evidence gaps without generating or revising assessments."""

from __future__ import annotations


def explain_assessment(record: dict) -> dict:
    """Project operator follow-ups from the existing record; never infer labels."""
    gaps = []
    artifact = record["artifact"]
    assessment = record["assessment"]
    if record["processing"]["status"] == "unsupported_artifact":
        gaps.append(
            {
                "code": "CATALOG_ARTIFACT_UNSUPPORTED",
                "owner": "Erebus artifact evidence",
                "facts": {
                    "platform": artifact["platform"]["value"],
                    "format": artifact["format"]["value"],
                },
                "reason": assessment["artifact_label"]["reason"],
                "next_step": "Review exact-hash static evidence and the supported catalog binding workflow. "
                "This status does not establish invalid APK bytes.",
            }
        )
    for name in ("type", "family", "variant"):
        field = assessment[name]
        if field["state"] != "supported":
            gaps.append(
                {
                    "code": f"{name.upper()}_{field['state'].upper()}",
                    "owner": "Erebus governed evidence",
                    "facts": {
                        "state": field["state"],
                        "value": field["value"],
                        "candidates": field["candidates"],
                        "evidence_refs": field["evidence_refs"],
                    },
                    "reason": field["reason"],
                    "next_step": "Review conflicting governed sources."
                    if field["state"] == "conflict"
                    else "Retain unresolved state until sample-bound governed evidence is available.",
                }
            )
    permissions = record["evidence"]["permissions"]
    missing = permissions.get("retained_tokens_missing_downstream", [])
    if missing:
        gaps.append(
            {
                "code": "RETAINED_PERMISSION_PROJECTION_GAP",
                "owner": "Erebus permission projection",
                "facts": {
                    "tokens": missing,
                    "evidence_refs": permissions.get("retained_evidence_refs", []),
                },
                "reason": "Retained tokens are not fully represented downstream.",
                "next_step": "Review bounded local materialization; this does not require a new provider request.",
            }
        )
    if permissions["availability"] != "available":
        gaps.append(
            {
                "code": "PERMISSION_EVIDENCE_UNAVAILABLE",
                "owner": "Permission evidence collection",
                "facts": {
                    "availability": permissions["availability"],
                    "observed_token_count": permissions.get("observed_token_count"),
                },
                "reason": "Missing observations do not establish permission absence.",
                "next_step": "Compare exact APK declarations and retained provider evidence separately.",
            }
        )
    if permissions.get("unresolved_count"):
        gaps.append(
            {
                "code": "PERMISSION_SEMANTICS_UNRESOLVED",
                "owner": "Permission Intel governance",
                "facts": {
                    "unresolved_count": permissions["unresolved_count"],
                    "semantic_release": permissions.get("semantic_release"),
                },
                "reason": "Current accepted semantics do not resolve every observed token.",
                "next_step": "Review token identity and release scope; do not equate a lexical prefix with ownership.",
            }
        )
    context = record["provenance"].get("batch_context", {})
    return {
        "evidence_cutoff_at": context.get("evidence_cutoff_at"),
        "snapshot_reference": context.get("snapshot_reference"),
        "static_baseline_reference": context.get("static_baseline_reference"),
        "static_declaration_projection": (
            context.get("static_baseline_reference") or {}
        ).get("static_declaration_projection"),
        "contract": "obsidiandroid.assessment-explanation.v1",
        "artifact_sha256": artifact["sha256"],
        "assessment_id": record["assessment_id"],
        "revision": record["revision"],
        "assessed_at_utc": record["assessed_at_utc"],
        "processing_status": record["processing"]["status"],
        "gaps": gaps,
        "scope": "Stored assessment only; no live upstream refresh or independent APK validation",
        "mutations_performed": False,
    }


def format_explanation(report: dict) -> str:
    lines = [
        f"SHA-256: {report['artifact_sha256']}",
        f"Revision: {report['revision']} ({report['assessment_id']})",
        f"Status: {report['processing_status']}",
        report["scope"],
    ]
    projection = report.get("static_declaration_projection")
    if projection:
        summary = projection["summary"]
        lines.extend(
            [
                "Static declaration accounting: "
                f"{summary['accounted_count']}/{summary['declared_count']}",
                "Static permission semantics: "
                f"{summary['semantically_resolved_count']} resolved; "
                f"{summary['unresolved_count']} unresolved; "
                f"{summary['invalid_or_non_permission_count']} invalid/non-permission",
                "Source: immutable static declaration ledger; legacy provider observations remain separate.",
                f"Projection SHA-256: {projection['file_sha256']}",
            ]
        )
    for gap in report["gaps"]:
        lines.extend(
            [
                f"{gap['code']} — {gap['owner']}",
                f"  {gap['reason'] or 'See referenced evidence.'}",
                f"  Next: {gap['next_step']}",
            ]
        )
    if not report["gaps"]:
        lines.append("No gaps identified by this stored-record diagnostic.")
    return "\n".join(lines)
