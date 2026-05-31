"""Shared readiness-note formatting helpers for operator surfaces."""

from __future__ import annotations


def build_observed_readiness_note(readiness: dict[str, object] | None, bucket: str | None) -> str | None:
    """Return the compact observed-readiness note for a mapped bucket."""
    token = str(bucket or "").strip()
    if not token:
        return None
    snapshot = readiness if isinstance(readiness, dict) else {}
    buckets = snapshot.get("buckets", {}) if isinstance(snapshot, dict) else {}
    payload = buckets.get(token, {}) if isinstance(buckets, dict) else {}
    sample_count = payload.get("sample_count") if isinstance(payload, dict) else None
    family_count = payload.get("family_count") if isinstance(payload, dict) else None
    if sample_count is None:
        return f"Observed readiness for `{token}` is unavailable in the live DB snapshot."
    note = f"Observed readiness for `{token}`: samples={sample_count}"
    if family_count is not None:
        note += f", families={family_count}"
    if "permission_obs" in token and int(sample_count or 0) <= 0:
        note += ". Live DB currently shows no matching PI-observation-ready cohort for this bucket."
    return note


def build_permission_obs_gap_note(readiness: dict[str, object] | None, bucket: str | None) -> str | None:
    """Return a normalized PI-observation mismatch note for a mapped bucket."""
    token = str(bucket or "").strip()
    if "permission_obs" not in token:
        return None
    snapshot = readiness if isinstance(readiness, dict) else {}
    buckets = snapshot.get("buckets", {}) if isinstance(snapshot, dict) else {}
    payload = buckets.get(token, {}) if isinstance(buckets, dict) else {}
    sample_count = payload.get("sample_count") if isinstance(payload, dict) else None
    permission_obs_available = bool(snapshot.get("permission_obs_available", False))
    if sample_count in (None, 0) or not permission_obs_available:
        return (
            "Live readiness mismatch: this bucket names `permission_obs`, but the current DB snapshot "
            "does not verify a matching PI-observed cohort."
        )
    return None


__all__ = ["build_observed_readiness_note", "build_permission_obs_gap_note"]
