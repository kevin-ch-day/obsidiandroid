"""Compatibility shim; canonical implementation in :mod:`obsidiandroid.observability.logging`."""

from __future__ import annotations

import utils.repo_import_paths  # noqa: F401

from obsidiandroid.observability.logging import get_logger, log_event

__all__ = ["get_logger", "log_event"]
