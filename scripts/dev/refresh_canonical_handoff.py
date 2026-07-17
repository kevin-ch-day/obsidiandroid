#!/usr/bin/env python3
"""Refresh ML seed handoff artifacts on canonical run slots."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from obsidiandroid.common.run_slots import CANONICAL_PROFILES, _SLOT_BY_PROFILE  # noqa: E402
from obsidiandroid.diagnostics import ml_seed_exports  # noqa: E402
from obsidiandroid.common.json_io import read_json_dict  # noqa: E402
from obsidiandroid.diagnostics.dl_handoff import (  # noqa: E402
    build_dl_handoff_observability_block,
    export_dl_handoff_summary,
)
from obsidiandroid.reporting.operator_surface_refresh import (  # noqa: E402
    refresh_operator_surfaces_from_disk,
)


def _default_runs_root() -> Path:
    from config import app_config  # noqa: E402

    output_root = str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output") or "output").strip()
    return Path(output_root) / "runs"


def refresh_slot(*, runs_root: Path, profile_id: str) -> dict[str, object]:
    slot = _SLOT_BY_PROFILE[profile_id]
    slot_root = runs_root / slot
    manifest_path = slot_root / "run_manifest.json"
    if not manifest_path.is_file():
        return {"profile_id": profile_id, "ok": False, "error": f"missing {manifest_path}"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", "") or "").strip()
    if not run_id:
        return {"profile_id": profile_id, "ok": False, "error": "run_manifest missing run_id"}
    diagnostics_dir = slot_root / "diagnostics"
    vocab_path = ml_seed_exports.refresh_persisted_permission_vocabulary(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    )
    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    synced = ml_seed_exports.sync_ml_run_manifest_seed_counters(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    )
    ml_seed_exports.ensure_ml_split_export(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        manifest=manifest,
    )
    ml_manifest = json.loads(synced.read_text(encoding="utf-8")) if synced is not None else {}
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_payload = read_json_dict(obs_path) if obs_path.is_file() else {}
    handoff_context = {
        "cohort_persistence_source": obs_payload.get("cohort_persistence_source")
        or manifest.get("cohort_persistence_source"),
        "dataset_hash": manifest.get("dataset_hash") or obs_payload.get("dataset_hash"),
    }
    handoff_path = export_dl_handoff_summary(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile={"profile_id": profile_id},
        manifest=manifest,
        manifest_context=handoff_context,
    )
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    observability_backfilled = False
    if obs_path.is_file():
        handoff_block = build_dl_handoff_observability_block(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest=manifest,
            manifest_context=handoff_context,
        )
        obs_payload["dataset_hash"] = handoff_block.get("dataset_hash")
        obs_payload["cohort_persistence_source"] = handoff_block.get("cohort_persistence_source")
        obs_payload["dl_handoff"] = handoff_block
        obs_path.write_text(json.dumps(obs_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        observability_backfilled = True

    operator_refresh = refresh_operator_surfaces_from_disk(
        run_root=slot_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id=profile_id,
        manifest=manifest,
    )
    return {
        "profile_id": profile_id,
        "run_slot": slot,
        "run_id": run_id,
        "vocabulary_entry_count": vocab.get("entry_count"),
        "dataset_hash": ml_manifest.get("dataset_hash"),
        "dl_seed_status": handoff.get("dl_seed_status"),
        "observability_backfilled": observability_backfilled,
        "operator_surfaces_refreshed": bool(operator_refresh.get("ok")),
        "supervised_family_claims_suitable": operator_refresh.get("supervised_family_claims_suitable"),
        "claim_status": operator_refresh.get("claim_status"),
        "claim_surface": operator_refresh.get("claim_surface"),
        "publication_ready": operator_refresh.get("publication_ready"),
        "operator_refresh_error": operator_refresh.get("error"),
        "ok": True,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="Runs root (default: <DEFAULT_OUTPUT_DIR>/runs).",
    )
    parser.add_argument(
        "--skip-missing-slots",
        action="store_true",
        help="Skip canonical slots without run_manifest.json instead of failing.",
    )
    args = parser.parse_args()
    runs_root = args.runs_root or _default_runs_root()
    results: list[dict[str, object]] = []
    for profile_id in CANONICAL_PROFILES:
        row = refresh_slot(runs_root=runs_root, profile_id=profile_id)
        if args.skip_missing_slots and not row.get("ok") and str(row.get("error", "")).startswith("missing"):
            results.append({**row, "ok": True, "skipped": True, "skip_reason": row.get("error")})
            continue
        results.append(row)
    print(json.dumps({"refreshed": results}, indent=2))
    evaluated = [row for row in results if not row.get("skipped")]
    return 0 if evaluated and all(bool(row.get("ok")) for row in evaluated) else (0 if not evaluated else 1)


if __name__ == "__main__":
    raise SystemExit(main())
