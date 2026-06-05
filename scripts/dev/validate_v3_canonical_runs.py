#!/usr/bin/env python3
"""Validate V3 closure artifacts for the four canonical profiles."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config import app_config  # noqa: E402
import main  # noqa: E402

CANONICAL_PROFILES = (
    "android_malware_major_families",
    "android_malware_type_taxonomy",
    "android_malware_expanded_families",
    "android_malware_all_current",
)

REQUIRED_ARTIFACTS = (
    "v3_label_contract",
    "permission_pattern_contract",
    "ml_run_manifest",
    "ml_sample_label_fact",
    "run_observability_summary.json",
    "run_manifest.json",
)


def _diagnostics_dir() -> Path:
    token = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if token:
        return Path(token)
    run_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if run_root:
        return Path(run_root) / "diagnostics"
    return Path("output/diagnostics")


def _verify_run(profile_id: str, run_id: str) -> dict[str, object]:
    diag = _diagnostics_dir()
    missing: list[str] = []
    present: list[str] = []
    for stem in REQUIRED_ARTIFACTS:
        if stem.endswith(".json"):
            candidates = [diag / stem, diag / f"{stem.replace('.json', '')}_{run_id}.json"]
        else:
            candidates = [
                diag / f"{stem}_{run_id}.json",
                diag / f"{stem}_{run_id}.md",
                diag / f"{stem}_{run_id}.csv",
            ]
        if any(path.is_file() for path in candidates):
            present.append(stem)
        else:
            missing.append(stem)

    label_contract = diag / f"v3_label_contract_{run_id}.json"
    payload = {}
    if label_contract.is_file():
        payload = json.loads(label_contract.read_text(encoding="utf-8"))
    return {
        "profile_id": profile_id,
        "run_id": run_id,
        "present": present,
        "missing": missing,
        "profile_role": payload.get("profile_role"),
        "target_label_namespace": payload.get("target_label_namespace"),
        "claim_surface_label": payload.get("claim_surface_label"),
        "ok": not missing and bool(payload.get("profile_role")),
    }


def main_cli() -> int:
    results: list[dict[str, object]] = []
    for profile_id in CANONICAL_PROFILES:
        print(f"[V3] Running profile={profile_id} …", flush=True)
        code = main.run_pipeline(
            profile_ref=profile_id,
            selected_models=["logistic_regression"],
        )
        run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
        summary = _verify_run(profile_id, run_id)
        summary["exit_code"] = int(code)
        results.append(summary)
        print(json.dumps(summary, indent=2), flush=True)
        if int(code) != 0:
            print(f"[V3] profile={profile_id} exit_code={code}", file=sys.stderr)

    all_ok = all(bool(row.get("ok")) and int(row.get("exit_code", 1)) == 0 for row in results)
    print(json.dumps({"tag_validation": "PASS" if all_ok else "FAIL", "profiles": results}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
