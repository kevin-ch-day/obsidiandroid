"""Labeling package facade.

This package intentionally keeps its import-time side effects minimal.

- Pass 86 moved ``classification_label_resolver`` physically under this package.
- Pass 58 added ``obsidiandroid.labeling.taxonomy`` as a wrapper module.
- Pass 95 moved labeling helpers (validator, builder wrapper, postprocessor,
  field normalizer, format generator) physically under this package.

Why lazy? Vendor parsing now imports taxonomy helpers; importing the full legacy
labeling stack at package import time can create circular imports. So we use a
PEP 562 ``__getattr__`` facade and only import legacy modules on demand.
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_BY_CANONICAL: dict[str, str] = {
    "classification_label_resolver": "obsidiandroid.labeling.classification_label_resolver",
    "label_builder_wrapper": "obsidiandroid.labeling.label_builder_wrapper",
    "label_field_normalizer": "obsidiandroid.labeling.label_field_normalizer",
    "label_format_generator": "obsidiandroid.labeling.label_format_generator",
    "label_input_validator": "obsidiandroid.labeling.label_input_validator",
    "label_postprocessor": "obsidiandroid.labeling.label_postprocessor",
}


def __getattr__(name: str):
    if name not in _LEGACY_BY_CANONICAL:
        raise AttributeError(name)
    mod = importlib.import_module(_LEGACY_BY_CANONICAL[name])
    globals()[name] = mod
    sys.modules.setdefault(f"obsidiandroid.labeling.{name}", mod)
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LEGACY_BY_CANONICAL.keys()))


__all__ = sorted(_LEGACY_BY_CANONICAL.keys())
