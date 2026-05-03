"""Resolve symbols from ``main`` when present so monkeypatched tests affect ``runner.run_pipeline``."""

from __future__ import annotations

import sys
from typing import TypeVar

_T = TypeVar("_T")


def from_main_or(attr: str, default: _T) -> _T:
    """Return ``main.<attr>`` after CLI import, otherwise ``default``.

    Tests patch attributes on ``main`` (e.g. ``finalize_run_manifest_stage``); ``runner``
    must resolve those bindings at call time because ``run_pipeline`` lives outside
    ``main.py``.
    """
    main_mod = sys.modules.get("main")
    if main_mod is None:
        return default
    return getattr(main_mod, attr, default)
