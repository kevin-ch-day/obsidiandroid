"""Stable malware-family taxonomy helpers (Pass 58).

Pass 46 tagged ``ml_classification.common.malware_family_constants`` normalization
functions as ``needs_wrapper`` because outer callers should not depend on mutable
tables and package layout under ``ml_classification``.

**Surface:** ``needs_wrapper`` → implemented here as an explicit delegation wrapper,
not as a ``sys.modules`` alias to the legacy module.

**Frozen public API** (backward-compatible with legacy behavior):

* :func:`normalize_family_name`
* :func:`is_known_family_name`
* :func:`canonicalize_family_label`

**Intentionally not exported:** ``KNOWN_FAMILIES``, ``FAMILY_ALIASES``, ``GENERIC_TOKENS``,
and ``CANONICAL_FAMILY_DISPLAY`` remain legacy implementation details.
Alias dictionaries that overlap vendor parsing belong under a future
``obsidiandroid.vendors`` contract (Pass 46 ``defer`` rows), not this labeling surface.

Outside ``ml_classification/``, prefer this module over importing
``ml_classification.common.malware_family_constants`` directly.
"""

from __future__ import annotations

from typing import Any

from ml_classification.common import malware_family_constants as _legacy


def normalize_family_name(name: Any) -> str:
    """Normalize a vendor or metadata family string to a canonical lowercase token."""
    return _legacy.normalize_family_name(name)


def is_known_family_name(name: str) -> bool:
    """Return True if ``name`` maps to a cohort-known malware family token."""
    return _legacy.is_known_family_name(name)


def canonicalize_family_label(name: str) -> str:
    """Return a display-oriented canonical label for reporting and training merges."""
    return _legacy.canonicalize_family_label(name)


__all__ = [
    "canonicalize_family_label",
    "is_known_family_name",
    "normalize_family_name",
]
