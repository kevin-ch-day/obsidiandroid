"""Shared pytest fixtures for test isolation."""

from __future__ import annotations

import builtins
import logging
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Standard bootstrap for source checkouts (idempotent).
from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path  # noqa: E402

ensure_repo_src_on_sys_path()

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
        except (AttributeError, TypeError):
            continue
        if name in _SLOW_TEST_MODULES:
            item.add_marker(pytest.mark.slow)


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
            from obsidiandroid.reporting import export_manager

            monkeypatch.setattr(export_manager, "OUTPUT_ROOT", output_root.resolve(), raising=False)
        except Exception:
            pass
        try:
            import obsidiandroid.governance.run_manifest as run_manifest

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
            except (OSError, RuntimeError, TypeError, ValueError):
                pass
            try:
                logger_obj.removeHandler(handler)
            except (OSError, RuntimeError, TypeError, ValueError):
                pass
    for handler in list(logging.getLogger().handlers):
        try:
            handler.flush()
            handler.close()
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        try:
            logging.getLogger().removeHandler(handler)
        except (OSError, RuntimeError, TypeError, ValueError):
            pass


@pytest.fixture
def make_run_diagnostics_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Create canonical tmp output layout and pin ``RUNTIME_OUTPUT_ROOT_BASE`` to it."""

    def _make(run_id: str = "rid") -> tuple[Path, Path, Path]:
        output_root = tmp_path / "output"
        diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
        global_diag = output_root / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        global_diag.mkdir(parents=True, exist_ok=True)
        try:
            from config import app_config

            monkeypatch.setattr(
                app_config,
                "RUNTIME_OUTPUT_ROOT_BASE",
                str(output_root),
                raising=False,
            )
        except Exception:
            pass
        return output_root, diagnostics_dir, global_diag

    return _make


@pytest.fixture
def write_text_file():
    """Write UTF-8 text to a path, creating parents automatically."""

    def _write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    return _write
