"""Tier-aware held-out evaluation summaries for family-target model runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

from config import app_config
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.governance import family_tier_authority

_TIER_ORDER = {"overall": 0, "major": 1, "minor": 2, "generic_or_coarse": 3, "unresolved": 4}


def _clean_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _runtime_split_metadata() -> pd.DataFrame:
    frame = getattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", None)
    if not isinstance(frame, pd.DataFrame) or frame.empty or "sample_id" not in frame.columns:
        return pd.DataFrame()
    out = frame.copy()
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["sample_id"]).copy()
    out["sample_id"] = out["sample_id"].astype(int)
    return out


def _tier_for_row(row: pd.Series) -> str:
    family_name = _clean_token(row.get("family_canonical"))
    family_id = pd.to_numeric(pd.Series([row.get("family_id")]), errors="coerce").iloc[0]
    generic_tokens = family_tier_authority.generic_coarse_token_set()
    major_families = family_tier_authority.major_family_name_set()
    type_slug = _clean_token(row.get("type_slug"))
    category_primary = _clean_token(row.get("category_primary"))
    category_subtype = _clean_token(row.get("category_subtype"))
    sample_label_kind = _clean_token(row.get("sample_label_kind"))

    mapped_family = bool(family_name) and pd.notna(family_id) and float(family_id) >= 0
    if mapped_family:
        return "major" if family_name in major_families else "minor"
    if (
        family_name in generic_tokens
        or category_primary in generic_tokens
        or category_subtype in generic_tokens
        or sample_label_kind in set(family_tier_authority.WEAK_LABEL_KINDS)
    ):
        return "generic_or_coarse"
    if type_slug:
        return "unresolved"
    return "unresolved"


def _subset_metrics(y_true: list[Any], y_pred: list[Any]) -> dict[str, Any]:
    if not y_true:
        return {
            "sample_count": 0,
            "distinct_true_labels": 0,
            "macro_f1": None,
            "weighted_f1": None,
            "accuracy": None,
        }
    return {
        "sample_count": int(len(y_true)),
        "distinct_true_labels": int(len({str(v) for v in y_true})),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
    }


def build_family_tier_model_evaluation_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Build tier-aware held-out metrics rows from model evaluation outputs."""
    training_label_field = str(
        getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "") or "family_id"
    ).strip()
    if training_label_field != "family_id":
        return []

    meta = _runtime_split_metadata()
    if meta.empty:
        return []
    meta = meta.copy()
    meta["authority_tier"] = meta.apply(_tier_for_row, axis=1)
    meta_by_id = meta.set_index("sample_id", drop=False).to_dict(orient="index")

    authority = family_tier_authority.major_family_authority_payload()
    policy = family_tier_authority.generic_coarse_token_policy_payload()
    rows: list[dict[str, Any]] = []
    for model_name, payload in (results or {}).items():
        if not isinstance(payload, dict):
            continue
        evaluation = payload.get("evaluation", {})
        X_test = payload.get("X_test")
        if not isinstance(evaluation, dict) or not isinstance(X_test, pd.DataFrame):
            continue
        y_true_raw = evaluation.get("y_true")
        y_pred_raw = evaluation.get("y_pred")
        if y_true_raw is None or y_pred_raw is None:
            continue
        test_ids = pd.to_numeric(pd.Index(X_test.index), errors="coerce")
        if test_ids.isna().any():
            continue
        test_ids = test_ids.astype(int)
        y_true = [str(v) for v in list(y_true_raw)]
        y_pred = [str(v) for v in list(y_pred_raw)]
        if len(test_ids) != len(y_true) or len(y_true) != len(y_pred):
            continue

        tier_buckets: dict[str, tuple[list[str], list[str]]] = {
            "overall": (list(y_true), list(y_pred)),
            "major": ([], []),
            "minor": ([], []),
            "generic_or_coarse": ([], []),
            "unresolved": ([], []),
        }
        for sid, yt, yp in zip(test_ids.tolist(), y_true, y_pred):
            tier = str(meta_by_id.get(int(sid), {}).get("authority_tier", "unresolved"))
            tier_buckets.setdefault(tier, ([], []))
            tier_buckets[tier][0].append(yt)
            tier_buckets[tier][1].append(yp)

        for tier_name, (tier_true, tier_pred) in tier_buckets.items():
            metrics = _subset_metrics(tier_true, tier_pred)
            rows.append(
                {
                    "model": str(model_name),
                    "evaluation_scope": tier_name,
                    "sample_count": metrics["sample_count"],
                    "distinct_true_labels": metrics["distinct_true_labels"],
                    "macro_f1": metrics["macro_f1"],
                    "weighted_f1": metrics["weighted_f1"],
                    "accuracy": metrics["accuracy"],
                    "training_label_field": training_label_field,
                    "major_authority_version": str(authority.get("version", "") or ""),
                    "major_authority_hash": str(authority.get("hash", "") or ""),
                    "generic_policy_version": str(policy.get("version", "") or ""),
                    "generic_policy_hash": str(policy.get("hash", "") or ""),
                }
            )
    rows.sort(key=lambda row: (str(row.get("model", "")), _TIER_ORDER.get(str(row.get("evaluation_scope", "")), 9)))
    return rows


def export_family_tier_model_evaluation_reports(
    *,
    diagnostics_dir: Path,
    run_id: str,
    results: dict[str, Any],
) -> list[str]:
    """Write tier-aware held-out evaluation summaries for family-target runs."""
    rows = build_family_tier_model_evaluation_rows(results)
    if not rows:
        return []

    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)

    csv_path = diagnostics_dir / f"family_tier_model_evaluation_{run_id}.csv"
    json_path = diagnostics_dir / f"family_tier_model_evaluation_{run_id}.json"
    md_path = diagnostics_dir / f"family_tier_model_evaluation_{run_id}.md"

    csv_text = df.to_csv(index=False)
    csv_path.write_text(csv_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=csv_path.name,
        csv_text=csv_text,
        global_latest_name="family_tier_model_evaluation.latest.csv",
    )

    json_payload = json.dumps(rows, indent=2, sort_keys=True) + "\n"
    json_path.write_text(json_payload, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        text=json_payload,
        global_latest_name="family_tier_model_evaluation.latest.json",
    )

    lines = [
        "# Family Tier Model Evaluation",
        "",
        f"Run ID: `{run_id}`",
        "",
        "| model | scope | samples | labels | macro_f1 | weighted_f1 | accuracy |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        def _fmt(value: Any) -> str:
            return "—" if value is None else f"{float(value):.4f}"
        lines.append(
            f"| `{row.get('model', '')}` | `{row.get('evaluation_scope', '')}` | "
            f"{int(row.get('sample_count', 0))} | {int(row.get('distinct_true_labels', 0))} | "
            f"{_fmt(row.get('macro_f1'))} | {_fmt(row.get('weighted_f1'))} | {_fmt(row.get('accuracy'))} |"
        )
    md_text = "\n".join(lines).strip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="family_tier_model_evaluation.latest.md",
    )

    return [str(json_path), str(csv_path), str(md_path)]


__all__ = [
    "build_family_tier_model_evaluation_rows",
    "export_family_tier_model_evaluation_reports",
]
