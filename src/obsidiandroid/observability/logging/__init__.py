"""Structured file logging and runtime stream tee logging (canonical).

Subpackages :mod:`logger` and :mod:`runtime` provide structured loggers and tee handling.
"""

from __future__ import annotations

from . import logger
from . import runtime
from .logger import get_logger, log_event

__all__ = ["get_logger", "log_event", "logger", "runtime"]
