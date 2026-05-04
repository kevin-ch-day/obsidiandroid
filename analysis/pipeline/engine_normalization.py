"""Engine name normalization and alias resolution."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

import yaml

from utils.hash_utils import sha256_hex

_REPO_ROOT = Path(__file__).resolve().parents[2]
ALIASES_FILE = _REPO_ROOT / "config" / "engine_aliases.yaml"


def load_engine_aliases() -> Dict[str, str]:
    """Load engine alias mapping from YAML."""
    if not ALIASES_FILE.exists():
        return {}
    data = yaml.safe_load(ALIASES_FILE.read_text(encoding="utf-8")) or {}
    raw = data.get("aliases", {}) if isinstance(data, dict) else {}
    aliases = {}
    for k, v in raw.items():
        nk = _base_normalize(str(k))
        nv = _base_normalize(str(v))
        if nk and nv:
            aliases[nk] = nv
    return aliases


def canonicalize_engine_name(name: str, aliases: Dict[str, str] | None = None) -> str:
    """Canonicalize engine name using governance rules."""
    norm = _base_normalize(name)
    if not norm:
        return ""
    # Apply numeric suffix stripping only to raw normalized names. Alias targets
    # may intentionally include numeric tokens (e.g., qihoo_360 DB key).
    normalized = _strip_trailing_numeric(norm)
    mapped = (aliases or {}).get(norm, normalized)
    return mapped.strip("_")


def compute_engine_hash(canonical_slug: str) -> str:
    """Stable engine hash derived from canonical slug."""
    return sha256_hex(canonical_slug)[:12]


def _base_normalize(name: str) -> str:
    text = str(name or "").strip().lower()
    text = re.sub(r"[-\s_]+", "_", text)
    text = re.sub(r"[^a-z0-9_]", "", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def _strip_trailing_numeric(name: str) -> str:
    if "_" not in name:
        return name
    parts = name.split("_")
    # Preserve legitimate numeric engine keys (e.g., qihoo_360) while still
    # collapsing duplicate-like suffixes introduced by source naming (_2, _03).
    if parts and parts[-1].isdigit() and len(parts[-1]) <= 2:
        return "_".join(parts[:-1]) or name
    return name
