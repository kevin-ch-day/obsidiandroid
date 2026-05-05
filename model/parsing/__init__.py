"""Legacy shim for ``model.parsing``.

Pass 60 physically moved parsed-label metadata to
``obsidiandroid.vendors.contracts.parsed_label_metadata``.

This package preserves legacy import compatibility and ModuleType identity.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.vendors.contracts.parsed_label_metadata")
ParsedLabelMetadata = _mod.ParsedLabelMetadata
sys.modules.setdefault("model.parsing.parsed_label_metadata", _mod)

__all__ = ["ParsedLabelMetadata"]

del _mod
