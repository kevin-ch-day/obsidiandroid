"""Opt-in pipeline capture using exact in-memory cohort, splits and model outputs."""

from contextvars import ContextVar
from collections import Counter
from datetime import datetime, UTC
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import subprocess
from .contract import artifact, canonical, digest

ACTIVE = ContextVar("analytical_run_capture", default=None)


def code_identity(root):
    root = Path(root)
    paths = set(
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            text=True,
        ).splitlines()
    )
    rows = []
    for name in sorted(paths):
        p = root / name
        if (
            p.is_file()
            and not p.is_symlink()
            and p.suffix in {".py", ".sql", ".yaml", ".toml", ".sh"}
        ):
            rows.append((name, hashlib.sha256(p.read_bytes()).hexdigest()))
    return {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            )
        ),
        "worktree_sha256": digest(rows),
    }


def capture_cohort(frame):
    session = ACTIVE.get()
    if session is None:
        return
    if "sha256" not in frame.columns:
        raise ValueError("Persisted analysis requires exact SHA source membership")
    for index, row in frame.iterrows():
        sid = row.get("sample_id", index)
        sha = str(row["sha256"]).lower()
        if sid in session.cohort or sha in session.cohort.values():
            raise ValueError("Duplicate source identity")
        session.cohort[sid] = sha
    session.source_records = frame.to_json(orient="split", date_format="iso")


