"""Pipeline manifest canonical aliases.

Implementation remains under ``analysis.pipeline.manifest`` for now. This package
surfaces stable manifest helper modules without physically moving them.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = (
    "hashing",
    "paper_compliance_checks",
    "paper_figure_renderers",
    "runtime_support",
    "writer",
)

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"analysis.pipeline.manifest.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.pipeline.manifest.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _name, _canon
