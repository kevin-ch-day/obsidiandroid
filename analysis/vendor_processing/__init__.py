"""Legacy compatibility shim for vendor parser modules.

Pass 59 physically moved parser implementations to
``obsidiandroid.vendors.parsing``. This package keeps legacy import paths alive
and identity-preserving by registering module aliases in ``sys.modules``.

Registration data lives in :mod:`obsidiandroid.legacy.analysis_vendor_processing_registry`.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy.analysis_vendor_processing_registry import (
    VENDOR_PARSER_SUBMODULE_NAMES,
    register_analysis_vendor_processing_legacy_aliases,
)

register_analysis_vendor_processing_legacy_aliases(sys.modules[__name__])

__all__ = list(VENDOR_PARSER_SUBMODULE_NAMES)
