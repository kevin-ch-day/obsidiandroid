"""Governed paper-facing family display policy for confusion-matrix exports."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from obsidiandroid.common.repo_paths import repo_root

POLICY_ARTIFACT_PATH = Path("config") / "taxonomy" / "paper_family_display_policy.yaml"
PAPER_FAMILY_DISPLAY_POLICY_HANDLE = "android_paper_family_display_policy.family_confusion_matrix"


def _stable_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _artifact_path() -> Path:
    return repo_root() / POLICY_ARTIFACT_PATH


@lru_cache(maxsize=1)
def load_paper_family_display_policy_artifact() -> dict[str, Any]:
    """Load the governed paper-facing family display policy artifact."""
    path = _artifact_path()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Paper family display policy artifact must be a mapping: {path}")
    matrix_policy = payload.get("family_confusion_matrix") or {}
    if not isinstance(matrix_policy, dict):
        raise ValueError(f"family_confusion_matrix must be a mapping: {path}")
    payload["family_confusion_matrix"] = dict(matrix_policy)
    return payload


def paper_family_display_policy_payload() -> dict[str, Any]:
    """Return machine-readable paper-facing family display policy metadata."""
    artifact = load_paper_family_display_policy_artifact()
    matrix_policy = dict(artifact.get("family_confusion_matrix") or {})
    payload = {
        "policy_id": str(artifact.get("policy_id", "") or "").strip(),
        "version": str(artifact.get("version", "") or "").strip(),
        "source": str(artifact.get("source", "") or "").strip(),
        "review_status": str(artifact.get("review_status", "") or "").strip(),
        "review_notes": list(artifact.get("review_notes", []) or []),
        "artifact_path": str(POLICY_ARTIFACT_PATH.as_posix()),
        "handle": PAPER_FAMILY_DISPLAY_POLICY_HANDLE,
        "family_confusion_matrix": matrix_policy,
    }
    payload["hash"] = _stable_hash(payload)
    return payload


__all__ = [
    "PAPER_FAMILY_DISPLAY_POLICY_HANDLE",
    "POLICY_ARTIFACT_PATH",
    "load_paper_family_display_policy_artifact",
    "paper_family_display_policy_payload",
]
