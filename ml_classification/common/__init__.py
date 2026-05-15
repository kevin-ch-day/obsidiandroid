"""Legacy ``ml_classification.common`` package shim.

Canonical malware-family tables and helpers live at
``obsidiandroid.labeling.malware_family_constants``; public taxonomy functions use
``obsidiandroid.labeling.taxonomy``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_SUBMODULES = {
    "malware_family_constants": "obsidiandroid.labeling.malware_family_constants",
}

for _name, _canonical in _SUBMODULES.items():
    _mod = import_legacy_shim(_canonical, f"{__name__}.{_name}", warn=True)
    globals()[_name] = _mod
    sys.modules[f"{__name__}.{_name}"] = _mod


def __dir__() -> list[str]:
    return sorted(_SUBMODULES)


__all__ = tuple(sorted(_SUBMODULES))
