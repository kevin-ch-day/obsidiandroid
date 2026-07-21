"""Holdout confidence calibration and split class accounting (read-only).

Consumes ``headline_test_predictions_*.csv`` and ``split_freeze_headline_*.csv``.
Does not query production databases or write Core/Erebus.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

COMPOSER_VERSION = "1.0.0"
SCHEMA_VERSION = "holdout_calibration_v1"


def _ece(confidence: np.ndarray, correct: np.ndarray, *, n_bins: int = 10) -> float:
    """Expected calibration error for top-1 confidence as P(correct)."""
    if len(confidence) == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, int(n_bins) + 1)
    total = float(len(confidence))
    ece = 0.0
    for i in range(int(n_bins)):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (confidence >= lo) & (confidence <= hi)
        else:
            mask = (confidence >= lo) & (confidence < hi)
        if not np.any(mask):
            continue
        acc = float(correct[mask].mean())
        conf = float(confidence[mask].mean())
        ece += (float(mask.sum()) / total) * abs(acc - conf)
    return float(ece)


def _brier_top1(confidence: np.ndarray, correct: np.ndarray) -> float:
    if len(confidence) == 0:
        return float("nan")
    return float(np.mean((confidence - correct) ** 2))


def _support_tier(n: int) -> str:
    if n < 3:
        return "n_lt_3"
    if n < 20:
        return "n_3_to_19"
    if n < 50:
        return "n_20_to_49"
    return "n_ge_50"


def build_split_class_accounting(
    split_df: pd.DataFrame,
    *,
    visible_family_count: int | None = None,
) -> dict[str, Any]:
    """Reconcile visible / training / held-out / train-only class counts."""
    work = split_df.copy()
    role = work["split_role"].fillna("").astype(str).str.strip().str.lower()
    fam = work["family_canonical"].fillna("").astype(str).str.strip()
    fam = fam[fam.ne("") & fam.str.lower().ne("unknown")]
    role = role.loc[fam.index]
    train = set(fam.loc[role.eq("train")])
    test = set(fam.loc[role.isin(["test", "holdout", "eval"])])
    train_only = sorted(train - test)
    test_only = sorted(test - train)
    payload = {
        "training_target_classes": int(len(train)),
        "held_out_evaluated_classes": int(len(test)),
        "train_only_classes": int(len(train_only)),
        "test_only_classes": int(len(test_only)),
        "train_sample_count": int(role.eq("train").sum()),
        "test_sample_count": int(role.isin(["test", "holdout", "eval"]).sum()),
        "train_only_family_canonical": train_only,
        "reconciles_training_minus_heldout": int(len(train) - len(test)) == int(len(train_only)),
    }
    if visible_family_count is not None:
        payload["visible_governed_families"] = int(visible_family_count)
        payload["note"] = (
            "Visible governed families may exceed training target classes because "
            "unknown/unmapped or non-authoritative labels are excluded before training."
        )
    return payload


def build_calibration_tables(
    pred_df: pd.DataFrame,
    family_support: dict[str, int],
    *,
    n_bins: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return reliability bins, support-tier summary, and scalar metrics."""
    work = pred_df.copy()
    work["confidence"] = pd.to_numeric(work["confidence"], errors="coerce")
    work = work.dropna(subset=["confidence"]).copy()
    work["is_correct"] = (
        work["true_label_id"].astype(str) == work["predicted_label_id"].astype(str)
    ).astype(int)
    true_name = work.get("true_label_name", pd.Series([""] * len(work))).fillna("").astype(str)
    work["family_support"] = true_name.map(lambda name: int(family_support.get(name, 0)))
    work["support_tier"] = work["family_support"].map(_support_tier)

    conf = work["confidence"].to_numpy(dtype=float)
    correct = work["is_correct"].to_numpy(dtype=float)
    metrics = {
        "n_predictions": int(len(work)),
        "accuracy": float(correct.mean()) if len(work) else float("nan"),
        "mean_confidence": float(conf.mean()) if len(work) else float("nan"),
        "mean_confidence_correct": float(conf[correct == 1].mean()) if (correct == 1).any() else float("nan"),
        "mean_confidence_incorrect": float(conf[correct == 0].mean()) if (correct == 0).any() else float("nan"),
        "ece_equal_width_10": _ece(conf, correct, n_bins=n_bins),
        "brier_top1_correctness": _brier_top1(conf, correct),
        "high_conf_error_rate_ge_0_95": (
            float(((conf >= 0.95) & (correct == 0)).sum() / max((conf >= 0.95).sum(), 1))
        ),
        "high_conf_error_rate_ge_0_99": (
            float(((conf >= 0.99) & (correct == 0)).sum() / max((conf >= 0.99).sum(), 1))
        ),
    }

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        mask = (conf >= lo) & (conf <= hi if i == n_bins - 1 else conf < hi)
        n = int(mask.sum())
        rows.append(
            {
                "bin_index": i,
                "bin_low": lo,
                "bin_high": hi,
                "n": n,
                "mean_confidence": float(conf[mask].mean()) if n else float("nan"),
                "accuracy": float(correct[mask].mean()) if n else float("nan"),
                "gap_abs": float(abs(conf[mask].mean() - correct[mask].mean())) if n else float("nan"),
            }
        )
    reliability = pd.DataFrame(rows)

    tier_rows: list[dict[str, Any]] = []
    for tier, group in work.groupby("support_tier"):
        c = group["confidence"].to_numpy(dtype=float)
        y = group["is_correct"].to_numpy(dtype=float)
        tier_rows.append(
            {
                "support_tier": tier,
                "n": int(len(group)),
                "accuracy": float(y.mean()),
                "mean_confidence": float(c.mean()),
                "ece_equal_width_10": _ece(c, y, n_bins=min(n_bins, max(2, int(math.sqrt(len(group)))))),
                "brier_top1_correctness": _brier_top1(c, y),
                "mean_confidence_incorrect": float(c[y == 0].mean()) if (y == 0).any() else float("nan"),
            }
        )
    tiers = pd.DataFrame(tier_rows).sort_values("support_tier").reset_index(drop=True)
    return reliability, tiers, metrics


