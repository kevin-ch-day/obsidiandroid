#!/usr/bin/env python3
"""Compare run_manifest / run_summary against run_observability_summary.json (Tier A QA).

Exits non-zero when identifiers or headline counts disagree beyond optional tolerances.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Failed to read JSON {path}: {exc}") from exc


def _as_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _close(a: float | None, b: float | None, *, tol: float) -> bool:
    if a is None or b is None:
        return True
    return abs(a - b) <= tol


def resolve_default_paths(run_root: Path) -> tuple[Path, Path | None, Path]:
    run_root = Path(run_root).resolve()
    manifest_path = run_root / "run_manifest.json"
    summary_path = run_root / "run_summary.json"
    obs_path = run_root / "diagnostics" / "run_observability_summary.json"
    return manifest_path, summary_path if summary_path.exists() else None, obs_path


def compare_run_artifacts(
    *,
    manifest: dict[str, Any],
    summary: dict[str, Any] | None,
    observability: dict[str, Any],
    f1_tolerance: float,
) -> list[str]:
    """Return human-readable discrepancy lines (empty = OK)."""
    issues: list[str] = []
    counts = observability.get("counts")
    oc = counts if isinstance(counts, dict) else {}

    rid_m = str(manifest.get("run_id", "") or "")
    rid_o = str(observability.get("run_id", "") or "")
    if rid_m and rid_o and rid_m != rid_o:
        issues.append(f"run_id mismatch: manifest={rid_m!r} observability={rid_o!r}")

    pf_m = str((manifest.get("profile_params") or {}).get("profile_id", "") or "")
    pf_o = str(observability.get("profile_id", "") or "").strip()
    if pf_m and pf_o and pf_m != pf_o:
        issues.append(f"profile_id mismatch: manifest={pf_m!r} observability={pf_o!r}")

    co_m = _as_int(manifest.get("cohort_size"))
    co_o = (
        _as_int(oc.get("cohort_prepared_row_count"))
        or _as_int(observability.get("cohort_prepared_row_count"))
        or _as_int(oc.get("governed_cohort_rows"))
        or _as_int(observability.get("governed_cohort_rows"))
    )
    if co_m is not None and co_o is not None and co_m != co_o:
        issues.append(
            f"cohort_size mismatch: manifest={co_m} observability_counts.cohort_prepared_row_count="
            f"{co_o} (legacy governed_cohort_rows also checked)"
        )

    split_m = manifest.get("split") if isinstance(manifest.get("split"), dict) else {}
    tr_m = _as_int(manifest.get("train_sample_count"))
    if tr_m is None:
        tr_m = _as_int(split_m.get("train_sample_count"))
    te_m = _as_int(manifest.get("test_sample_count"))
    if te_m is None:
        te_m = _as_int(split_m.get("test_sample_count"))

    tr_o = _as_int(oc.get("train_rows")) or _as_int(observability.get("train_sample_count"))
    te_o = _as_int(oc.get("test_rows")) or _as_int(observability.get("test_sample_count"))

    if tr_m is not None and tr_o is not None and tr_m != tr_o:
        issues.append(f"train_sample_count mismatch: manifest={tr_m} observability={tr_o}")
    if te_m is not None and te_o is not None and te_m != te_o:
        issues.append(f"test_sample_count mismatch: manifest={te_m} observability={te_o}")

    if summary:
        rs_tr = _as_int(summary.get("train_sample_count"))
        rs_te = _as_int(summary.get("test_sample_count"))
        rs_co = _as_int(summary.get("cohort_size"))
        if rs_co is not None and co_m is not None and rs_co != co_m:
            issues.append(f"cohort_size drift: manifest={co_m} run_summary={rs_co}")
        if rs_tr is not None and tr_o is not None and rs_tr != tr_o:
            issues.append(f"train_sample_count drift: run_summary={rs_tr} observability={tr_o}")
        if rs_te is not None and te_o is not None and rs_te != te_o:
            issues.append(f"test_sample_count drift: run_summary={rs_te} observability={te_o}")

        msm = observability.get("model_summary") if isinstance(observability.get("model_summary"), dict) else {}
        mod_inner = observability.get("model") if isinstance(observability.get("model"), dict) else {}
        tm_s = str(summary.get("top_model") or "").strip()
        tm_o = str(msm.get("top_model") or mod_inner.get("top_model") or "").strip()
        if tm_s and tm_o and tm_s != tm_o:
            issues.append(f"top_model mismatch: run_summary={tm_s!r} observability={tm_o!r}")

        f1_s = _as_float(summary.get("top_macro_f1"))
        f1_o = _as_float(msm.get("top_macro_f1")) or _as_float(mod_inner.get("top_macro_f1"))
        if not _close(f1_s, f1_o, tol=f1_tolerance):
            issues.append(f"top_macro_f1 mismatch: run_summary={f1_s} observability={f1_o} (tol={f1_tolerance})")

        ps_s = str(summary.get("paper_safe_status") or "").strip()
        ps_o = str(observability.get("paper_safe_status") or "").strip()
        if ps_s and ps_o and ps_s != ps_o:
            issues.append(f"paper_safe_status mismatch: run_summary={ps_s!r} observability={ps_o!r}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-root",
        default="",
        help="Run directory containing run_manifest.json and diagnostics/",
    )
    parser.add_argument("--manifest", default="", help="Explicit run_manifest.json path.")
    parser.add_argument("--run-summary", default="", help="Explicit run_summary.json path.")
    parser.add_argument(
        "--observability",
        default="",
        help="Explicit run_observability_summary.json path.",
    )
    parser.add_argument(
        "--f1-tolerance",
        type=float,
        default=5e-3,
        help="Allowed absolute drift for Macro-F1 cross-check (JSON rounding).",
    )
    parser.add_argument("--json", action="store_true", help="Emit discrepancies as JSON array on stdout.")
    args = parser.parse_args()

    if args.manifest and args.observability:
        m_path = Path(args.manifest).resolve()
        o_path = Path(args.observability).resolve()
        s_path = Path(args.run_summary).resolve() if args.run_summary else None
    elif args.run_root:
        m_path, s_maybe, o_path = resolve_default_paths(Path(args.run_root))
        s_path = Path(args.run_summary).resolve() if args.run_summary else s_maybe
    else:
        parser.error("Provide --run-root or both --manifest and --observability")

    if not m_path.exists():
        print(f"[integrity] Missing manifest: {m_path}", file=sys.stderr)
        return 2
    if not o_path.exists():
        print(f"[integrity] Missing observability summary: {o_path}", file=sys.stderr)
        return 2

    manifest_payload = _load_json(m_path)
    obs_payload = _load_json(o_path)
    summary_payload = _load_json(s_path) if s_path and s_path.exists() else None

    issues = compare_run_artifacts(
        manifest=manifest_payload,
        summary=summary_payload,
        observability=obs_payload,
        f1_tolerance=float(args.f1_tolerance),
    )
    if args.json:
        print(json.dumps({"ok": len(issues) == 0, "issues": issues}, indent=2))
    else:
        if not issues:
            print(f"[integrity] OK — {manifest_payload.get('run_id')} manifests align with observability summary.")
            return 0
        print("[integrity] MISMATCH:", file=sys.stderr)
        for line in issues:
            print(f"  - {line}", file=sys.stderr)
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
