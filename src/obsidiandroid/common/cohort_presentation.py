"""Operator-facing presentation helpers for cohort methodology semantics."""

from __future__ import annotations

from typing import Any

from obsidiandroid.common.cohort_methodology import safe_int


def cohort_methodology_summary(payload: dict[str, Any]) -> str:
    """Compact one-line methodology summary for tables and status views."""
    membership_mode = str(payload.get("cohort_membership_mode", "") or "").strip()
    lock_status = str(payload.get("cohort_lock_status", "") or "").strip()
    rescued = safe_int(payload.get("min_malicious_detections_rescued_unknown_consensus", 0), 0)
    threshold = safe_int(payload.get("min_malicious_detections_threshold", 0), 0)
    parts: list[str] = []
    if lock_status:
        parts.append(f"lock={lock_status}")
    if membership_mode == "paper_locked_snapshot_membership":
        parts.append("membership=locked_sample_ids")
    elif membership_mode:
        parts.append(f"membership={membership_mode}")
    if threshold > 0:
        parts.append(f"min_mal={threshold}")
    if rescued > 0:
        parts.append(f"rescued_unknown={rescued}")
    return "; ".join(parts) if parts else "standard_contract_filters"


def cohort_methodology_notes(payload: dict[str, Any]) -> list[str]:
    """Short operator notes for methodology-specific caveats."""
    notes: list[str] = []
    membership_mode = str(payload.get("cohort_membership_mode", "") or "").strip()
    if membership_mode == "paper_locked_snapshot_membership":
        notes.append(
            "Cohort membership authority: locked sample-id snapshot owned membership before normal contract-shrinking gates."
        )
    rescued = safe_int(payload.get("min_malicious_detections_rescued_unknown_consensus", 0), 0)
    if rescued > 0:
        notes.append(
            "Malware rescue: "
            f"{rescued} rows were retained despite missing VT consensus because other malware evidence remained authoritative."
        )
    return notes


def cohort_filter_highlight_lines(payload: dict[str, Any]) -> list[str]:
    """Markdown-friendly highlight lines for run-science style artifact summaries."""
    lines: list[str] = []
    membership_mode = str(payload.get("cohort_membership_mode", "") or "").strip()
    membership_note = str(payload.get("cohort_membership_authority_note", "") or "").strip()
    rescued = safe_int(payload.get("min_malicious_detections_rescued_unknown_consensus", 0), 0)
    threshold = payload.get("min_malicious_detections_threshold")
    if membership_mode:
        lines.append(f"- **membership_mode:** `{membership_mode}`")
    if membership_note:
        lines.append(f"- **locked_membership_note:** {membership_note}")
    if threshold not in (None, "") or rescued > 0:
        threshold_display = threshold if threshold not in (None, "") else "unknown"
        lines.append(
            f"- **min_malicious_detections:** threshold=`{threshold_display}`; "
            f"rescued_unknown_consensus=`{rescued}`"
        )
    if not lines:
        lines.append("- cohort filter contract artifacts unavailable")
    return lines