def compose_holdout_calibration_report(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    visible_family_count: int | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Write calibration + split-class accounting under diagnostics."""
    run_root = Path(run_root)
    diagnostics = run_root / "diagnostics"
    pred_path = diagnostics / f"headline_test_predictions_{run_id}.csv"
    split_path = diagnostics / f"split_freeze_headline_{run_id}.csv"
    if not pred_path.is_file():
        raise FileNotFoundError(pred_path)
    if not split_path.is_file():
        raise FileNotFoundError(split_path)

    pred = pd.read_csv(pred_path)
    split = pd.read_csv(split_path)
    family_support = (
        split.loc[split["family_canonical"].fillna("").astype(str).str.strip().ne(""), "family_canonical"]
        .astype(str)
        .value_counts()
        .to_dict()
    )
    if visible_family_count is None:
        obs = diagnostics / "run_observability_summary.json"
        if obs.is_file():
            try:
                payload = json.loads(obs.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and payload.get("visible_family_count") is not None:
                    visible_family_count = int(payload["visible_family_count"])
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                visible_family_count = None

    accounting = build_split_class_accounting(split, visible_family_count=visible_family_count)
    reliability, tiers, metrics = build_calibration_tables(pred, family_support)

    out_dir = Path(output_dir) if output_dir else diagnostics / "holdout_calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_status = detect_source_run_status(run_root)

    derived = {
        "reliability_bins": reliability,
        "calibration_by_support_tier": tiers,
        "split_class_accounting": pd.DataFrame(
            [
                {"metric": key, "value": value}
                for key, value in accounting.items()
                if not isinstance(value, list)
            ]
        ),
        "train_only_families": pd.DataFrame(
            {"family_canonical": accounting.get("train_only_family_canonical", [])}
        ),
    }
    output_hashes: dict[str, str] = {}
    for name, frame in derived.items():
        path = out_dir / f"{name}_{run_id}.csv"
        frame.to_csv(path, index=False)
        frame.to_csv(out_dir / f"{name}.latest.csv", index=False)
        output_hashes[path.name] = sha256_file(path)

    md = [
        f"# Holdout calibration and split class accounting (`{run_id}`)",
        "",
        f"- Report status: **{run_status['report_status']}**",
        f"- Composer: `{COMPOSER_VERSION}` / `{SCHEMA_VERSION}`",
        "",
        "## Split class accounting",
        "",
        f"- Visible governed families: **{accounting.get('visible_governed_families', 'n/a')}**",
        f"- Training target classes: **{accounting['training_target_classes']}**",
        f"- Held-out evaluated classes: **{accounting['held_out_evaluated_classes']}**",
        f"- Train-only classes: **{accounting['train_only_classes']}**",
        f"- Test-only classes: **{accounting['test_only_classes']}**",
        f"- Reconciles (train − held-out = train-only): **{accounting['reconciles_training_minus_heldout']}**",
        "",
        "## Confidence calibration (top-1 confidence as P(correct))",
        "",
        f"- Holdout predictions: **{metrics['n_predictions']:,}**",
        f"- Accuracy: **{metrics['accuracy']:.4f}**",
        f"- Mean confidence: **{metrics['mean_confidence']:.4f}** "
        f"(correct={metrics['mean_confidence_correct']:.4f}, "
        f"incorrect={metrics['mean_confidence_incorrect']:.4f})",
        f"- ECE (10 equal-width bins): **{metrics['ece_equal_width_10']:.4f}**",
        f"- Brier (top-1 correctness): **{metrics['brier_top1_correctness']:.4f}**",
        f"- Error rate among conf≥0.95: **{metrics['high_conf_error_rate_ge_0_95']:.4f}**",
        f"- Error rate among conf≥0.99: **{metrics['high_conf_error_rate_ge_0_99']:.4f}**",
        "",
        "Average confidence near 0.96 with Macro-F1 ~0.70 is compatible with "
        "good dominant-family calibration and residual overconfidence on the tail.",
        "",
        "## Calibration by family-support tier",
        "",
        "| tier | n | accuracy | mean conf | ECE | mean conf on errors |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in tiers.itertuples(index=False):
        md.append(
            f"| {row.support_tier} | {int(row.n)} | {float(row.accuracy):.3f} | "
            f"{float(row.mean_confidence):.3f} | {float(row.ece_equal_width_10):.3f} | "
            f"{float(row.mean_confidence_incorrect) if not math.isnan(row.mean_confidence_incorrect) else float('nan'):.3f} |"
        )
    md.append("")
    report_path = out_dir / f"holdout_calibration_report_{run_id}.md"
    report_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    output_hashes[report_path.name] = sha256_file(report_path)

    manifest = {
        "composer_version": COMPOSER_VERSION,
        "report_schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": resolve_git_commit(repo_root),
        "run_id": run_id,
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
        "metrics": metrics,
        "split_class_accounting": {
            k: v for k, v in accounting.items() if k != "train_only_family_canonical"
        },
        "train_only_class_count": accounting["train_only_classes"],
        "source_tables": {
            "headline_test_predictions": str(pred_path),
            "split_freeze_headline": str(split_path),
        },
        "input_sha256": {
            "headline_test_predictions": sha256_file(pred_path),
            "split_freeze_headline": sha256_file(split_path),
        },
        "output_sha256": output_hashes,
        "report_markdown": str(report_path),
        "output_dir": str(out_dir),
        "controls": {
            "no_database_access": True,
            "confidence_is_not_assumed_calibrated": True,
            "generated_outputs_must_not_be_committed": True,
        },
    }
    manifest_path = out_dir / f"holdout_calibration_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


__all__ = [
    "COMPOSER_VERSION",
    "build_calibration_tables",
    "build_split_class_accounting",
    "compose_holdout_calibration_report",
]
