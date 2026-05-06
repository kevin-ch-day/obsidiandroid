"""Compatibility shim; canonical implementation in :mod:`obsidiandroid.observability.logging`."""

from __future__ import annotations


from obsidiandroid.observability.logging import get_logger, log_event

__all__ = ["get_logger", "log_event"]
