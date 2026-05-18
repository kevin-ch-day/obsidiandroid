"""Canonical helpers for repo-root ``main`` monkeypatch overrides.

The repo-root ``main.py`` shell remains a stable operator/test entrypoint. Some tests
patch attributes on the loaded ``main`` module, so canonical pipeline code needs a
small call-time bridge to honor those overrides without importing legacy shim paths.
"""

from __future__ import annotations

import sys
from typing import TypeVar

__all__ = ["resolve_main_override"]

_T = TypeVar("_T")


def resolve_main_override(attr: str, default: _T) -> _T:
    """Return ``main.<attr>`` when the CLI shell is loaded, else ``default``.

    Args:
        attr: Attribute name on the repo-root ``main`` module.
        default: Fallback object used during normal production imports.

    Returns:
        The object exposed by ``main`` when present, otherwise ``default``.
    """
    main_mod = sys.modules.get("main")
    if main_mod is None:
        return default
    return getattr(main_mod, attr, default)
