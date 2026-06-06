#!/usr/bin/env python3
"""Backfill v3_dl_handoff fields on existing canonical run observability summaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from obsidiandroid.common.run_slots import CANONICAL_V3_PROFILES, _SLOT_BY_PROFILE  # noqa: E402
from obsidiandroid.common.json_io import read_json_dict  # noqa: E402
from obsidiandroid.diagnostics.v3_dl_handoff import build_v3_dl_handoff_observability_block  # noqa: E402


def _default_runs_root() -> Path:
    from config import app_config  # noqa: E402

    return Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output") or "output")) / "runs"


def backfill_slot(*, runs_root: Path, profile_id: str) -> dict[str, object]:
    slot_root = runs_root / _SLOT_BY_PROFILE[profile_id]
    manifest_path = slot_root / "run_manifest.json"
    if not manifest_path.is_file():
        return {"profile_id": profile_id, "ok": False, "error": f"missing {manifest_path}"}
    manifest = read_json_dict(manifest_path)
    run_id = str(manifest.get("run_id", "") or "").strip()
    diagnostics_dir = slot_root / "diagnostics"
    obs_path = diagnostics_dir / "run_observability_summary.json"
    if not obs_path.is_file():
        return {"profile_id": profile_id, "ok": False, "error": "missing run_observability_summary.json"}
    payload = read_json_dict(obs_path)
    handoff_block = build_v3_dl_handoff_observability_block(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        manifest=manifest,
        manifest_context={
            "cohort_persistence_source": payload.get("cohort_persistence_source"),
            "dataset_hash": payload.get("dataset_hash"),
        },
    )
    payload["dataset_hash"] = handoff_block.get("dataset_hash")
    payload["cohort_persistence_source"] = handoff_block.get("cohort_persistence_source")
    payload["v3_dl_handoff"] = handoff_block
    obs_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "profile_id": profile_id,
        "run_id": run_id,
        "dl_seed_status": handoff_block.get("dl_seed_status"),
        "ok": True,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument(
        "--skip-missing-slots",
        action="store_true",
        help="Skip canonical slots without run_manifest.json instead of failing.",
    )
    args = parser.parse_args()
    runs_root = args.runs_root or _default_runs_root()
    results: list[dict[str, object]] = []
    for profile_id in CANONICAL_V3_PROFILES:
        row = backfill_slot(runs_root=runs_root, profile_id=profile_id)
        if args.skip_missing_slots and not row.get("ok") and str(row.get("error", "")).startswith("missing"):
            results.append({**row, "ok": True, "skipped": True, "skip_reason": row.get("error")})
            continue
        results.append(row)
    print(json.dumps({"backfilled": results}, indent=2))
    evaluated = [row for row in results if not row.get("skipped")]
    return 0 if evaluated and all(bool(row.get("ok")) for row in evaluated) else (0 if not evaluated else 1)


if __name__ == "__main__":
    raise SystemExit(main())
