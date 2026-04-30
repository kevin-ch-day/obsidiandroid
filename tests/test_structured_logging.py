"""Tests for structured logging backend utilities."""

from __future__ import annotations

from pathlib import Path

from utils.logging import logger as logger_mod


def test_get_logger_writes_category_file(monkeypatch, tmp_path: Path) -> None:
    """Category logger should write to output/diagnostics/logs/<category>.log."""
    monkeypatch.setattr(logger_mod.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(logger_mod.app_config, "LOG_LEVEL", "INFO")
    logger_mod._LOGGERS.clear()

    log = logger_mod.get_logger("test.logger", "ml")
    logger_mod.log_event(log, "model_start", model="random_forest", run_id="r1")

    path = tmp_path / "diagnostics" / "logs" / "ml.log"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "model_start" in text
    assert "random_forest" in text
    assert "run_id='r1'" in text


def test_get_logger_reuses_cached_instance(monkeypatch, tmp_path: Path) -> None:
    """Repeated requests should return the same logger instance."""
    monkeypatch.setattr(logger_mod.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path))
    logger_mod._LOGGERS.clear()

    a = logger_mod.get_logger("test.same", "database")
    b = logger_mod.get_logger("test.same", "database")
    assert a is b

