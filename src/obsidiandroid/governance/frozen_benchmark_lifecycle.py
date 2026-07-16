"""Persisted, fail-closed lifecycle for frozen benchmark evidence."""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidiandroid.common.hash_utils import hash_payload, sha256_hex
from obsidiandroid.governance.frozen_benchmark_manifest import REQUIRED_SNAPSHOT_NAMES, validate_atomic_evaluation_plan


STATES = ("DRAFT", "COHORT_LOCKED", "SPLIT_LOCKED", "FEATURE_CONTRACTS_LOCKED", "MODELS_LOCKED", "HELDOUT_AUTHORIZED", "HELDOUT_EVALUATED")


def _digest(path: Path) -> str:
    return sha256_hex(path.read_text(encoding="utf-8"))


class FrozenBenchmarkLifecycle:
    def __init__(self, run_root: Path, run_id: str | None = None, *, classification: str = "canonical") -> None:
        if classification not in {"synthetic_validation", "canonical", "exploratory", "legacy_incomplete"}:
            raise ValueError("Unsupported frozen benchmark classification.")
        self.root, self.run_id = Path(run_root).resolve(), str(run_id or uuid.uuid4().hex)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "frozen_benchmark_manifest.json"
        if self.path.exists():
            self.payload = json.loads(self.path.read_text(encoding="utf-8"))
            if self.payload.get("run_id") != self.run_id:
                raise ValueError("Frozen manifest run identity does not match this invocation.")
        else:
            self.payload = {"run_id": self.run_id, "classification": classification, "state": "DRAFT", "history": [], "artifacts": {}, "evaluation_count": 0}
            self._write()

    def _write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def record_artifact(self, name: str, path: Path) -> dict[str, str]:
        candidate = Path(path).resolve()
        if Path(path).is_symlink() or (candidate.parent != self.root and self.root not in candidate.parents):
            raise ValueError("Frozen evidence must be run-local.")
        segments = [segment for segment in re.split(r"[._-]+", candidate.name.lower()) if segment]
        if "latest" in segments or not candidate.is_file():
            raise ValueError("Frozen evidence cannot use global/latest or missing artifacts.")
        entry = {"path": str(candidate), "sha256": _digest(candidate), "run_id": self.run_id}
        self.payload["artifacts"][name] = entry
        self._write()
        return entry

    def _verify_artifact(self, name: str) -> None:
        entry = self.payload["artifacts"][name]
        path = Path(entry["path"])
        if path.is_symlink() or path.resolve().parent != self.root and self.root not in path.resolve().parents:
            raise ValueError(f"Frozen lifecycle evidence path escaped run root: {name}")
        if entry["run_id"] != self.run_id or not path.is_file() or _digest(path) != entry["sha256"]:
            raise ValueError(f"Frozen lifecycle artifact hash mismatch: {name}")
        if name == "sources":
            try:
                source_entries = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("Frozen source snapshot index is unreadable.") from exc
            for source in source_entries:
                source_path = Path(str(source.get("path", "")))
                if source_path.is_symlink() or not source_path.is_file() or self.root not in source_path.resolve().parents:
                    raise ValueError("Frozen source extract is absent or escapes the run root.")
                if source.get("run_id") != self.run_id or _digest(source_path) != source.get("sha256"):
                    raise ValueError("Frozen source extract hash/run identity mismatch.")

    def transition(self, target: str, *, required_artifacts: tuple[str, ...] = (), metadata: dict[str, Any] | None = None) -> None:
        if target not in STATES or STATES.index(target) != STATES.index(self.payload["state"]) + 1:
            raise ValueError("Frozen lifecycle rejects skipped, repeated, or backward transitions.")
        missing = [name for name in required_artifacts if name not in self.payload["artifacts"]]
        if missing:
            raise ValueError(f"Frozen lifecycle missing required artifacts: {missing}")
        for name in required_artifacts:
            self._verify_artifact(name)
        self.payload["state"] = target
        self.payload["history"].append({"state": target, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "metadata": metadata or {}})
        self._write()

    def authorize(self, *, plan: dict[str, Any], source_commit: str, dependency_hash: str, approved_manifest_hash: str, repo_root: Path | None = None) -> None:
        validate_atomic_evaluation_plan(plan)
        if self.payload["classification"] == "canonical":
            if repo_root is None:
                raise ValueError("Canonical heldout authorization requires runtime repository state.")
            clean = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, check=True).stdout == ""
            resolved_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True).stdout.strip()
            if not clean or source_commit != resolved_commit:
                raise ValueError("Canonical heldout authorization requires a clean tree and exact source commit.")
            source_entries = json.loads(Path(self.payload["artifacts"]["sources"]["path"]).read_text(encoding="utf-8"))
            missing_snapshots = REQUIRED_SNAPSHOT_NAMES.difference({entry.get("name") for entry in source_entries})
            if missing_snapshots:
                raise ValueError(f"Canonical heldout authorization missing source snapshots: {sorted(missing_snapshots)}")
        elif self.payload["classification"] not in {"synthetic_validation", "exploratory"}:
            raise ValueError("Only synthetic validation or exploratory runs may be authorized outside canonical runtime checks.")
        if not all((source_commit, dependency_hash, approved_manifest_hash)):
            raise ValueError("Frozen authorization requires source, dependency, and approved-manifest hashes.")
        # Verify every indexed extract before an irreversible state transition.
        for name in self.payload["artifacts"]:
            self._verify_artifact(name)
        self.transition("HELDOUT_AUTHORIZED", required_artifacts=("cohort", "split", "features", "models", "sources"), metadata={"plan": plan, "plan_hash": hash_payload(plan), "source_commit": source_commit, "dependency_hash": dependency_hash, "approved_manifest_hash": approved_manifest_hash})

    def complete_evaluation(self, *, execution_cells: list[str] | tuple[str, ...], prediction_path: Path, comparison_path: Path, metrics_path: Path | None = None) -> None:
        if self.payload["state"] != "HELDOUT_AUTHORIZED" or self.payload["evaluation_count"] != 0:
            raise ValueError("Frozen heldout evaluation is sealed or unauthorized.")
        plan = self.payload["history"][-1]["metadata"].get("plan")
        if not plan or hash_payload(plan) != self.payload["history"][-1]["metadata"].get("plan_hash"):
            raise ValueError("Frozen heldout evaluation authorization plan is missing or altered.")
        required = [f"{arm}:{variant}:{model}" for arm in plan["arms"] for variant in (["base"] if arm == "A" else ["detection_only", "detection_plus_mask"]) for model in plan["models"]]
        if list(execution_cells) != required or len(set(execution_cells)) != len(execution_cells):
            raise ValueError("Frozen heldout evaluation requires the complete atomic plan.")
        self.record_artifact("predictions", prediction_path)
        self.record_artifact("comparisons", comparison_path)
        if metrics_path is not None:
            self.record_artifact("metrics", metrics_path)
        self.payload["evaluation_count"] = 1
        required = ("predictions", "comparisons", "metrics") if metrics_path is not None else ("predictions", "comparisons")
        self.transition("HELDOUT_EVALUATED", required_artifacts=required, metadata={"first_heldout_run_id": self.run_id})
