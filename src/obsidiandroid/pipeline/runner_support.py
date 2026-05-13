"""Shared helpers for ``obsidiandroid.pipeline.runner`` (artifact list, stage errors, main sync).

Keeping these symbols out of ``runner.py`` reduces module size while preserving behavior:
``run_pipeline`` still owns diagnostics globals and ``_set_diagnostics_dir`` so tests can
monkeypatch ``pipeline.runner.DIAGNOSTICS_DIR`` unchanged.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from obsidiandroid.governance.integrity import enforce_run_scoped_artifact_paths


def sync_main_module_diagnostics(path: str) -> None:
    """Mirror diagnostics path onto ``main`` when loaded (tests patch ``main.DIAGNOSTICS_DIR``)."""
    main_mod = sys.modules.get("main")
    if main_mod is not None and hasattr(main_mod, "DIAGNOSTICS_DIR"):
        setattr(main_mod, "DIAGNOSTICS_DIR", path)


class ScopedArtifactList(list[str]):
    """Artifact list with immediate run-scope path enforcement on append/extend."""

    def __init__(
        self,
        *,
        strict_run_scoped: bool,
        run_root_getter: Callable[[], str],
        output_root_getter: Callable[[], str],
        allow_global_getter: Callable[[], bool],
    ) -> None:
        super().__init__()
        self._strict = bool(strict_run_scoped)
        self._run_root_getter = run_root_getter
        self._output_root_getter = output_root_getter
        self._allow_global_getter = allow_global_getter

    def _validate(self, item: str) -> None:
        if not self._strict:
            return
        if bool(self._allow_global_getter()):
            return
        path_text = str(item).strip()
        if not path_text:
            return
        enforce_run_scoped_artifact_paths(
            artifact_paths=[path_text],
            run_root=Path(str(self._run_root_getter())),
            output_root=Path(str(self._output_root_getter())),
            allow_latest=True,
        )

    def append(self, item: str) -> None:  # type: ignore[override]
        self._validate(str(item))
        super().append(str(item))

    def extend(self, items) -> None:  # type: ignore[override]
        for item in items:
            self.append(str(item))


class PipelineStageFailure(RuntimeError):
    """Expected pipeline-stage failure that should finalize cleanly."""
