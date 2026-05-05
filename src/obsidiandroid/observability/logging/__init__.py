"""Structured file logging and runtime stream tee logging (canonical).

Subpackages :mod:`logger` and :mod:`runtime` mirror the legacy ``utils.logging``
layout so imports like ``from ... import logger as logger_manager`` remain valid.
"""

from __future__ import annotations

from . import logger
from . import runtime
from .logger import get_logger, log_event

__all__ = ["get_logger", "log_event", "logger", "runtime"]
