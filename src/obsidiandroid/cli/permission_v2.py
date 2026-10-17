"""Read-only inspection and feature acceptance for an independently approved PI export.

The root-controlled anchor remains mandatory. This command neither installs an
approval nor trains a model, persists Core records, or changes database grants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import warnings

import pandas as pd

from obsidiandroid.orchestration import permission_v2_export as v2
from obsidiandroid.pipeline.permission_run_validity import (
    assert_training_permission_validity,
    evaluate_permission_run_validity,
    permission_frame_status,
)


def inspect_export(export_path: Path) -> dict:
    export_bytes, _, export = v2._checked_export(export_path)
    return {
        "status": "APPROVED_EXACT_EVIDENCE_AVAILABLE",
        "samples": len(export["samples"]),
        "raw_members": sum(len(row["members"]) for row in export["samples"]),
        "projected_pairs": sum(len({m["projected_token"] for m in row["members"]})
                               for row in export["samples"]),
        "evidence_state": "PROVIDER_REPORTED_UNRESOLVED",
        "export_sha256": hashlib.sha256(export_bytes).hexdigest(),
        "source_commit": export["source_commit"],
        "manifest_sha256": export["manifest_sha256"],
    }


def check_features(export_path: Path, training_ids_path: Path) -> dict:
    """Build and reverify an in-memory frame using the existing frozen split."""
    _, _, export = v2._checked_export(export_path)
    samples = pd.DataFrame([
        {"sample_id": row["sample_id"], "sha256": row["sha256"]}
        for row in export["samples"]
    ])
    split_bytes = training_ids_path.read_bytes()
    training = json.loads(split_bytes)
    if (not isinstance(training, list) or not training
        or any(type(value) is not int or value <= 0 for value in training)):
        raise ValueError("Training IDs must be a nonempty array of positive integers")
    if len(set(training)) != len(training) or not set(training) < set(samples["sample_id"]):
        raise ValueError("A duplicate-free frozen split with a held-out partition is required")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
        frame = v2.build_v2_unresolved_features(
            samples, export_path, training_sample_ids=training, min_support=2)
    v2.assert_verified_v2_frame(
        frame, samples=samples, training_sample_ids=training, min_support=2)
    flags = {"enable_permission_features": True, "permission_input_policy": "required",
             "permission_feature_contract_version": v2.CONTRACT_VERSION}
    decision = evaluate_permission_run_validity(
        flags, available=True, degraded=False,
        evidence_status=permission_frame_status(frame, degraded=False))
    assert_training_permission_validity(decision)
    return {
        "status": "APPROVED_V2_FEATURE_CONSUMPTION_PASS",
        "samples": len(samples), "training_samples": len(training),
        "held_out_samples": len(samples) - len(training),
        "occurrence_features": sum(str(c).startswith("perm_provider_unresolved__") for c in frame),
        "projected_pairs": int(frame["perm_status__provider_reported_unresolved_count"].sum()),
        "manifest_verified_samples": int(frame["perm_status__manifest_verified"].sum()),
        "evidence_state": "PROVIDER_REPORTED_UNRESOLVED", "decision": decision,
        "export_sha256": frame.attrs["permission_v2_export_sha256"],
        "split_sha256": hashlib.sha256(split_bytes).hexdigest(),
        "model_training_executed": False, "production_writes": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "features"))
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--training-ids", type=Path)
    args = parser.parse_args(argv)
    if (args.action == "features") != (args.training_ids is not None):
        parser.error("--training-ids is required only for features")
    try:
        result = (inspect_export(args.export) if args.action == "inspect"
                  else check_features(args.export, args.training_ids))
    except (ValueError, TypeError, OSError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": "PI_V2_CONSUMPTION_REFUSED", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
