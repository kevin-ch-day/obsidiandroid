# Filename: src/obsidiandroid/vendors/parsing/analysis_vendor_processing_shim.py
"""Register ``analysis.vendor_processing.*`` :class:`sys.modules` aliases (Pass 59).

Parser implementations live under :mod:`obsidiandroid.vendors.parsing`; this module
holds the submodule name list and registration used by :mod:`analysis.vendor_processing`.
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_PKG = "analysis.vendor_processing"
_CANON_PREFIX = "obsidiandroid.vendors.parsing"

VENDOR_PARSER_SUBMODULE_NAMES: tuple[str, ...] = (
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


def register_analysis_vendor_processing_legacy_aliases(package: object | None = None) -> None:
    for name in VENDOR_PARSER_SUBMODULE_NAMES:
        canon_name = f"{_CANON_PREFIX}.{name}"
        mod = importlib.import_module(canon_name)
        sys.modules.setdefault(f"{_LEGACY_PKG}.{name}", mod)
        if package is not None:
            setattr(package, name, mod)


__all__ = ("VENDOR_PARSER_SUBMODULE_NAMES", "register_analysis_vendor_processing_legacy_aliases")
