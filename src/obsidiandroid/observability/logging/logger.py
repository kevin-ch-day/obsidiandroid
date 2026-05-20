"""Centralized structured logging utilities."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from config import app_config
from obsidiandroid.common.output_paths import project_logs_root, project_runtime_logs_dir

_LOGGERS: dict[str, logging.Logger] = {}
_CATEGORY_FILENAMES: dict[str, str] = {
    "analysis": "analysis_summary.log",
    "database": "database_access.log",
    "export": "artifact_exports.log",
    "label_authority": "label_authority_alerts.log",
    "menu": "profile_preflight.log",
    "ml": "machine_learning.log",
    "pipeline": "pipeline_orchestration.log",
    "temporal_readiness": "temporal_readiness_alerts.log",
}
_ERROR_AGGREGATE_FILENAME = "error.log"


def _log_level() -> int:
    raw = str(getattr(app_config, "LOG_LEVEL", "INFO")).upper().strip()
    return getattr(logging, raw, logging.INFO)


def _log_dir() -> Path:
    """Rolling / fallback category logs at ``<project_logs_root>/<canonical-name>.log``."""
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
    rolling_path = _log_dir() / _log_filename_for_category(category)
    run_path = (_runtime_log_dir(run_id) / _log_filename_for_category(category)) if run_id else None
    if policy == "rolling_only":
        return [rolling_path]
    if policy == "hybrid":
        return [rolling_path] + ([run_path] if run_path else [])
    # per_run_only
    if run_path:
        return [run_path]
    return [rolling_path]


def _log_filename_for_category(category: str) -> str:
    """Return the canonical on-disk filename for one logger category."""
    token = str(category).strip().lower()
    return _CATEGORY_FILENAMES.get(token, f"{token}.log")


def _normalize_log_level(level: object) -> int:
    """Return a stdlib logging level from string/int input."""
    if isinstance(level, int):
        return int(level)
    token = str(level or "INFO").strip().upper()
    return getattr(logging, token, logging.INFO)


def _runtime_context_fields(logger: logging.Logger) -> dict[str, Any]:
    """Return useful runtime context fields for every structured event."""
    context: dict[str, Any] = {
        "category": str(getattr(logger, "_obsidiandroid_category", "")).strip(),
        "logger_name": str(getattr(logger, "name", "")).strip(),
    }
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
    if run_id and run_id != "unknown":
        context["run_id"] = run_id
    profile_id = str(getattr(app_config, "RUNTIME_PROFILE_ID", "") or "").strip()
    if profile_id and profile_id != "unknown":
        context["profile_id"] = profile_id
    if bool(getattr(app_config, "RUNTIME_EVIDENCE_MODE", False)):
        context["evidence_mode"] = True
    if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
        context["paper_mode"] = True
    return context


def _merge_event_fields(logger: logging.Logger, explicit_fields: dict[str, Any]) -> dict[str, Any]:
    """Merge auto context fields without overriding explicit event payload keys."""
    fields = dict(explicit_fields)
    for key, value in _runtime_context_fields(logger).items():
        if key not in fields and value not in ("", None):
            fields[key] = value
    return fields


def _sync_logger_handlers(logger: logging.Logger, category: str) -> None:
    target_paths = {path.resolve() for path in _resolve_log_paths(category)}
    target_paths.add((_log_dir() / _ERROR_AGGREGATE_FILENAME).resolve())
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
        # Delay open so categories that never emit do not leave empty placeholder files behind.
        handler = logging.FileHandler(path, encoding="utf-8", delay=True)
        if path.name == _ERROR_AGGREGATE_FILENAME:
            handler.setLevel(logging.ERROR)
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


def log_event(logger: logging.Logger, event: str, *, level: object = "INFO", **fields: Any) -> None:
    """Emit a structured event as key-value text.

    Args:
        logger: Destination logger returned by :func:`get_logger`.
        event: Stable event name.
        level: Logging level name or integer.
        **fields: Structured payload fields.
    """
    category = str(getattr(logger, "_obsidiandroid_category", "")).strip()
    if category:
        _sync_logger_handlers(logger, category)
    merged = _merge_event_fields(logger, fields)
    payload = " ".join(f"{k}={merged[k]!r}" for k in sorted(merged))
    message = f"event={event!r}" if not payload else f"event={event!r} {payload}"
    logger.log(_normalize_log_level(level), message)


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
