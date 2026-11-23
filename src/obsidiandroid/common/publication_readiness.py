"""Shared helpers for publication/evidence readiness semantics."""

from __future__ import annotations

from typing import Any


def coalesce_publication_ready_status(payload: dict[str, Any]) -> str:
    """Resolve the canonical publication-ready status token from mixed payloads."""
    return str(payload.get("publication_ready_status", "") or "unknown").strip() or "unknown"


def coalesce_publication_ready_reasons(payload: dict[str, Any]) -> list[str]:
    """Resolve the canonical publication-ready reasons list from mixed payloads."""
    raw = payload.get("publication_ready_reasons", [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def publication_ready_status_light(status: object) -> str:
    """Map publication-ready status tokens to GREEN/YELLOW/RED for operator surfaces."""
    token = str(status or "").strip().lower()
    if token in {"ready", "pass", "yes"}:
        return "GREEN"
    if token in {"fail", "not_ready", "blocked"}:
        return "RED"
    return "YELLOW"


def publication_ready_display(raw_status: object, *, run_class: str, evidence_mode: bool) -> str:
    """Human-facing publication-ready display string for review surfaces."""
    token = str(raw_status or "").strip().lower()
    if token in {"ready", "pass", "yes"}:
        return "Yes"
    if token in {"fail", "not_ready", "blocked"}:
        return "Blocked"
    if run_class == "Exploratory":
        return "Not applicable — exploratory run"
    if evidence_mode:
        return "No"
    return "No — exploratory run"


def evaluate_publication_ready_status(
    *,
    paper_mode: bool,
    manifest: dict[str, Any] | None,
    compliance_report: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Return canonical publication-ready status and reasons."""
    reasons: list[str] = []
    if not paper_mode:
        return ("NOT_APPLICABLE", reasons)
    if isinstance(compliance_report, dict) and str(compliance_report.get("overall_status", "")).lower() != "pass":
        reasons.append("paper_compliance_not_pass")
    if isinstance(manifest, dict):
        if manifest.get("vendor_fallback_used"):
            reasons.append("vendor_fallback_used")
        if manifest.get("non_standard_features"):
            reasons.append("non_standard_features")
    return ("PASS" if len(reasons) == 0 else "FAIL", reasons)


def publication_ready_payload(status: object, reasons: list[str] | None = None) -> dict[str, Any]:
    """Return canonical publication-ready fields for JSON payloads."""
    normalized_status = str(status or "").strip() or "unknown"
    normalized_reasons = [str(item) for item in (reasons or []) if str(item).strip()]
    return {
        "publication_ready_status": normalized_status,
        "publication_ready_reasons": normalized_reasons,
    }


def claim_audit_alias_name(*, profile_id: str, evidence_mode: bool, paper_mode: bool) -> str:
    """Return the profile-appropriate claim audit alias for index artifacts."""
    if bool(evidence_mode or paper_mode):
        return "publication_claim_audit.md"
    profile = str(profile_id or "").strip()
    if profile in {
        "android_malware_major_families",
        "android_malware_type_taxonomy",
    }:
        return "benchmark_claim_audit.md"
    return "research_claim_audit.md"


def claim_surface_label(*, profile_id: str, evidence_mode: bool, paper_mode: bool) -> str:
    """Return a human-readable claim surface label for index artifacts."""
    profile = str(profile_id or "").strip()
    if bool(evidence_mode or paper_mode):
        return "Locked publication cohort"
    if profile == "android_catalog_all_exploratory":
        return "Android catalog exploratory surface"
    if profile == "android_malware_all_current":
        return "Current-corpus diagnostic surface"
    if profile == "android_malware_major_families":
        return "Support-gated benchmark cohort"
    if profile == "android_malware_expanded_families":
        return "Expanded-family exploratory cohort"
    if profile == "android_malware_type_taxonomy":
        return "Type taxonomy benchmark"
    return "Benchmark research surface"
