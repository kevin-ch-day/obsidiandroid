"""Shared pytest fixtures for test isolation."""

from __future__ import annotations

import builtins
import logging
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
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
