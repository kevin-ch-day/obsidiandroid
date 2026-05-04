"""Pipeline orchestration namespace (facade over ``analysis.pipeline``).

Re-exports stable, public symbols from :mod:`analysis.pipeline.runner` without
relocating implementation files. Attributes resolve via :func:`__getattr__` so
they stay aligned when tests monkeypatch :mod:`analysis.pipeline.runner`
(e.g. ``DIAGNOSTICS_DIR``).

Prefer ``from obsidiandroid.pipeline import ...`` in new code.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DIAGNOSTICS_DIR",
    "PIPELINE_MAIN_LOGGER",
    "PARSER_QUALITY_PATH",
    "run_pipeline",
]


def __getattr__(name: str) -> Any:
    """Forward public names to the live :mod:`analysis.pipeline.runner` bindings."""
    if name in __all__:
        import analysis.pipeline.runner as runner_mod

        return getattr(runner_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
