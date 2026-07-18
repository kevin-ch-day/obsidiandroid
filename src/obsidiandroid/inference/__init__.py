"""Canonical inference namespace for heuristic consensus and signal-quality helpers.

Heuristic label consensus and signal-quality helpers live under
``obsidiandroid.inference``.
"""

from __future__ import annotations

import importlib

_LAZY_CANONICAL_SUBMODULES: dict[str, str] = {
    "label_consensus_engine": "obsidiandroid.inference.label_consensus_engine",
    "malware_type_engine": "obsidiandroid.inference.malware_type_engine",
    "signal_health_checker": "obsidiandroid.inference.signal_health_checker",
    "threat_class_engine": "obsidiandroid.inference.threat_class_engine",
}


def __getattr__(name: str):
    if name not in _LAZY_CANONICAL_SUBMODULES:
        raise AttributeError(name)
    mod = importlib.import_module(_LAZY_CANONICAL_SUBMODULES[name])
    globals()[name] = mod
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LAZY_CANONICAL_SUBMODULES.keys()))


__all__ = sorted(_LAZY_CANONICAL_SUBMODULES.keys())
