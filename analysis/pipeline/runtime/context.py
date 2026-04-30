"""Run context container used by pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunContext:
    """Mutable runtime context for one pipeline execution.

    Attributes:
        run_id: Runtime run identifier.
        profile_id: Active profile ID.
        output_root: Global output root.
        run_root: Run-scoped output root.
        diagnostics_dir: Run-scoped diagnostics directory.
        metadata: Free-form metadata map.
    """

    run_id: str
    profile_id: str
    output_root: Path
    run_root: Path
    diagnostics_dir: Path
    metadata: dict[str, Any] = field(default_factory=dict)

