"""Canonical vendor parser package.

Pass 59 physically moved parser implementations from ``analysis.vendor_processing``
into this package. Legacy import compatibility is maintained by
``analysis.vendor_processing`` shim registration.
"""

from __future__ import annotations

import importlib
import sys

_SUBMODULES = (
    "parser_defaults",
    "parser_confidence_estimator",
    "generic_label_parser",
    "vendor_parser_map",
    "avast_parser",
    "avast_mobile_parser",
    "bitdefender_parser",
    "bitdefenderfalx_parser",
    "ikarus_parser",
    "k7gw_parser",
    "kaspersky_parser",
    "lionic_parser",
    "microsoft_parser",
    "tencent_parser",
    "zonealarm_parser",
    "alibaba_parser",
    "ahnlab_v3_parser",
)

for _name in _SUBMODULES:
    _mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{_name}")
    globals()[_name] = _mod
    sys.modules.setdefault(f"obsidiandroid.vendors.parsing.{_name}", _mod)

__all__ = list(_SUBMODULES)

del _SUBMODULES, _name, _mod
