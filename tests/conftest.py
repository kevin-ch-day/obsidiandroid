"""Shared pytest fixtures for test isolation."""

from __future__ import annotations

import builtins
import logging
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

# Whole-module slow tier: keeps default `pytest` fast; run full suite with `-m "slow or not slow"`.
_SLOW_TEST_MODULES = frozenset(
    {
        "test_classification_label_resolver_taxonomy_audit.py",
        "test_export_manager.py",
        "test_main_stop_after_training.py",
        "test_model_trainer_factory.py",
        "test_paper2_scripts.py",
        "test_stage_manifest.py",
        "test_stage_permission_trends_report.py",
        "test_startup_menu.py",
        "test_training_trainer.py",
    }
)


def pytest_collection_modifyitems(config, items) -> None:  # noqa: ARG001
    """Tag known slow integration modules so default `-m "not slow"` skips them."""
    for item in items:
        try:
            path = getattr(item, "path", None)
            name = Path(path).name if path is not None else Path(item.fspath).name
        except Exception:
            continue
        if name in _SLOW_TEST_MODULES:
            item.add_marker(pytest.mark.slow)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def isolate_output_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Route output artifacts to a per-test temporary root."""
    output_root = tmp_path / "output"
    output_root.mkdir(parents=True, exist_ok=True)
    diagnostics_root = output_root / "diagnostics"
    diagnostics_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("OBSIDIANDROID_TEST_OUTPUT_ROOT", str(output_root))
    log_root = tmp_path / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(log_root))

    repo_output_root = (REPO_ROOT / "output").resolve()

    original_open = builtins.open

    def _guarded_open(file, *args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            candidate = Path(file).resolve()
            if candidate.is_relative_to(repo_output_root):
                if not candidate.is_relative_to(output_root.resolve()):
                    raise AssertionError(
                        f"Blocked test read/write outside tmp output root: {candidate}"
                    )
        except TypeError:
            # Non-path open targets (fds, buffers) are ignored.
            pass
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _guarded_open)

    try:
        from config import app_config

        monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
        monkeypatch.setattr(
            app_config,
            "PAPER_COHORT_SAMPLE_IDS_FILE",
            str(diagnostics_root / "paper_cohort_sample_ids.csv"),
            raising=False,
        )
        try:
            from utils import export_manager

            monkeypatch.setattr(export_manager, "OUTPUT_ROOT", output_root.resolve(), raising=False)
        except Exception:
            pass
        try:
            from utils import run_manifest

            monkeypatch.setattr(
                run_manifest,
                "MANIFEST_PATH",
                diagnostics_root / "run_manifest.latest.json",
                raising=False,
            )
        except Exception:
            pass
    except Exception:
        # Some tests may import minimal modules only.
        pass

    yield

    # Windows can hold open file handles from cached loggers; force-close handlers
    # after each test to keep tmp cleanup deterministic.
    manager = logging.Logger.manager
    for logger_obj in list(manager.loggerDict.values()):
        if not isinstance(logger_obj, logging.Logger):
            continue
        for handler in list(logger_obj.handlers):
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass
            try:
                logger_obj.removeHandler(handler)
            except Exception:
                pass
    for handler in list(logging.getLogger().handlers):
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass
        try:
            logging.getLogger().removeHandler(handler)
        except Exception:
            pass
