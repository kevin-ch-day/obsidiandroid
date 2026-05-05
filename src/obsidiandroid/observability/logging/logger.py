"""Centralized structured logging utilities."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from config import app_config
from obsidiandroid.common.output_paths import project_logs_root, project_runtime_logs_dir

_LOGGERS: dict[str, logging.Logger] = {}


def _log_level() -> int:
    raw = str(getattr(app_config, "LOG_LEVEL", "INFO")).upper().strip()
    return getattr(logging, raw, logging.INFO)


def _log_dir() -> Path:
    """Rolling / fallback category logs at ``<project_logs_root>/<category>.log``."""
    path = project_logs_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _runtime_log_dir(run_id: str) -> Path:
    """Per-run category logs under ``<project_logs_root>/runtime/<run_id>/``."""
    path = project_runtime_logs_dir(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log_policy() -> str:
    policy = str(getattr(app_config, "LOG_RETENTION_POLICY", "per_run_only")).strip().lower()
    allowed = {"per_run_only", "rolling_only", "hybrid"}
    if policy not in allowed:
        return "per_run_only"
    return policy


def _current_run_id() -> str:
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "")).strip()
    if not run_id or run_id == "unknown":
        return ""

    runtime_diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if not runtime_diag:
        return ""

    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))).resolve()
    runtime_path = Path(runtime_diag).resolve()
    try:
        runtime_path.relative_to(output_root)
    except ValueError:
        # Ignore stale runtime state leaked across contexts/tests.
        return ""
    return run_id


def _resolve_log_paths(category: str) -> list[Path]:
    policy = _log_policy()
    run_id = _current_run_id()
    rolling_path = _log_dir() / f"{category}.log"
    run_path = (_runtime_log_dir(run_id) / f"{category}.log") if run_id else None
    if policy == "rolling_only":
        return [rolling_path]
    if policy == "hybrid":
        return [rolling_path] + ([run_path] if run_path else [])
    # per_run_only
    if run_path:
        return [run_path]
    return [rolling_path]


def _sync_logger_handlers(logger: logging.Logger, category: str) -> None:
    target_paths = {path.resolve() for path in _resolve_log_paths(category)}
    existing_handlers: list[logging.FileHandler] = [
        handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)
    ]
    existing_paths = {Path(handler.baseFilename).resolve() for handler in existing_handlers}

    for handler in list(existing_handlers):
        base_path = Path(handler.baseFilename).resolve()
        if base_path in target_paths:
            continue
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    for path in sorted(target_paths):
        if path in existing_paths:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(fmt)
        logger.addHandler(handler)


def get_logger(name: str, category: str) -> logging.Logger:
    """Get or create a category-based file logger.

    Args:
        name: Logger namespace (e.g. ``"framework.db"``).
        category: Log file category (e.g. ``"database"`` / ``"ml"``).

    Returns:
        Configured ``logging.Logger`` instance.
    """
    key = f"{name}:{category}"
    if key in _LOGGERS:
        return _LOGGERS[key]

    logger = logging.getLogger(key)
    logger.setLevel(_log_level())
    logger.propagate = False
    setattr(logger, "_obsidiandroid_category", str(category))
    _sync_logger_handlers(logger, category)

    _LOGGERS[key] = logger
    return logger


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a structured info event as key-value text."""
    category = str(getattr(logger, "_obsidiandroid_category", "")).strip()
    if category:
        _sync_logger_handlers(logger, category)
    payload = " ".join(f"{k}={fields[k]!r}" for k in sorted(fields))
    logger.info("%s %s", event, payload)


def close_all_loggers() -> None:
    """Close and detach file handlers for all managed loggers."""
    for logger in list(_LOGGERS.values()):
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
    _LOGGERS.clear()
