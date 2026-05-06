"""Legacy ``ml_classification.common`` (shim-only).

Canonical malware-family tables and helpers live at
``obsidiandroid.labeling.malware_family_constants``; public taxonomy functions use
``obsidiandroid.labeling.taxonomy``.
"""

from __future__ import annotations

import importlib
from typing import Any


def __getattr__(name: str) -> Any:
    if name == "malware_family_constants":
        return importlib.import_module(f"{__name__}.malware_family_constants")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return ["malware_family_constants"]


__all__ = ("malware_family_constants",)
