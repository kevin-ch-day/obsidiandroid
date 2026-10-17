"""Read-only adapter for PI immutable static declaration projections v1."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd


def _normalize(value: object) -> object:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, float):
        raise ValueError("static projection semantic JSON contains a float")
    return value


def _semantic_digest(value: object) -> str:
    payload = json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_static_projection_evidence(
    samples: pd.DataFrame,
    projection_paths: Sequence[Path],
    *,
    baseline_paths_by_sha: Mapping[str, Path],
    expected_projection_digests_by_sha: Mapping[str, str],
) -> pd.DataFrame:
    """Bind exact SHA and verified APK baseline to manifestation occurrences."""
    if not {"sample_id", "sha256"} <= set(samples):
        raise ValueError("catalog sample/SHA columns are required")
    if samples["sha256"].duplicated().any() or samples["sample_id"].duplicated().any():
        raise ValueError("catalog sample identity is duplicated")
    sample_by_sha = dict(zip(samples["sha256"], samples["sample_id"], strict=True))
    rows: list[dict[str, object]] = []
    seen_projection_sha: set[str] = set()
    for path in projection_paths:
        projection = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(projection, dict) or projection.get("contract") != "pi.static-declaration-projection.v1":
            raise ValueError("static projection contract differs")
        body = {key: value for key, value in projection.items() if key != "projection_digest"}
        if _semantic_digest(body) != projection.get("projection_digest"):
            raise ValueError("static projection digest differs")
        sha = projection.get("sha256")
        if sha not in sample_by_sha or sha in seen_projection_sha:
            raise ValueError("static projection sample identity is absent or duplicated")
        if projection.get("projection_digest") != expected_projection_digests_by_sha.get(sha):
            raise ValueError("static projection reviewed digest differs")
        seen_projection_sha.add(sha)
        baseline_path = baseline_paths_by_sha.get(sha)
        if baseline_path is None or hashlib.sha256(baseline_path.read_bytes()).hexdigest() != projection.get("baseline_sha256"):
            raise ValueError("static baseline file digest differs")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        static = baseline.get("static", {})
        if (baseline.get("sha256") != sha or static.get("status") != "VALID_APK"
                or static.get("extracted_sha256") != sha or baseline.get("runtime_evidence_used") is not False):
            raise ValueError("static baseline APK identity is invalid")
        projected_rows = projection.get("rows")
        declared = static.get("permissions")
        if (not isinstance(projected_rows, list) or not isinstance(declared, list)
                or projection.get("occurrence_complete") is not True
                or projection.get("declared_count") != len(declared)
                or len(projected_rows) != len(declared)):
            raise ValueError("static occurrence set is incomplete")
        if not declared:
            # A verified empty manifest is observed absence, not missing parse
            # evidence. Keep it separate from positive permission occurrences.
            rows.append({
                "sample_id": sample_by_sha[sha], "sha256": sha,
                "raw_token": "", "projected_token": "",
                "observation_origin": "manifest", "source_verified": True,
                "source_receipt_digest": projection["projection_digest"],
                "event_verified": False, "identity_status": "VERIFIED_EMPTY",
                "canonical_token": "", "alias_release_digest": "",
            })
        for index, (item, token) in enumerate(zip(projected_rows, declared, strict=True)):
            occurrence = item.get("occurrence") if isinstance(item, dict) else None
            if not isinstance(occurrence, dict):
                raise ValueError("static occurrence is missing")
            occurrence_body = {key: value for key, value in occurrence.items()
                               if key != "occurrence_evidence_digest"}
            digest = occurrence.get("occurrence_evidence_digest")
            identity = occurrence.get("identity", {})
            provenance = occurrence.get("provenance", {})
            subject = occurrence.get("subject", {})
            if (
                _semantic_digest(occurrence_body) != digest
                or occurrence.get("occurrence_role") != "MANIFEST_USES_PERMISSION"
                or occurrence.get("evidence_layer") != "DIRECT_MANIFEST"
                or occurrence.get("semantic_claim") != "PERMISSION_REQUEST"
                or subject.get("artifact_sha256") != sha
                or provenance.get("source_artifact_sha256") != projection["baseline_sha256"]
                or provenance.get("evidence_locator") != f"/static/permissions/{index}"
                or identity.get("raw_token") != token
                or identity.get("projected_pi_token") != token
                or item.get("raw_token") != token
            ):
                raise ValueError("static occurrence provenance differs")
            accepted = item.get("state") in {
                "PROJECTED_KNOWN", "PROJECTED_APP_DEFINED", "PROJECTED_VENDOR_OR_ECOSYSTEM"
            }
            rows.append({
                "sample_id": sample_by_sha[sha], "sha256": sha,
                "raw_token": token, "projected_token": token,
                "observation_origin": "manifest", "source_verified": True,
                "source_receipt_digest": digest, "event_verified": False,
                "identity_status": "ACCEPTED_EXACT" if accepted else "CONFLICT",
                "canonical_token": token if accepted else "",
                "alias_release_digest": "",
            })
    return pd.DataFrame(rows, columns=[
        "sample_id", "sha256", "raw_token", "projected_token",
        "observation_origin", "source_verified", "source_receipt_digest",
        "event_verified", "identity_status", "canonical_token",
        "alias_release_digest",
    ])
