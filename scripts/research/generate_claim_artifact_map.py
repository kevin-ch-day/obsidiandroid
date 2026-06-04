"""Generate claim-artifact scaffold from run path manifests."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime  # noqa: E402

prepare_script_runtime(__file__)

from config import app_config
from obsidiandroid.cli.menu import run_locator as rl


def _resolve_run_root(*, output_root: Path, run_id: str) -> Path:
    """Resolve and validate canonical run root under the configured output root."""
    root = output_root.resolve()
    manifest_payload, manifest_path = rl.resolve_manifest_for_run_id(
        str(run_id).strip(),
        runs_dir=root / "runs",
    )
    if not manifest_payload:
        raise FileNotFoundError(f"Run manifest not found for run_id: {run_id}")
    run_root = rl.resolve_run_root_for_manifest(
        manifest_payload,
        run_id=str(run_id).strip(),
        manifest_path=manifest_path,
    ).resolve()
    if root not in run_root.parents:
        raise ValueError(f"Run root escapes output_root: run_root={run_root} output_root={root}")
    return run_root


def _load_run_manifest(run_id: str, *, output_root: Path) -> dict:
    run_root = _resolve_run_root(output_root=output_root, run_id=run_id)
    path = run_root / "diagnostics" / f"run_paths_manifest_{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing run paths manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(run_ids: list[str], *, output_root: Path | None = None) -> list[dict[str, str]]:
    root = (
        Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
        if output_root is None
        else Path(output_root)
    )
    rows: list[dict[str, str]] = []
    claim_index = 1
    for run_id in run_ids:
        payload = _load_run_manifest(run_id, output_root=root)
        artifacts = payload.get("artifacts", {})
        roots = payload.get("roots", {})
        run_root = str(roots.get("run_root", "")).strip()
        for artifact_key, entry in sorted(artifacts.items()):
            relpath = str(entry.get("relpath", ""))
            artifact_path = str((Path(run_root) / relpath).resolve()) if run_root and relpath else relpath
            rows.append(
                {
                    "claim_id": f"C{claim_index:03d}",
                    "claim_text": "",
                    "run_id": run_id,
                    "artifact_key": artifact_key,
                    "artifact_path": artifact_path,
                    "artifact_sha256": str(entry.get("sha256", "")),
                    "status": "draft",
                    "owner": "PM",
                }
            )
            claim_index += 1
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate claim_artifact_map.csv scaffold")
    parser.add_argument("--run-ids", required=True, help="Comma-separated run IDs")
    parser.add_argument(
        "--output-root",
        default=str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")),
        help="Output root containing runs/ (default: DEFAULT_OUTPUT_DIR).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV output path",
    )
    args = parser.parse_args()

    run_ids = [token.strip() for token in str(args.run_ids).split(",") if token.strip()]
    if not run_ids:
        raise SystemExit("No run IDs provided.")

    output_root = Path(str(args.output_root))
    rows = build_rows(run_ids, output_root=output_root)
    out_path = (
        Path(str(args.output))
        if args.output
        else output_root / "diagnostics" / "claim_artifact_map.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "claim_id",
        "claim_text",
        "run_id",
        "artifact_key",
        "artifact_path",
        "artifact_sha256",
        "status",
        "owner",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote: {out_path} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
