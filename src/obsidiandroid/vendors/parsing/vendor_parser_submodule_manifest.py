# Filename: src/obsidiandroid/vendors/parsing/vendor_parser_submodule_manifest.py
"""Physical vendor-parser submodule names under :mod:`obsidiandroid.vendors.parsing`.

Shared by the canonical package ``__init__``, legacy ``analysis.vendor_processing``
registration, and import-surface parity checks so new parsers cannot land under
``src/`` without updating the legacy shim contract.
"""

from __future__ import annotations

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

__all__ = ("VENDOR_PARSER_SUBMODULE_NAMES",)
