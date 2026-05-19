"""Canonical inference namespace for heuristic consensus and signal-quality helpers.

Heuristic label consensus and signal-quality helpers live under
``obsidiandroid.inference``.
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_BY_CANONICAL: dict[str, str] = {
    "label_consensus_engine": "obsidiandroid.inference.label_consensus_engine",
    "malware_type_engine": "obsidiandroid.inference.malware_type_engine",
    "signal_health_checker": "obsidiandroid.inference.signal_health_checker",
    "threat_class_engine": "obsidiandroid.inference.threat_class_engine",
}


def __getattr__(name: str):
    if name not in _LEGACY_BY_CANONICAL:
        raise AttributeError(name)
    mod = importlib.import_module(_LEGACY_BY_CANONICAL[name])
    globals()[name] = mod
    sys.modules.setdefault(f"obsidiandroid.inference.{name}", mod)
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LEGACY_BY_CANONICAL.keys()))


__all__ = sorted(_LEGACY_BY_CANONICAL.keys())
