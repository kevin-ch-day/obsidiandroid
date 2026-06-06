#!/usr/bin/env python3
"""Wait for a canonical V3 run slot to finalize, then validate (and optionally refresh handoff)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from obsidiandroid.common.run_slots import CANONICAL_V3_PROFILES, _SLOT_BY_PROFILE  # noqa: E402


def _default_runs_root() -> Path:
    from config import app_config  # noqa: E402

    return Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output") or "output")) / "runs"


def _slot_root(*, runs_root: Path, profile_id: str) -> Path:
    return runs_root / _SLOT_BY_PROFILE[profile_id]


def wait_for_manifest(*, slot_root: Path, poll_sec: float, timeout_sec: float) -> Path | None:
    manifest_path = slot_root / "run_manifest.json"
    running_marker = slot_root / ".RUNNING"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if manifest_path.is_file():
            return manifest_path
        if not running_marker.is_file():
            return manifest_path if manifest_path.is_file() else None
        time.sleep(poll_sec)
    return manifest_path if manifest_path.is_file() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-id",
        choices=list(CANONICAL_V3_PROFILES),
        default="android_malware_major_families",
    )
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument("--poll-sec", type=float, default=15.0)
    parser.add_argument("--timeout-sec", type=float, default=7200.0)
    parser.add_argument(
        "--refresh-handoff",
        action="store_true",
        help="Run refresh-v3-handoff for the slot after manifest appears.",
    )
    parser.add_argument(
        "--validate-all",
        action="store_true",
        help="Validate all present canonical slots (strict, skip missing).",
    )
    args = parser.parse_args()

    runs_root = args.runs_root or _default_runs_root()
    slot_root = _slot_root(runs_root=runs_root, profile_id=args.profile_id)
    manifest_path = wait_for_manifest(
        slot_root=slot_root,
        poll_sec=float(args.poll_sec),
        timeout_sec=float(args.timeout_sec),
    )
    if manifest_path is None or not manifest_path.is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "profile_id": args.profile_id,
                    "run_slot": _SLOT_BY_PROFILE[args.profile_id],
                    "error": "timed out waiting for run_manifest.json",
                },
                indent=2,
            )
        )
        return 1

    if args.refresh_handoff:
        from scripts.dev import refresh_v3_canonical_handoff  # noqa: E402

        refresh_v3_canonical_handoff.refresh_slot(
            runs_root=runs_root,
            profile_id=args.profile_id,
        )

    from scripts.dev import validate_v3_canonical_runs as v3_validate  # noqa: E402

    if args.validate_all:
        code = v3_validate.verify_only_cli(
            runs_root=runs_root,
            strict=True,
            skip_missing_slots=True,
        )
    else:
        result = v3_validate._verify_slot_profile(
            profile_id=args.profile_id,
            runs_root=runs_root,
            strict=True,
        )
        print(json.dumps({"validated": result}, indent=2))
        code = 0 if bool(result.get("ok")) else 1
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
