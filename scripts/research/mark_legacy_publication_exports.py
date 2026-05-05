"""Mark legacy runs that contain non-authoritative partial publication exports.

This utility scans ``output/runs/*`` and marks runs whose ``paper_exports``
folder exists but fails the strict evidence-bundle checks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from utils.repo_import_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from scripts.research import check_evidence_bundle


MARKER_FILE = "publication_exports.INVALID_PRE_STRICT.txt"


def mark_legacy_runs(*, output_root: Path) -> list[dict[str, str]]:
    """Mark runs with invalid partial publication exports.

    Args:
        output_root: Root output directory containing run folders.

    Returns:
        List of run results with status.
    """
    root = output_root.resolve()
    runs_root = root / "runs"
    if not runs_root.exists():
        return []
    rows: list[dict[str, str]] = []
    for run_dir in sorted([p for p in runs_root.iterdir() if p.is_dir()]):
        run_id = run_dir.name
        paper_dir = run_dir / "paper_exports"
        marker_path = paper_dir / MARKER_FILE
        if not paper_dir.exists():
            rows.append({"run_id": run_id, "status": "no_publication_exports", "marker": ""})
            continue
        try:
            report = check_evidence_bundle.check_run(run_id, output_root=root)
        except TypeError:
            # Backward compatibility for patched/mocked legacy signature.
            report = check_evidence_bundle.check_run(run_id)
        if bool(report.get("passed", False)):
            if marker_path.exists():
                marker_path.unlink(missing_ok=True)
            rows.append({"run_id": run_id, "status": "valid_publication_exports", "marker": ""})
            continue
        marker_payload = (
            "This run contains non-authoritative or partial publication exports.\n"
            "Do not use these exports as canonical evidence artifacts.\n"
            f"run_id={run_id}\n"
        )
        marker_path.write_text(marker_payload, encoding="utf-8")
        rows.append({"run_id": run_id, "status": "marked_invalid_partial", "marker": str(marker_path)})
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark legacy partial publication exports.")
    parser.add_argument(
        "--output-root",
        default="output",
        help="Output root containing runs/ (default: output).",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    rows = mark_legacy_runs(output_root=Path(str(args.output_root)))
    for row in rows:
        marker = f" marker={row['marker']}" if row["marker"] else ""
        print(f"{row['run_id']}: {row['status']}{marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
