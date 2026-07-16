"""Persisted, fail-closed lifecycle for frozen benchmark evidence."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidiandroid.common.hash_utils import hash_payload, sha256_hex
from obsidiandroid.governance.frozen_benchmark_manifest import validate_atomic_evaluation_plan


STATES = ("DRAFT", "COHORT_LOCKED", "SPLIT_LOCKED", "FEATURE_CONTRACTS_LOCKED", "MODELS_LOCKED", "HELDOUT_AUTHORIZED", "HELDOUT_EVALUATED")


def _digest(path: Path) -> str:
    return sha256_hex(path.read_text(encoding="utf-8"))


class FrozenBenchmarkLifecycle:
    def __init__(self, run_root: Path, run_id: str, *, classification: str = "canonical") -> None:
        self.root, self.run_id = Path(run_root).resolve(), str(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "frozen_benchmark_manifest.json"
        if self.path.exists():
            self.payload = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.payload = {"run_id": self.run_id, "classification": classification, "state": "DRAFT", "history": [], "artifacts": {}, "evaluation_count": 0}
            self._write()

    def _write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def record_artifact(self, name: str, path: Path) -> dict[str, str]:
        candidate = Path(path).resolve()
        if candidate.parent != self.root and self.root not in candidate.parents:
            raise ValueError("Frozen evidence must be run-local.")
        if ".latest." in candidate.name or not candidate.is_file():
            raise ValueError("Frozen evidence cannot use global/latest or missing artifacts.")
        entry = {"path": str(candidate), "sha256": _digest(candidate), "run_id": self.run_id}
        self.payload["artifacts"][name] = entry
        self._write()
        return entry

    def transition(self, target: str, *, required_artifacts: tuple[str, ...] = (), metadata: dict[str, Any] | None = None) -> None:
        if target not in STATES or STATES.index(target) != STATES.index(self.payload["state"]) + 1:
            raise ValueError("Frozen lifecycle rejects skipped, repeated, or backward transitions.")
        missing = [name for name in required_artifacts if name not in self.payload["artifacts"]]
        if missing:
            raise ValueError(f"Frozen lifecycle missing required artifacts: {missing}")
        for name in required_artifacts:
            entry = self.payload["artifacts"][name]
            if entry["run_id"] != self.run_id or _digest(Path(entry["path"])) != entry["sha256"]:
                raise ValueError(f"Frozen lifecycle artifact hash mismatch: {name}")
        self.payload["state"] = target
        self.payload["history"].append({"state": target, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "metadata": metadata or {}})
        self._write()

    def authorize(self, *, plan: dict[str, Any], clean_tree: bool, source_commit: str, dependency_hash: str, approved_manifest_hash: str) -> None:
        validate_atomic_evaluation_plan(plan)
        if self.payload["classification"] != "canonical" or not clean_tree:
            raise ValueError("Canonical heldout authorization requires a clean canonical run.")
        if not all((source_commit, dependency_hash, approved_manifest_hash)):
            raise ValueError("Frozen authorization requires source, dependency, and approved-manifest hashes.")
        self.transition("HELDOUT_AUTHORIZED", required_artifacts=("cohort", "split", "features", "models", "sources"), metadata={"plan_hash": hash_payload(plan), "source_commit": source_commit, "dependency_hash": dependency_hash, "approved_manifest_hash": approved_manifest_hash})

    def complete_evaluation(self, *, execution_cells: set[str], required_cells: set[str], prediction_path: Path, comparison_path: Path) -> None:
        if self.payload["state"] != "HELDOUT_AUTHORIZED" or self.payload["evaluation_count"] != 0:
            raise ValueError("Frozen heldout evaluation is sealed or unauthorized.")
        if execution_cells != required_cells:
            raise ValueError("Frozen heldout evaluation requires the complete atomic plan.")
        self.record_artifact("predictions", prediction_path)
        self.record_artifact("comparisons", comparison_path)
        self.payload["evaluation_count"] = 1
        self.transition("HELDOUT_EVALUATED", required_artifacts=("predictions", "comparisons"), metadata={"first_heldout_run_id": self.run_id})
