"""Console-noise policy helpers for model training."""

from __future__ import annotations

from collections import Counter

from config import app_config
from obsidiandroid.cli.ui import display as du


def should_print_detailed_classification_report() -> bool:
    """Return whether per-class sklearn text reports should be printed to console."""
    return bool(
        getattr(app_config, "DEBUG_MODE", False)
        or getattr(app_config, "ENABLE_DETAILED_PER_CLASS_REPORTS", False)
    )


def should_print_training_analysis(*, cv_folds: int | None = None) -> bool:
    """Return whether trainer analysis blocks should be printed to console."""
    return bool(cv_folds is not None or getattr(app_config, "DEBUG_MODE", False))


def should_print_training_label_summary() -> bool:
    """Return whether per-model label summary blocks should be printed to console."""
    return bool(
        getattr(app_config, "DEBUG_MODE", False)
        or getattr(app_config, "ENABLE_DETAILED_PER_CLASS_REPORTS", False)
    )


def emit_class_imbalance_notice(y_train) -> None:
    """Emit a profile-aware class-imbalance notice once per run."""
    label_dist = Counter(int(x) for x in y_train)
    if not label_dist:
        return
    min_ratio = min(label_dist.values()) / max(label_dist.values())
    if min_ratio >= 0.1:
        return

    already_emitted = bool(
        getattr(app_config, "RUNTIME_CLASS_IMBALANCE_NOTICE_EMITTED", False)
    )
    support_floor_mode = str(
        getattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "membership_gate") or "membership_gate"
    ).strip().lower()
    training_label_field = str(
        getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id") or "family_id"
    ).strip().lower()

    if training_label_field == "type_slug":
        surface_label = "type-level target surface"
    elif support_floor_mode == "diagnostic_only":
        surface_label = "broad diagnostic family surface"
    elif support_floor_mode == "benchmark_eligibility":
        surface_label = "benchmark family surface"
    else:
        surface_label = "family target surface"

    top_counts = sorted((int(v) for v in label_dist.values()), reverse=True)[:5]
    msg = (
        f"[TRAINING] Class imbalance detected on the {surface_label} "
        f"(classes={len(label_dist)}, top_supports={top_counts})."
    )
    if support_floor_mode == "diagnostic_only" and training_label_field == "family_id":
        msg += " This is expected on the all-current diagnostic run."
        if not already_emitted:
            du.print_note(msg)
            setattr(app_config, "RUNTIME_CLASS_IMBALANCE_NOTICE_EMITTED", True)
        return
    if not already_emitted:
        du.print_warning(msg)
        setattr(app_config, "RUNTIME_CLASS_IMBALANCE_NOTICE_EMITTED", True)
