"""Governed ATT&CK-Mobile permission-to-capability hypothesis mapping."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from obsidiandroid.common.repo_paths import repo_root

MAPPING_ARTIFACT_PATH = Path("config") / "taxonomy" / "mobile_attack_permission_mapping.yaml"
MAPPING_HANDLE = "mobile_attack_permission_mapping.rules"


def _stable_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _artifact_path() -> Path:
    return repo_root() / MAPPING_ARTIFACT_PATH


def _normalized_permission_list(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values if isinstance(values, list) else []:
        token = str(value or "").strip().lower()
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


@lru_cache(maxsize=1)
def load_mobile_attack_permission_mapping() -> dict[str, Any]:
    """Load the governed ATT&CK-Mobile permission mapping artifact."""
    payload = yaml.safe_load(_artifact_path().read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("mobile_attack_permission_mapping artifact must be a mapping")
    rules = payload.get("rules", [])
    if not isinstance(rules, list):
        rules = []
    normalized_rules: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        normalized_rules.append(
            {
                "attack_id": str(rule.get("attack_id", "") or "").strip(),
                "attack_name": str(rule.get("attack_name", "") or "").strip(),
                "attack_url": str(rule.get("attack_url", "") or "").strip(),
                "tactic": str(rule.get("tactic", "") or "").strip().lower(),
                "confidence": str(rule.get("confidence", "") or "").strip().lower(),
                "min_prevalence": float(rule.get("min_prevalence", 0.0) or 0.0),
                "required_any": _normalized_permission_list(rule.get("required_any", [])),
                "required_count": int(rule.get("required_count", 1) or 1),
            }
        )
    payload["rules"] = normalized_rules
    return payload


def mobile_attack_permission_mapping_payload() -> dict[str, Any]:
    """Return machine-readable metadata for the ATT&CK-Mobile permission mapping."""
    artifact = load_mobile_attack_permission_mapping()
    payload = {
        "mapping_id": str(artifact.get("mapping_id", "") or "").strip(),
        "version": str(artifact.get("version", "") or "").strip(),
        "source": str(artifact.get("source", "") or "").strip(),
        "review_status": str(artifact.get("review_status", "") or "").strip(),
        "review_notes": list(artifact.get("review_notes", []) or []),
        "artifact_path": str(MAPPING_ARTIFACT_PATH.as_posix()),
        "handle": MAPPING_HANDLE,
        "rule_count": int(len(artifact.get("rules", []) or [])),
        "rules": list(artifact.get("rules", []) or []),
    }
    payload["hash"] = _stable_hash(payload)
    return payload


__all__ = [
    "MAPPING_ARTIFACT_PATH",
    "MAPPING_HANDLE",
    "load_mobile_attack_permission_mapping",
    "mobile_attack_permission_mapping_payload",
]
