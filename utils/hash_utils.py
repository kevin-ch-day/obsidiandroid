"""Deterministic hashing helpers for ObsidianDroid governance artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(text: str) -> str:
    """Return SHA-256 hex digest for text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize payload deterministically for hashing."""
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def hash_payload(payload: Any) -> str:
    """Hash structured payload deterministically."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def short_hash(full_hash: str, size: int = 12) -> str:
    """Return display-safe shortened hash."""
    return str(full_hash)[: int(size)]