def _plain(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {
            "__float__": "NaN"
            if math.isnan(value)
            else "+Infinity"
            if value > 0
            else "-Infinity"
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "item"):
        return _plain(value.item())
    raise ValueError("Model configuration is not reproducibly serializable")


def capture_model(key, result, features, labels):
    session = ACTIVE.get()
    if session is None:
        return
    session.model(key, result, features, labels)


class PipelineCapture:
    def __init__(self, store, profile, root, output):
        self.store = store
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.cohort = {}
        self.source_records = None
        self.models = []
        self.refs = []
        self.spec = {
            "profile": str(profile),
            "mode": "supervised",
            "code": code_identity(root),
            "feature_schema": [],
            "source_digests": {"collection": "pending"},
            "evidence_cutoff": datetime.now(UTC).isoformat(),
            "seeds": {},
            "label_authority": "pipeline_reference_labels_not_governed_predictions",
            "cohort_id": str(profile),
            "membership_boundary": "SQL profile scope before Python preparation and alignment; pre-query exclusions are outside this cohort",
        }
        self.run_id = store.begin_run(self.spec)

    def model(self, key, result, features, labels):
        if not self.cohort:
            raise ValueError("Source cohort not captured")
        columns = [str(c) for c in features.columns]
        if any(m["key"] == key for m in self.models):
            raise ValueError(
                "Duplicate model execution key; ablations require distinct runs"
            )
        self.spec.setdefault("model_feature_schemas", {})[key] = columns
        if not self.models:
            self.spec["feature_schema"] = columns
        mapping = self.cohort
        train = set(result.get("sample_ids_train", []))
        test = set(result.get("sample_ids_test", []))
        if not train or not test or train & test or not (train | test) <= set(mapping):
            raise ValueError("Exact trainer split required")
        predictions = []
        splits = {}
        split_labels = {}
        for sid, sha in mapping.items():
            splits[sha] = (
                "train" if sid in train else "test" if sid in test else "excluded"
            )
            meta = result["prediction_metadata"].get(sid)
            if meta is None:
                predictions.append(
                    {
                        "sha256": sha,
                        "status": "EXCLUDED",
                        "reason": "Not present in aligned model inputs",
                    }
                )
                continue
            if splits[sha] == "excluded":
                splits[sha] = "inference_only"
            actual = result["true_labels"].get(sid)
            actual = str(actual) if actual is not None else None
            split_labels[sha] = actual
            predictions.append(
                {
                    "sha256": sha,
                    "status": "PREDICTED",
                    "actual": actual,
                    "predicted": str(meta["decoded_label"]),
                    "score": float(meta["confidence"])
                    if hasattr(result["model"], "predict_proba")
                    else None,
                }
            )
        params = _plain(result["model"].get_params(deep=False))
        from config import app_config

        split_meta = dict(getattr(app_config, "RUNTIME_SPLIT_METADATA", {}) or {})
        if not split_meta.get("split_algorithm") or "split_seed" not in split_meta:
            raise ValueError("Actual split contract metadata missing")
        target = str(split_meta.get("label_target", "")).lower()
        dimensions = {
            "family": "family",
            "family_id": "family",
            "family_canonical": "family",
            "malware_family": "family",
            "type": "type",
            "type_slug": "type",
            "malware_type": "type",
            "variant": "variant",
        }
        if target not in dimensions:
            raise ValueError("Explicit family/type/variant target required")
        dimension = dimensions[target]
        seed = split_meta["split_seed"]
        self.spec["seeds"][key] = {"split": seed, "model": params.get("random_state")}
        model_file = result.get("export_paths", {}).get("model_path")
        model_role = None
        metadata_role = None
        if model_file:
            source = Path(model_file)
            if source.is_symlink() or not source.is_file():
                raise ValueError("Model export missing/unsafe")
            name = key + "_model" + source.suffix
            shutil.copyfile(source, self.output / name)
            model_role = key + "_model"
            self.refs.append(artifact(self.output, name, kind=model_role))
            metadata_file = result.get("export_paths", {}).get("metadata_path")
            if metadata_file:
                metadata_source = Path(metadata_file)
                if metadata_source.is_symlink() or not metadata_source.is_file():
                    raise ValueError("Model metadata export missing/unsafe")
                metadata_name = key + "_model_metadata.json"
                shutil.copyfile(metadata_source, self.output / metadata_name)
                metadata_role = key + "_model_metadata"
                self.refs.append(
                    artifact(self.output, metadata_name, kind=metadata_role)
                )
        feature_name = key + "_features.json"
        feature_bytes = features.to_json(orient="split", date_format="iso")
        (self.output / feature_name).write_text(feature_bytes)
        self.refs.append(artifact(self.output, feature_name, kind=key + "_features"))
        self.spec["source_digests"][key + "_features"] = hashlib.sha256(
            feature_bytes.encode()
        ).hexdigest()
        cells = Counter(
            (p["actual"], p["predicted"])
            for p in predictions
            if splits[p["sha256"]] == "test"
            and p["status"] == "PREDICTED"
            and p["actual"] is not None
        )
        from sklearn.metrics import classification_report, accuracy_score

        evaluated = [
            p
            for p in predictions
            if splits[p["sha256"]] == "test"
            and p["status"] == "PREDICTED"
            and p["actual"] is not None
        ]
        metrics = (
            {
                "accuracy": float(
                    accuracy_score(
                        [p["actual"] for p in evaluated],
                        [p["predicted"] for p in evaluated],
                    )
                ),
                "classification_report": classification_report(
                    [p["actual"] for p in evaluated],
                    [p["predicted"] for p in evaluated],
                    output_dict=True,
                    zero_division=0,
                ),
            }
            if evaluated
            else {}
        )
        self.models.append(
            {
                "key": key,
                "implementation": type(result["model"]).__module__
                + "."
                + type(result["model"]).__name__,
                "parameters": params,
                "dimension": dimension,
                "feature_schema": columns,
                "training_digest": digest(sorted(mapping[s] for s in train)),
                "library_versions": {
                    n: importlib.metadata.version(n)
                    for n in ("scikit-learn", "numpy", "scipy")
                },
                "seed": seed,
                "split_contract": {
                    "members": splits,
                    "labels": split_labels,
                    "seed": seed,
                    "stratification": split_meta["split_algorithm"],
                    "algorithm_version": split_meta.get("split_algorithm_version"),
                    "upstream_split_hash": split_meta.get("split_hash"),
                    "feature_selection": _plain(
                        result.get("feature_selection_contract", {})
                    ),
                },
                "predictions": predictions,
                "metrics": metrics,
                "confusion": [
                    {"true": a, "predicted": b, "count": n}
                    for (a, b), n in sorted(cells.items())
                ],
                "artifact": model_role,
                "metadata_artifact": metadata_role,
            }
        )

    def failure_context(self):
        """Retain known identities on failure without claiming complete model output."""
        return {
            "members": [
                {"sha256": sha, "source_sample_id": int(sid)}
                for sid, sha in self.cohort.items()
            ],
            "cohort_digest": digest(sorted(self.cohort.values())),
            "source_captured": self.source_records is not None,
            "requested_models": getattr(self, "expected_models", []),
            "completed_model_keys": [m["key"] for m in self.models],
            "artifact_root": str(self.output.absolute()),
            "captured_artifact_references": self.refs,
            "finalization_complete": False,
        }

    def finish(self):
        expected = getattr(self, "expected_models", [])
        if expected and set(expected) != {m["key"] for m in self.models}:
            raise ValueError(
                "Requested models missing; analytical run cannot claim success"
            )
        if not self.models or not self.cohort:
            raise ValueError("No complete model output")
        (self.output / "source_cohort.json").write_text(self.source_records)
        self.refs.append(
            artifact(self.output, "source_cohort.json", kind="source_cohort")
        )
        self.spec["source_digests"].pop("collection")
        self.spec["source_digests"]["cohort"] = hashlib.sha256(
            self.source_records.encode()
        ).hexdigest()
        self.spec["cohort_digest"] = digest(sorted(self.cohort.values()))
        roles = self.models[0]["split_contract"]["members"]
        members = [
            {
                "sha256": sha,
                "artifact_id": sha,
                "source_sample_id": int(sid),
                "source_sample_namespace": "erebus_sample_id",
                "role": roles[sha],
                "eligibility": "ELIGIBLE" if roles[sha] != "excluded" else "EXCLUDED",
                "outcome": "PREDICTED" if roles[sha] != "excluded" else "EXCLUDED",
                "reason": "Not aligned for modeling"
                if roles[sha] == "excluded"
                else None,
            }
            for sid, sha in self.cohort.items()
        ]
        result = {
            "members": members,
            "models": self.models,
            "artifacts": self.refs,
            "resolved_spec": self.spec,
        }
        (self.output / "analysis_result.json").write_text(canonical(result) + "\n")
        return self.store.finalize_run(self.run_id, result, artifact_root=self.output)
