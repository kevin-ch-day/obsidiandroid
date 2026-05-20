"""Tests for structured logging backend utilities."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.observability.logging import logger as logger_mod


def test_get_logger_writes_category_file(monkeypatch, tmp_path: Path) -> None:
    """Category logger should write to project logs root (repo ``logs/`` by default)."""
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(tmp_path))
    monkeypatch.setattr(logger_mod.app_config, "LOG_LEVEL", "INFO")
    logger_mod._LOGGERS.clear()
    monkeypatch.setattr(logger_mod.app_config, "RUNTIME_RUN_ID", "r1", raising=False)
    monkeypatch.setattr(logger_mod.app_config, "RUNTIME_PROFILE_ID", "dev_profile", raising=False)

    log = logger_mod.get_logger("test.logger", "ml")
    assert not (tmp_path / "machine_learning.log").exists()
    logger_mod.log_event(log, "model_start", model="random_forest", run_id="r1")

    path = tmp_path / "machine_learning.log"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "model_start" in text
    assert "random_forest" in text
    assert "run_id='r1'" in text
    assert "profile_id='dev_profile'" in text
    assert "category='ml'" in text


def test_get_logger_reuses_cached_instance(monkeypatch, tmp_path: Path) -> None:
    """Repeated requests should return the same logger instance."""
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(tmp_path))
    logger_mod._LOGGERS.clear()

    a = logger_mod.get_logger("test.same", "database")
    b = logger_mod.get_logger("test.same", "database")
    assert a is b


def test_log_filename_for_known_category_uses_canonical_name() -> None:
    """Short category labels should map to clearer on-disk filenames."""
    assert logger_mod._log_filename_for_category("pipeline") == "pipeline_orchestration.log"
    assert logger_mod._log_filename_for_category("database") == "database_access.log"
    assert logger_mod._log_filename_for_category("analysis") == "analysis_summary.log"
    assert logger_mod._log_filename_for_category("label_authority") == "label_authority_alerts.log"
    assert logger_mod._log_filename_for_category("menu") == "profile_preflight.log"
    assert logger_mod._log_filename_for_category("ml") == "machine_learning.log"
    assert logger_mod._log_filename_for_category("temporal_readiness") == "temporal_readiness_alerts.log"


def test_log_event_honors_explicit_level(monkeypatch, tmp_path: Path) -> None:
    """Explicit warning/error levels should be written through the logger level field."""
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(tmp_path))
    monkeypatch.setattr(logger_mod.app_config, "LOG_LEVEL", "INFO")
    logger_mod._LOGGERS.clear()

    log = logger_mod.get_logger("test.level", "pipeline")
    logger_mod.log_event(log, "stage_failed", level="ERROR", reason="boom")

    text = (tmp_path / "pipeline_orchestration.log").read_text(encoding="utf-8")
    assert "| ERROR |" in text
    assert "event='stage_failed'" in text


def test_error_log_collects_error_events(monkeypatch, tmp_path: Path) -> None:
    """Error aggregate log should only be created when an error-level event is emitted."""
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(tmp_path))
    monkeypatch.setattr(logger_mod.app_config, "LOG_LEVEL", "INFO")
    logger_mod._LOGGERS.clear()

    log = logger_mod.get_logger("test.error", "menu")
    assert not (tmp_path / "error.log").exists()
    logger_mod.log_event(log, "preflight_failed", level="ERROR", reason="empty_cohort")

    text = (tmp_path / "error.log").read_text(encoding="utf-8")
    assert "| ERROR |" in text
    assert "preflight_failed" in text
