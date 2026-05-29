"""Shared helpers for cohort-lock and cohort-gate methodology semantics."""

from __future__ import annotations

from typing import Any

from obsidiandroid.common.authority_taxonomy_terms import taxonomy_count_drift_note


def safe_int(value: object, default: int = 0) -> int:
    """Best-effort integer coercion for small operator/reporting helpers."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def extract_rescued_unknown_consensus(details: object) -> int:
    """Parse ``rescued_unknown_consensus=<n>`` tokens from gate-detail text."""
    token = "rescued_unknown_consensus="
    text = str(details or "")
    if token not in text:
        return 0
    tail = text.split(token, 1)[1].strip()
    digits: list[str] = []
    for char in tail:
        if char.isdigit():
            digits.append(char)
            continue
        break
    return safe_int("".join(digits), 0) if digits else 0


def resolve_cohort_lock_status(manifest: dict[str, Any]) -> str:
    """Normalize cohort-lock status across manifest and contract payload variants."""
    from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode

    direct = str(manifest.get("cohort_lock_status", "") or "").strip().lower()
    if direct in {"membership_locked", "locked"}:
        return "locked"
    if direct in {"membership_locked_taxonomy_drift", "taxonomy-drift", "taxonomy_drift"}:
        return "taxonomy-drift"
    if direct in {"count_only_incomplete_sample_lock", "count_only", "count-only"}:
        return "count-only"
    if direct in {"not_paper_locked", "not_locked", "unlocked"}:
        return "unlocked"
    if direct in {"locked_mismatch", "missing_lock", "missing-lock"}:
        return "missing-lock"

    evidence_mode = coalesce_manifest_publication_mode(manifest)
    publication_raw = str(
        manifest.get("publication_ready_status", "") or manifest.get("paper_safe_status", "") or ""
    ).strip().lower()

    for key in ("cohort_contract", "paper_cohort_contract"):
        payload = manifest.get(key)
        if not isinstance(payload, dict):
            continue
        status = str(payload.get("cohort_lock_status", "") or payload.get("contract_status", "") or "").strip().lower()
        if status in {"membership_locked", "locked"}:
            return "locked"
        if status in {"membership_locked_taxonomy_drift", "taxonomy-drift", "taxonomy_drift"}:
            return "taxonomy-drift"
        if status in {"count_only_incomplete_sample_lock", "count_only", "count-only"}:
            return "count-only"
        if status in {"not_paper_locked", "not_locked", "unlocked"}:
            return "unlocked"
        if status in {"locked_mismatch", "missing_lock", "missing-lock", "unknown"}:
            return "missing-lock"
        if bool(payload.get("paper_locked", False)):
            return "locked"

    if evidence_mode or publication_raw in {"ready", "pass", "fail", "not_ready"}:
        return "missing-lock"
    return "unlocked"


def extract_taxonomy_label_drift(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return taxonomy-label drift metadata from manifest/contract payloads when present."""
    for key in ("paper_cohort_contract", "cohort_contract"):
        payload = manifest.get(key) if isinstance(manifest, dict) else {}
        if not isinstance(payload, dict):
            continue
        sample_id_lock = payload.get("sample_id_lock")
        if not isinstance(sample_id_lock, dict):
            continue
        drift = sample_id_lock.get("taxonomy_label_drift")
        if isinstance(drift, dict) and drift:
            return drift
    return {}


def taxonomy_label_drift_display(manifest: dict[str, Any]) -> str:
    """Render taxonomy-label drift metadata for compact operator screens."""
    drift = extract_taxonomy_label_drift(manifest)
    return taxonomy_count_drift_note(drift) if drift else ""
