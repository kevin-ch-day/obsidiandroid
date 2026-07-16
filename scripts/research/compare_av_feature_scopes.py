"""Compare two completed AV binary-feature scope runs without re-running data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.diagnostics.av_scope_comparison import (
    build_av_scope_comparison,
    load_av_scope_run,
    render_comparison_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate paired AV binary-feature scope runs.")
    parser.add_argument("--baseline-run-root", required=True, help="Run root using all_observed scope.")
    parser.add_argument("--candidate-run-root", required=True, help="Run root using lifecycle_included scope.")
    parser.add_argument("--output-dir", required=True, help="Directory for derived comparison CSV/Markdown.")
    args = parser.parse_args()

    baseline = load_av_scope_run(args.baseline_run_root)
    candidate = load_av_scope_run(args.candidate_run_root)
    checks, deltas = build_av_scope_comparison(baseline, candidate)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checks.to_csv(output_dir / "av_scope_comparison_checks.csv", index=False)
    deltas.to_csv(output_dir / "av_scope_comparison_model_deltas.csv", index=False)
    report = render_comparison_markdown(
        baseline=baseline,
        candidate=candidate,
        checks=checks,
        deltas=deltas,
    )
    report_path = output_dir / "av_scope_comparison.md"
    report_path.write_text(report, encoding="utf-8")
    comparable = bool(not checks.empty and checks["passed"].astype(bool).all())
    print(f"Wrote: {report_path}")
    return 0 if comparable else 2


if __name__ == "__main__":
    raise SystemExit(main())
