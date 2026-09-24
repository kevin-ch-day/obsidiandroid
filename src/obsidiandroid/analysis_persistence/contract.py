"""Strict, JSON-native analytical contracts, separate from assessment authority."""

from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path
from datetime import datetime

VERSION = "analysis-persistence-v1"
ROLES = {"train", "validation", "test", "inference_only", "excluded"}
STATES = {
    "PREDICTED",
    "EXCLUDED",
    "FEATURE_INCOMPLETE",
    "LABEL_UNAVAILABLE",
    "MODEL_ERROR",
    "INVALID_ARTIFACT",
    "NOT_APPLICABLE",
}


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def reject_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(
                r"password|passwd|secret|api_key|access_token|connection_string|dsn|credential",
                key,
                re.I,
            ):
                raise ValueError("Credential-shaped metadata forbidden")
            reject_secrets(child)
    elif isinstance(value, list):
        for child in value:
            reject_secrets(child)
    elif isinstance(value, str) and re.search(r"://[^\s/]+:[^\s/]+@", value):
        raise ValueError("Credential-bearing URL forbidden")


def validate_spec(spec):
    reject_secrets(spec)
    canonical(spec)
    for key in (
        "profile",
        "mode",
        "code",
        "feature_schema",
        "source_digests",
        "evidence_cutoff",
        "seeds",
        "label_authority",
        "cohort_id",
    ):
        if key not in spec:
            raise ValueError("Missing scientific run identity: " + key)
    cutoff = datetime.fromisoformat(spec["evidence_cutoff"].replace("Z", "+00:00"))
    if cutoff.utcoffset() is None or cutoff.utcoffset().total_seconds() != 0:
        raise ValueError("UTC cutoff required")
    if not spec["code"].get("git_commit") or not spec["code"].get("worktree_sha256"):
        raise ValueError("Exact code state required")
    if not isinstance(spec["feature_schema"], list) or len(
        set(spec["feature_schema"])
    ) != len(spec["feature_schema"]):
        raise ValueError("Ordered unique features required")


def validate_result(spec, result):
    validate_spec(spec)
    reject_secrets(result)
    canonical(result)
    members = result["members"]
    hashes = [r["sha256"] for r in members]
    if (
        not hashes
        or len(set(hashes)) != len(hashes)
        or any(not re.fullmatch("[a-f0-9]{64}", h) for h in hashes)
    ):
        raise ValueError("Unique exact SHA membership required")
    bysha = {r["sha256"]: r for r in members}
    for r in members:
        if r["role"] not in ROLES or not r.get("eligibility") or not r.get("outcome"):
            raise ValueError("Explicit membership outcomes required")
        if r["role"] == "excluded" and not r.get("reason"):
            raise ValueError("Exclusion reason required")
    if not result["models"]:
        raise ValueError("At least one model outcome required")
    seen = set()
    for model in result["models"]:
        if model["key"] in seen:
            raise ValueError("Duplicate model identity")
        seen.add(model["key"])
        for key in (
            "implementation",
            "parameters",
            "dimension",
            "feature_schema",
            "training_digest",
            "library_versions",
            "seed",
            "split_contract",
            "predictions",
            "metrics",
            "confusion",
        ):
            if key not in model:
                raise ValueError("Missing model identity: " + key)
        if model["dimension"] not in {"family", "type", "variant"}:
            raise ValueError("Explicit prediction dimension required")
        if model["feature_schema"] != spec.get("model_feature_schemas", {}).get(
            model["key"], spec["feature_schema"]
        ):
            raise ValueError("Feature ordering mismatch")
        splits = model["split_contract"]["members"]
        if set(splits) != set(hashes) or any(v not in ROLES for v in splits.values()):
            raise ValueError("Complete split ledger required")
        train = sorted(h for h, v in splits.items() if v == "train")
        if model["training_digest"] != digest(train):
            raise ValueError("Training identity mismatch")
        predictions = model["predictions"]
        keys = [(p["sha256"], p.get("rank", 1)) for p in predictions]
        if len(keys) != len(set(keys)) or {h for h, k in keys} != set(hashes):
            raise ValueError("Explicit per-SHA outcome required, including exclusions")
        for p in predictions:
            if p["status"] not in STATES or p.get("rank", 1) < 1:
                raise ValueError("Invalid prediction status/rank")
            if p["status"] == "PREDICTED" and p.get("predicted") is None:
                raise ValueError("Missing prediction")
            score = p.get("score")
            if score is not None and (
                not isinstance(score, (int, float)) or not math.isfinite(score)
            ):
                raise ValueError("Invalid score")
        # Confusion cells must reproduce the recorded rank-one test predictions.
        from collections import Counter

        expected = Counter(
            (p["actual"], p["predicted"])
            for p in predictions
            if splits[p["sha256"]] == "test"
            and p["status"] == "PREDICTED"
            and p.get("actual") is not None
            and p.get("rank", 1) == 1
        )
        cells = {
            (c["true"], c["predicted"]): c["count"]
            for c in model["confusion"]
            if c["count"]
        }
        if len(cells) != sum(
            bool(c["count"]) for c in model["confusion"]
        ) or cells != dict(expected):
            raise ValueError("Confusion matrix contradicts predictions")
    if not result["models"]:
        raise ValueError("No model execution outputs")
    return digest(
        {
            "spec": spec,
            "members": members,
            "models": [
                {
                    k: v
                    for k, v in m.items()
                    if k not in {"predictions", "metrics", "confusion", "artifact"}
                }
                for m in result["models"]
            ],
        }
    )


def artifact(root, relative, *, kind, required=True):
    root = Path(root).absolute()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Relative artifact path required")
    path = root
    if path.is_symlink():
        raise ValueError("Symlink root refused")
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlink artifact path refused")
    if not path.is_file():
        raise ValueError("Artifact missing")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return {
        "kind": kind,
        "path": relative.as_posix(),
        "sha256": h.hexdigest(),
        "byte_size": path.stat().st_size,
        "required": bool(required),
    }
