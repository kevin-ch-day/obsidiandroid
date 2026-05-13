"""Legacy diagnostics package shim (Pass 65).

Registers ``analysis.diagnostics.<name>`` in ``sys.modules`` to point at the same
:class:`types.ModuleType` objects as ``obsidiandroid.diagnostics.<name>`` so legacy
imports and monkeypatch surfaces keep working during migration.

Registration logic lives in :mod:`obsidiandroid.diagnostics.analysis_diagnostics_shim`.
"""

from __future__ import annotations

from obsidiandroid.diagnostics.analysis_diagnostics_shim import (
    register_analysis_diagnostics_legacy_aliases,
)

register_analysis_diagnostics_legacy_aliases()

__all__: list[str] = []
