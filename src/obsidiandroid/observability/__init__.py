"""Observability: structured logging helpers under :mod:`obsidiandroid.observability.logging`.

Prefer:

    from obsidiandroid.observability import get_logger, log_event

Implementation lives in ``logging/logger.py`` and ``logging/runtime.py``.
"""

from __future__ import annotations

from obsidiandroid.observability.logging import get_logger, log_event

__all__ = ["get_logger", "log_event"]
