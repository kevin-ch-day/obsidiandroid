"""Stable malware-family taxonomy helpers.

This explicit public surface keeps outer callers independent from the internal
normalization tables.

**Public API:**

* :func:`normalize_family_name`
* :func:`is_known_family_name`
* :func:`canonicalize_family_label`

**Intentionally not exported:** ``KNOWN_FAMILIES``, ``FAMILY_ALIASES``, ``GENERIC_TOKENS``,
and ``CANONICAL_FAMILY_DISPLAY`` are internal implementation details.
Alias dictionaries that overlap vendor parsing belong under a future
``obsidiandroid.vendors`` contract (Pass 46 ``defer`` rows), not this labeling surface.

Prefer this module over importing the underlying constants implementation
directly.
"""

from __future__ import annotations

from typing import Any

from obsidiandroid.labeling import malware_family_constants as _constants


def normalize_family_name(name: Any) -> str:
    """Normalize a vendor or metadata family string to a canonical lowercase token."""
    return _constants.normalize_family_name(name)


def is_known_family_name(name: str) -> bool:
    """Return True if ``name`` maps to a cohort-known malware family token."""
    return _constants.is_known_family_name(name)


def canonicalize_family_label(name: str) -> str:
    """Return a display-oriented canonical label for reporting and training merges."""
    return _constants.canonicalize_family_label(name)


__all__ = [
    "canonicalize_family_label",
    "is_known_family_name",
    "normalize_family_name",
]
