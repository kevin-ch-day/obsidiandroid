"""Resolve symbols from ``main`` when present so monkeypatched tests affect ``runner.run_pipeline``.

Canonical module (**Pass 68**): ``obsidiandroid.pipeline.main_facade``; legacy
``analysis.pipeline.main_facade`` is an identity shim.

``obsidiandroid.pipeline.runner`` imports concrete stage functions, but the stable CLI/test
surface is the repo-root ``main`` shim. Call sites use :func:`from_main_or` so
``monkeypatch.setattr(main, ...)`` works without re-importing the runner module.

Attributes consulted today (keep in sync with ``runner.run_pipeline``):

    * ``finalize_run_manifest_stage``
    * ``profile_manager`` (``load_profile``)
    * ``runtime_logging`` (``start_runtime_logging`` / ``stop_runtime_logging``)
    * ``load_and_prepare_samples``
    * ``run_av_analysis_stage``

For other stages, tests typically patch ``analysis.pipeline.runner`` directly.
"""

from __future__ import annotations

import sys
from typing import TypeVar

__all__ = ["from_main_or"]

_T = TypeVar("_T")


def from_main_or(attr: str, default: _T) -> _T:
    """Return ``main.<attr>`` when the CLI module is loaded, else ``default``.

    Resolution happens at **call time** via ``sys.modules["main"]``, so patches apply
    even though ``run_pipeline`` is defined outside ``main.py``.

    Args:
        attr: Attribute name on the ``main`` module.
        default: Implementation used when ``main`` is not loaded or the attribute
            is missing (normal production path).

    Returns:
        The callable or object bound on ``main``, or ``default``.
    """
    main_mod = sys.modules.get("main")
    if main_mod is None:
        return default
    return getattr(main_mod, attr, default)
