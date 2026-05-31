"""Centralized artifact path resolution for run-scoped outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactPaths:
    """Path resolver for run-scoped pipeline artifacts.

    Attributes:
        output_root: Global output root.
        run_id: Active run ID.
    """

    output_root: Path
    run_id: str

    @property
    def run_root(self) -> Path:
        """Return root directory for the active run."""
        return self.output_root / "runs" / str(self.run_id)

    @property
    def diagnostics_dir(self) -> Path:
        """Return run-scoped diagnostics directory."""
        return self.run_root / "diagnostics"

    @property
    def evidence_bundle_dir(self) -> Path:
        """Return canonical run-scoped evidence-bundle directory."""
        return self.run_root / "evidence_bundle"

    def resolve(self, *, kind: str, filename: str) -> Path:
        """Resolve a run-scoped artifact path.

        Args:
            kind: Subdirectory key under run root.
            filename: Output filename.

        Returns:
            Absolute run-scoped path.
        """
        safe_kind = str(kind).strip().replace("\\", "/").strip("/")
        safe_name = str(filename).strip().replace("\\", "/").split("/")[-1]
        target_dir = self.run_root / safe_kind if safe_kind else self.run_root
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / safe_name
