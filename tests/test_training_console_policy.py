"""Tests for training console-noise policy helpers."""

from __future__ import annotations

import numpy as np

from obsidiandroid.modeling import training_console_policy


def test_emit_class_imbalance_notice_uses_note_once_for_diagnostic_family_surface(
    monkeypatch,
) -> None:
    """Broad diagnostic family runs should emit a single note, not repeated warnings."""
    notes: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        training_console_policy.app_config,
        "RUNTIME_SUPPORT_FLOOR_MODE",
        "diagnostic_only",
        raising=False,
    )
    monkeypatch.setattr(
        training_console_policy.app_config,
        "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD",
        "family_id",
        raising=False,
    )
    monkeypatch.setattr(
        training_console_policy.app_config,
        "RUNTIME_CLASS_IMBALANCE_NOTICE_EMITTED",
        False,
        raising=False,
    )
    monkeypatch.setattr(training_console_policy.du, "print_note", lambda msg: notes.append(str(msg)))
    monkeypatch.setattr(training_console_policy.du, "print_warning", lambda msg: warnings.append(str(msg)))

    y = np.array([0] + [1] * 20 + [2] * 10)
    training_console_policy.emit_class_imbalance_notice(y)
    training_console_policy.emit_class_imbalance_notice(y)

    assert len(notes) == 1
    assert not warnings
    assert "all-current diagnostic run" in notes[0]


def test_emit_class_imbalance_notice_uses_warning_for_benchmark_surface(monkeypatch) -> None:
    """Benchmark surfaces should keep a warning when imbalance is severe."""
    notes: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        training_console_policy.app_config,
        "RUNTIME_SUPPORT_FLOOR_MODE",
        "benchmark_eligibility",
        raising=False,
    )
    monkeypatch.setattr(
        training_console_policy.app_config,
        "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD",
        "family_id",
        raising=False,
    )
    monkeypatch.setattr(
        training_console_policy.app_config,
        "RUNTIME_CLASS_IMBALANCE_NOTICE_EMITTED",
        False,
        raising=False,
    )
    monkeypatch.setattr(training_console_policy.du, "print_note", lambda msg: notes.append(str(msg)))
    monkeypatch.setattr(training_console_policy.du, "print_warning", lambda msg: warnings.append(str(msg)))

    y = np.array([0] + [1] * 20 + [2] * 10)
    training_console_policy.emit_class_imbalance_notice(y)

    assert not notes
    assert len(warnings) == 1
    assert "benchmark family surface" in warnings[0]


def test_should_print_detailed_classification_report_respects_flags(monkeypatch) -> None:
    """Detailed sklearn text reports should only print in debug/detailed modes."""
    monkeypatch.setattr(training_console_policy.app_config, "DEBUG_MODE", False, raising=False)
    monkeypatch.setattr(
        training_console_policy.app_config,
        "ENABLE_DETAILED_PER_CLASS_REPORTS",
        False,
        raising=False,
    )
    assert training_console_policy.should_print_detailed_classification_report() is False

    monkeypatch.setattr(
        training_console_policy.app_config,
        "ENABLE_DETAILED_PER_CLASS_REPORTS",
        True,
        raising=False,
    )
    assert training_console_policy.should_print_detailed_classification_report() is True


def test_should_print_training_analysis_only_for_grid_or_debug(monkeypatch) -> None:
    """Normal non-grid training should stay quiet unless debug is on."""
    monkeypatch.setattr(training_console_policy.app_config, "DEBUG_MODE", False, raising=False)
    assert training_console_policy.should_print_training_analysis(cv_folds=None) is False
    assert training_console_policy.should_print_training_analysis(cv_folds=3) is True

    monkeypatch.setattr(training_console_policy.app_config, "DEBUG_MODE", True, raising=False)
    assert training_console_policy.should_print_training_analysis(cv_folds=None) is True


def test_should_print_training_label_summary_respects_flags(monkeypatch) -> None:
    """Per-model top-class summaries should stay hidden on normal runs."""
    monkeypatch.setattr(training_console_policy.app_config, "DEBUG_MODE", False, raising=False)
    monkeypatch.setattr(
        training_console_policy.app_config,
        "ENABLE_DETAILED_PER_CLASS_REPORTS",
        False,
        raising=False,
    )
    assert training_console_policy.should_print_training_label_summary() is False

    monkeypatch.setattr(training_console_policy.app_config, "DEBUG_MODE", True, raising=False)
    assert training_console_policy.should_print_training_label_summary() is True
