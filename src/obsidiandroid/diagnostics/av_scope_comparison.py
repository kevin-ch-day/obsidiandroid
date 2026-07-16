"""Validate and summarize a paired AV binary-feature scope experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _single_run_artifact(diagnostics_dir: Path, pattern: str) -> Path | None:
    matches = sorted(diagnostics_dir.glob(pattern))
    return matches[-1] if matches else None


def load_av_scope_run(run_root: str | Path) -> dict[str, Any]:
    """Load only the run-scoped provenance needed for an AV-scope comparison."""
    root = Path(run_root)
    diagnostics = root / "diagnostics"
    run_manifest = _read_json(root / "run_manifest.json")
    run_id = str(run_manifest.get("run_id", "") or "").strip()
    feature_path = _single_run_artifact(diagnostics, "feature_contract_*.json")
    ml_path = _single_run_artifact(diagnostics, "ml_run_manifest_*.json")
    model_path = _single_run_artifact(diagnostics, "model_comparison_summary_*.csv")
    feature_contract = _read_json(feature_path) if feature_path else {}
    ml_manifest = _read_json(ml_path) if ml_path else {}
    if not run_id:
        run_id = str(feature_contract.get("run_id", "") or ml_manifest.get("run_id", "")).strip()
    model_rows = pd.read_csv(model_path) if model_path and model_path.is_file() else pd.DataFrame()
    return {
        "run_root": str(root.resolve()),
        "diagnostics_dir": str(diagnostics.resolve()),
        "run_id": run_id,
        "profile_id": str(
            feature_contract.get("profile_id", "")
            or ml_manifest.get("profile_id", "")
            or run_manifest.get("profile_id", "")
        ),
        "model_config_hash": str(run_manifest.get("model_config_hash", "") or ""),
        "feature_contract": feature_contract,
        "ml_manifest": ml_manifest,
        "model_rows": model_rows,
        "paths": {
            "feature_contract": str(feature_path) if feature_path else "",
            "ml_run_manifest": str(ml_path) if ml_path else "",
            "model_comparison": str(model_path) if model_path else "",
        },
    }


def _comparison_checks(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Build all mandatory compatibility checks; no score is interpreted before these pass."""
    b_feature = baseline.get("feature_contract", {})
    c_feature = candidate.get("feature_contract", {})
    b_ml = baseline.get("ml_manifest", {})
    c_ml = candidate.get("ml_manifest", {})
    checks = [
        ("baseline_scope", b_feature.get("binary_feature_engine_scope") == "all_observed", b_feature.get("binary_feature_engine_scope", "missing")),
        ("candidate_scope", c_feature.get("binary_feature_engine_scope") == "lifecycle_included", c_feature.get("binary_feature_engine_scope", "missing")),
        ("dataset_hash", bool(b_ml.get("dataset_hash")) and b_ml.get("dataset_hash") == c_ml.get("dataset_hash"), f"{b_ml.get('dataset_hash', '')} | {c_ml.get('dataset_hash', '')}"),
        ("split_hash", bool(b_ml.get("split_hash")) and b_ml.get("split_hash") == c_ml.get("split_hash"), f"{b_ml.get('split_hash', '')} | {c_ml.get('split_hash', '')}"),
        ("training_label_field", b_ml.get("training_label_field") == c_ml.get("training_label_field"), f"{b_ml.get('training_label_field', '')} | {c_ml.get('training_label_field', '')}"),
        (
            "model_config_hash",
            bool(baseline.get("model_config_hash"))
            and baseline.get("model_config_hash") == candidate.get("model_config_hash"),
            f"{baseline.get('model_config_hash', '')} | {candidate.get('model_config_hash', '')}",
        ),
        ("label_independent_contract", b_feature.get("classification_surface") == "label_independent" and c_feature.get("classification_surface") == "label_independent" and int(b_feature.get("direct_target_proxies", -1)) == 0 and int(c_feature.get("direct_target_proxies", -1)) == 0, f"{b_feature.get('classification_surface', '')} | {c_feature.get('classification_surface', '')}"),
    ]
    return [{"check": name, "passed": bool(passed), "detail": str(detail)} for name, passed, detail in checks]


def build_av_scope_comparison(baseline: dict[str, Any], candidate: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return compatibility checks and per-model deltas for two completed runs."""
    checks = _comparison_checks(baseline, candidate)
    b_rows = baseline.get("model_rows")
    c_rows = candidate.get("model_rows")
    if not isinstance(b_rows, pd.DataFrame) or not isinstance(c_rows, pd.DataFrame):
        return pd.DataFrame(checks), pd.DataFrame()
    required = {"Model", "Macro F1-Score", "split_hash", "train_sample_hash", "test_sample_hash", "evaluation_label_hash"}
    if not required.issubset(b_rows.columns) or not required.issubset(c_rows.columns):
        checks.append({"check": "model_comparison_columns", "passed": False, "detail": "missing required model-comparison columns"})
        return pd.DataFrame(checks), pd.DataFrame()
    b = b_rows.loc[:, sorted(required)].rename(columns={column: f"baseline_{column}" for column in required})
    c = c_rows.loc[:, sorted(required)].rename(columns={column: f"candidate_{column}" for column in required})
    merged = b.merge(c, left_on="baseline_Model", right_on="candidate_Model", how="outer", validate="one_to_one")
    for field in ("split_hash", "train_sample_hash", "test_sample_hash", "evaluation_label_hash"):
        equal = merged[f"baseline_{field}"].eq(merged[f"candidate_{field}"])
        checks.append({"check": f"model_{field}", "passed": bool(equal.all()), "detail": "per-model equality"})
    merged["macro_f1_delta_candidate_minus_baseline"] = (
        pd.to_numeric(merged["candidate_Macro F1-Score"], errors="coerce")
        - pd.to_numeric(merged["baseline_Macro F1-Score"], errors="coerce")
    )
    return pd.DataFrame(checks), merged


def render_comparison_markdown(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    checks: pd.DataFrame,
    deltas: pd.DataFrame,
) -> str:
    """Render a concise, no-guesswork AV-scope comparison report."""
    comparable = bool(not checks.empty and checks["passed"].astype(bool).all())
    lines = [
        "# AV binary-feature scope comparison",
        "",
        f"- baseline: `{baseline.get('run_id', '')}` | scope=`{baseline.get('feature_contract', {}).get('binary_feature_engine_scope', 'missing')}`",
        f"- candidate: `{candidate.get('run_id', '')}` | scope=`{candidate.get('feature_contract', {}).get('binary_feature_engine_scope', 'missing')}`",
        f"- status: `{'COMPARABLE' if comparable else 'NOT_COMPARABLE'}`",
        "",
        "## Required compatibility checks",
        "",
    ]
    for row in checks.to_dict(orient="records"):
        state = "PASS" if bool(row.get("passed")) else "FAIL"
        lines.append(f"- {state}: `{row.get('check', '')}` — {row.get('detail', '')}")
    if comparable and not deltas.empty:
        lines.extend(["", "## Macro-F1 deltas", ""])
        for row in deltas.sort_values("baseline_Model").to_dict(orient="records"):
            lines.append(
                f"- `{row.get('baseline_Model', '')}`: "
                f"baseline={float(row.get('baseline_Macro F1-Score')):.4f}; "
                f"candidate={float(row.get('candidate_Macro F1-Score')):.4f}; "
                f"delta={float(row.get('macro_f1_delta_candidate_minus_baseline')):+.4f}"
            )
    else:
        lines.extend(["", "No performance interpretation is permitted until every compatibility check passes."])
    return "\n".join(lines) + "\n"
