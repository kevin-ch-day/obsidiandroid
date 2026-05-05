"""Skeptical audits for very high headline classifier scores: scope, leakage hints, split overlap, SMOTE."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from config import app_config

from obsidiandroid.reporting import operator_dashboard


def _safe_read_split_audit(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _unique_families_from_drop_detail(drop_detail: list[Any]) -> int:
    fams: set[str] = set()
    for row in drop_detail:
        if isinstance(row, dict):
            f = row.get("family")
            if f is not None and str(f).strip():
                fams.add(str(f).strip())
    return len(fams)


def _label_display(raw: Any, label_map: dict[str, str]) -> str:
    s = str(raw).strip()
    if not s:
        return "unknown"
    if s in label_map:
        return str(label_map[s])
    try:
        ik = str(int(float(s)))
        if ik in label_map:
            return str(label_map[ik])
    except (ValueError, TypeError):
        pass
    return str(label_map.get(s, s))


def _build_label_map(model_results: dict[str, Any], model_key: str, diagnostics_dir: Path, run_id: str) -> dict[str, str]:
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    out: dict[str, str] = {}
    if isinstance(res, dict):
        m = res.get("label_name_map")
        if isinstance(m, dict):
            out = {str(k): str(v) for k, v in m.items() if str(k).strip() and str(v).strip()}
    if not out:
        p = diagnostics_dir / f"label_name_map_{run_id}.json"
        if not p.is_file():
            p = diagnostics_dir / "label_name_map.latest.json"
        if p.is_file():
            try:
                blob = json.loads(p.read_text(encoding="utf-8"))
                m2 = blob.get("label_name_map") if isinstance(blob, dict) else None
                if isinstance(m2, dict):
                    out = {str(k): str(v) for k, v in m2.items() if str(k).strip() and str(v).strip()}
            except Exception:
                pass
    return out


def write_headline_score_scope(
    *,
    diagnostics_dir: Path,
    run_id: str,
    q1: Mapping[str, Any],
    manifest_context: Mapping[str, Any],
    drop_detail: list[Any],
) -> dict[str, Any]:
    """Separate governed cohort semantics from the post-support-filter supervised task."""
    diagnostics_dir = Path(diagnostics_dir)
    gov_n = int(q1.get("governed_samples") or 0)
    aligned_n = q1.get("aligned_supervised_samples")
    trainable_n = q1.get("trainable_after_support_filter")
    fam_gov = int(q1.get("families_represented") or 0)
    type_gov = int(q1.get("malware_types_represented") or 0)
    fam_train = int(getattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 0) or 0)
    dropped_fams = _unique_families_from_drop_detail(list(drop_detail) if isinstance(drop_detail, list) else [])
    if dropped_fams == 0 and fam_gov and fam_train:
        dropped_fams = max(0, fam_gov - fam_train)

    aligned_i = int(aligned_n) if aligned_n not in (None, "") else None
    trainable_i = int(trainable_n) if trainable_n not in (None, "") else None
    dropped_samples = None
    if aligned_i is not None and trainable_i is not None:
        dropped_samples = max(0, aligned_i - trainable_i)

    payload: dict[str, Any] = {
        "run_id": run_id,
        "governed_cohort": {
            "samples": gov_n,
            "families": fam_gov,
            "malware_types": type_gov,
        },
        "trainable_family_classification_task": {
            "samples_after_support_filter": trainable_i,
            "families_after_support_filter": fam_train,
            "samples_dropped_before_training": dropped_samples,
            "families_dropped_before_training_est": dropped_fams,
        },
        "interpretation": (
            "The headline holdout score applies to the filtered supervised task "
            f"({trainable_i or 'n/a'} samples, {fam_train} families), not necessarily all "
            f"{fam_gov} families present in the governed cohort."
        ),
        "why_this_matters": (
            "High scores may partly reflect removal of low-support / harder families before training. "
            "Document this boundary whenever reporting Macro-F1."
        ),
    }
    (diagnostics_dir / "headline_score_scope.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_lines = [
        f"# Scope of headline score — `{run_id}`",
        "",
        "## Governed cohort",
        "",
        f"- Samples: **{gov_n}**",
        f"- Families: **{fam_gov}**",
        f"- Malware types: **{type_gov}**",
        "",
        "## Trainable family-classification task",
        "",
        f"- Samples after support filtering: **{trainable_i if trainable_i is not None else '—'}**",
        f"- Families after support filtering: **{fam_train}**",
        f"- Samples dropped before training (aligned − trainable): **{dropped_samples if dropped_samples is not None else '—'}**",
        f"- Families dropped / merged before training (estimate): **{dropped_fams}**",
        "",
        "## Interpretation",
        "",
        payload["interpretation"],
        "",
        "## Why this matters",
        "",
        payload["why_this_matters"],
        "",
    ]
    (diagnostics_dir / "headline_score_scope.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return payload


def write_high_score_audit(
    *,
    diagnostics_dir: Path,
    run_id: str,
    model_key: str,
    headline: Mapping[str, float | int | None],
    scope: Mapping[str, Any],
    drop_detail: list[Any],
) -> dict[str, Any]:
    """Narrative checklist of plausible inflation mechanisms."""
    diagnostics_dir = Path(diagnostics_dir)
    dropped_fams = _unique_families_from_drop_detail(list(drop_detail) if isinstance(drop_detail, list) else [])
    trainable = scope.get("trainable_family_classification_task") or {}
    dropped_samples = trainable.get("samples_dropped_before_training")
    fam_train = trainable.get("families_after_support_filter")
    gov_f = (scope.get("governed_cohort") or {}).get("families")

    factors = [
        {
            "tag": "SUPPORT_FILTER",
            "lines": [
                f"{dropped_samples or '—'} samples from an estimated {dropped_fams} families were removed before supervised training.",
                f"Score applies to {fam_train} supported families, not all {gov_f} governed families.",
            ],
        },
        {
            "tag": "RANDOM_SPLIT",
            "lines": [
                "Random stratified split may place closely related variants in both train and test.",
                "Exact SHA duplicates are audited separately; package/campaign/variant overlap still needs review.",
            ],
        },
        {
            "tag": "SMOTE",
            "lines": [
                "Training rows are expanded by SMOTE/ROS when enabled — see smote_effect_check.* and RUNTIME_SMOTE_AUDIT_LAST.",
                "Compare against a no-resampling baseline when making strong claims.",
            ],
        },
        {
            "tag": "FEATURE_LEAKAGE",
            "lines": [
                "Full fused features may include parsed vendor family/type signals.",
                "Compare headline Macro-F1 to permission-only and vendor_parsed_no_family ablations.",
            ],
        },
        {
            "tag": "TEST_SET_SIZE",
            "lines": [
                f"Holdout size is {headline.get('test_samples', '—')} samples across {fam_train} families.",
                "Per-family recall and confusion tails matter more than global accuracy.",
            ],
        },
    ]
    payload: dict[str, Any] = {
        "run_id": run_id,
        "headline_model": model_key,
        "metrics": {
            "accuracy": headline.get("accuracy"),
            "macro_f1": headline.get("macro_f1"),
            "weighted_f1": headline.get("weighted_f1"),
            "test_samples": headline.get("test_samples"),
            "trainable_families": fam_train,
        },
        "possible_inflation_factors": factors,
        "interpretation": (
            "Treat headline accuracy as promising but not final proof. "
            "Validate with leakage-safe ablations, no-SMOTE baselines, and harder splits when stakes are high."
        ),
    }
    (diagnostics_dir / "high_score_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md = [
        f"# Why is performance this high? — `{run_id}`",
        "",
        "## Headline model",
        "",
        f"- Model: **{model_key}**",
        f"- Accuracy: **{headline.get('accuracy', 0):.4f}**" if headline.get("accuracy") is not None else "",
        f"- Macro-F1: **{headline.get('macro_f1', 0):.4f}**" if headline.get("macro_f1") is not None else "",
        f"- Weighted F1: **{headline.get('weighted_f1', 0):.4f}**" if headline.get("weighted_f1") is not None else "",
        f"- Test samples: **{headline.get('test_samples', '—')}**",
        f"- Trainable families: **{fam_train}**",
        "",
        "## Possible inflation factors",
        "",
    ]
    for block in factors:
        md.append(f"### [{block['tag']}]")
        md.extend(f"- {ln}" for ln in block["lines"])
        md.append("")
    md.extend(
        [
            "## Interpretation",
            "",
            payload["interpretation"],
            "",
        ]
    )
    (diagnostics_dir / "high_score_audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return payload


def write_false_attribution_audit(
    *,
    diagnostics_dir: Path,
    run_id: str,
    model_results: dict[str, Any],
    model_key: str,
    samples_df: pd.DataFrame | None,
    type_lookup: dict[str, str],
) -> dict[str, Any]:
    """Per-family FP/FN skew, confusion pairs, high-confidence errors on holdout."""
    diagnostics_dir = Path(diagnostics_dir)
    label_map = _build_label_map(model_results, model_key, diagnostics_dir, run_id)
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    payload: dict[str, Any] = {
        "run_id": run_id,
        "model": model_key,
        "confidence_available": False,
        "note": "",
    }
    if not isinstance(res, dict):
        payload["note"] = "model result missing"
        _write_false_attribution_empty(diagnostics_dir, payload)
        return payload

    ev = res.get("evaluation") if isinstance(res.get("evaluation"), dict) else {}
    _yt = ev.get("y_true")
    _yp = ev.get("y_pred")
    y_true: list[Any] | None = None
    y_pred: list[Any] | None = None
    if _yt is not None and _yp is not None:
        try:
            y_true = list(_yt)
            y_pred = list(_yp)
        except TypeError:
            y_true, y_pred = None, None
    if not y_true or not y_pred or len(y_true) != len(y_pred):
        y_true, y_pred = None, None
    cm = ev.get("confusion_matrix")
    labels = ev.get("class_labels") or ev.get("decoded_labels")

    n_wrong = 0
    if y_true is not None and y_pred is not None:
        n_wrong = sum(1 for a, b in zip(y_true, y_pred) if str(a) != str(b))

    confidences: list[float] | None = None
    model = res.get("model")
    X_test = res.get("X_test")
    if model is not None and X_test is not None and hasattr(model, "predict_proba"):
        try:
            pr = model.predict_proba(X_test)
            confidences = [float(x) for x in np.max(pr, axis=1)]
            payload["confidence_available"] = True
        except Exception:
            confidences = None

    rows_fp: list[dict[str, Any]] = []
    rows_fn: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    hi_conf_rows: list[dict[str, Any]] = []

    if cm is not None and labels:
        arr = np.asarray(cm)
        lab = [str(x) for x in labels]
        if arr.ndim == 2 and arr.shape[0] == arr.shape[1] == len(lab):
            n = len(lab)
            for j in range(n):
                pred_name = _label_display(lab[j], label_map)
                tp = int(arr[j, j])
                fp = int(arr[:, j].sum() - arr[j, j])
                denom = fp + tp
                fp_rate = float(fp / denom) if denom > 0 else 0.0
                rows_fp.append(
                    {
                        "predicted_family": pred_name,
                        "false_positives": fp,
                        "true_positives": tp,
                        "fp_rate": round(fp_rate, 6),
                    }
                )
            for i in range(n):
                true_name = _label_display(lab[i], label_map)
                fn = int(arr[i, :].sum() - arr[i, i])
                support = int(arr[i, :].sum())
                rec = float(arr[i, i] / support) if support > 0 else 0.0
                rows_fn.append(
                    {
                        "true_family": true_name,
                        "false_negatives": fn,
                        "recall": round(rec, 6),
                        "support_holdout": support,
                    }
                )
            triples: list[tuple[int, int, int]] = []
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    c = int(arr[i, j])
                    if c > 0:
                        triples.append((i, j, c))
            triples.sort(key=lambda t: -t[2])
            for i, j, c in triples[:25]:
                ti = _label_display(lab[i], label_map)
                pj = _label_display(lab[j], label_map)
                tt = type_lookup.get(str(lab[i]), "") or type_lookup.get(ti, "")
                tp = type_lookup.get(str(lab[j]), "") or type_lookup.get(pj, "")
                shared = "yes" if tt and tp and tt == tp else ("no" if tt and tp else "")
                pair_rows.append(
                    {
                        "true_family": ti,
                        "predicted_family": pj,
                        "count": c,
                        "shared_type": shared,
                    }
                )

    if y_true is not None and y_pred is not None:
        idx = res.get("X_test")
        sid_list: list[Any] = []
        if isinstance(idx, pd.DataFrame):
            sid_list = [int(x) if str(x).isdigit() else x for x in idx.index.tolist()]
        wrong_idx = [k for k, (a, b) in enumerate(zip(y_true, y_pred)) if str(a) != str(b)]
        conf_list = confidences if isinstance(confidences, list) else [None] * len(y_true)
        ranked = sorted(wrong_idx, key=lambda k: float(conf_list[k] or 0.0), reverse=True)
        for k in ranked[:50]:
            row: dict[str, Any] = {
                "sample_id": sid_list[k] if k < len(sid_list) else k,
                "true_family": _label_display(y_true[k], label_map),
                "predicted_family": _label_display(y_pred[k], label_map),
            }
            if conf_list[k] is not None:
                row["confidence"] = round(float(conf_list[k]), 6)
            hi_conf_rows.append(row)

    rows_fp.sort(key=lambda r: -int(r.get("false_positives", 0)))
    rows_fn.sort(key=lambda r: -int(r.get("false_negatives", 0)))

    pd.DataFrame(rows_fp).to_csv(diagnostics_dir / "false_positive_by_predicted_family.csv", index=False)
    pd.DataFrame(rows_fn).to_csv(diagnostics_dir / "false_negative_by_true_family.csv", index=False)
    pd.DataFrame(pair_rows).to_csv(diagnostics_dir / "top_confusion_pairs.csv", index=False)
    if hi_conf_rows:
        pd.DataFrame(hi_conf_rows).to_csv(diagnostics_dir / "high_confidence_wrong_predictions.csv", index=False)
    else:
        pd.DataFrame(
            [{"sample_id": "", "true_family": "", "predicted_family": "", "confidence": "", "note": "no_wrong_predictions_or_no_holdout"}]
        ).to_csv(diagnostics_dir / "high_confidence_wrong_predictions.csv", index=False)

    payload["holdout_wrong_predictions"] = int(n_wrong)
    payload["top_fp_families"] = rows_fp[:10]
    payload["top_fn_families"] = rows_fn[:10]
    payload["top_confusion_pairs"] = pair_rows[:10]
    if n_wrong <= 3:
        payload["note"] = "Very few holdout errors — audit tables are sparse but still exported."

    (diagnostics_dir / "false_attribution_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    md = [
        f"# False attribution audit — `{run_id}`",
        "",
        f"- Model: `{model_key}`",
        f"- Holdout mis-predictions: **{n_wrong}**",
        f"- Confidence on errors: **{'available' if payload['confidence_available'] else 'unavailable'}**",
        "",
        "See `false_positive_by_predicted_family.csv`, `false_negative_by_true_family.csv`, "
        "`top_confusion_pairs.csv`, `high_confidence_wrong_predictions.csv`.",
        "",
    ]
    (diagnostics_dir / "false_attribution_audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return payload


def _write_false_attribution_empty(diagnostics_dir: Path, payload: dict[str, Any]) -> None:
    (diagnostics_dir / "false_attribution_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (diagnostics_dir / "false_attribution_audit.md").write_text(
        "# False attribution audit\n\n(no model payload)\n", encoding="utf-8"
    )
    for name in (
        "false_positive_by_predicted_family.csv",
        "false_negative_by_true_family.csv",
        "high_confidence_wrong_predictions.csv",
        "top_confusion_pairs.csv",
    ):
        pd.DataFrame([{"note": "insufficient_model_state"}]).to_csv(diagnostics_dir / name, index=False)


def _package_prefix_two_segments(package: str) -> str:
    s = str(package).strip().lower()
    if not s:
        return ""
    parts = [p for p in s.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return s


def write_split_contamination_audit(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Train/test overlap on SHA, package, and family+package using split_freeze_headline CSV."""
    del samples_df  # reserved for future joins; split CSV carries audit fields
    diagnostics_dir = Path(diagnostics_dir)
    path = diagnostics_dir / f"split_freeze_headline_{run_id}.csv"
    df = _safe_read_split_audit(path)
    if df.empty:
        df = _safe_read_split_audit(diagnostics_dir / "split_freeze_headline.latest.csv")
    payload: dict[str, Any] = {
        "run_id": run_id,
        "split_audit_path": str(path) if path.is_file() else "",
        "sha_overlap_train_test": 0,
        "package_names_in_both_splits": 0,
        "package_prefix_two_segment_overlap": 0,
        "family_package_pairs_in_both": 0,
        "samples_affected_by_package_overlap": 0,
        "families_affected_by_package_overlap": 0,
        "interpretation": "",
    }

    def _write_empty_split_artifacts() -> None:
        (diagnostics_dir / "split_contamination_audit.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        (diagnostics_dir / "split_contamination_audit.md").write_text(
            f"# Split contamination check — `{run_id}`\n\n{payload['interpretation']}\n",
            encoding="utf-8",
        )
        pd.DataFrame([{"note": "no_split_audit"}]).to_csv(
            diagnostics_dir / "train_test_package_overlap.csv", index=False
        )
        pd.DataFrame([{"note": "no_split_audit"}]).to_csv(
            diagnostics_dir / "train_test_family_package_overlap.csv", index=False
        )

    if df.empty or "split_role" not in df.columns:
        payload["interpretation"] = "Split audit CSV not found — contamination check skipped."
        _write_empty_split_artifacts()
        return payload

    for col in ("package_name", "family_canonical", "year", "sha256"):
        if col not in df.columns:
            df[col] = ""
    df["sha256"] = df["sha256"].fillna("").astype(str).str.strip().str.lower()
    df["package_name"] = df["package_name"].fillna("").astype(str).str.strip().str.lower()
    df["family_canonical"] = df["family_canonical"].fillna("").astype(str).str.strip()

    train = df[df["split_role"].astype(str) == "train"].copy()
    test = df[df["split_role"].astype(str) == "test"].copy()
    train_sha = set(train.loc[train["sha256"] != "", "sha256"].tolist())
    test_sha = set(test.loc[test["sha256"] != "", "sha256"].tolist())
    payload["sha_overlap_train_test"] = int(len(train_sha & test_sha))

    pkg_train = set(train.loc[train["package_name"] != "", "package_name"].tolist())
    pkg_test = set(test.loc[test["package_name"] != "", "package_name"].tolist())
    pkg_both = pkg_train & pkg_test
    payload["package_names_in_both_splits"] = int(len(pkg_both))

    train["pkg_prefix2"] = train["package_name"].map(_package_prefix_two_segments)
    test["pkg_prefix2"] = test["package_name"].map(_package_prefix_two_segments)
    pref_train = set(train.loc[train["pkg_prefix2"] != "", "pkg_prefix2"].tolist())
    pref_test = set(test.loc[test["pkg_prefix2"] != "", "pkg_prefix2"].tolist())
    pref_both = pref_train & pref_test
    payload["package_prefix_two_segment_overlap"] = int(len(pref_both))

    train_fp = set(
        zip(train["family_canonical"].tolist(), train["package_name"].tolist())
    )
    test_fp = set(zip(test["family_canonical"].tolist(), test["package_name"].tolist()))
    fp_both = {(f, p) for f, p in train_fp if p and (f, p) in test_fp}
    payload["family_package_pairs_in_both"] = int(len(fp_both))

    affected = df[
        (df["package_name"].isin(pkg_both)) & (df["package_name"].astype(str).str.len() > 0)
    ]
    payload["samples_affected_by_package_overlap"] = int(len(affected))
    fam_hit = affected["family_canonical"].fillna("").astype(str)
    fam_hit = fam_hit[fam_hit.str.len() > 0]
    payload["families_affected_by_package_overlap"] = int(fam_hit.nunique())

    pkg_rows: list[dict[str, Any]] = []
    for pkg in sorted(pkg_both)[:500]:
        nt = int((train["package_name"] == pkg).sum())
        ne = int((test["package_name"] == pkg).sum())
        pkg_rows.append({"package_name": pkg, "n_train": nt, "n_test": ne, "n_total": nt + ne})

    fprows: list[dict[str, Any]] = []
    for f, p in sorted(fp_both)[:500]:
        nt = int(((train["family_canonical"] == f) & (train["package_name"] == p)).sum())
        ne = int(((test["family_canonical"] == f) & (test["package_name"] == p)).sum())
        fprows.append({"family_canonical": f, "package_name": p, "n_train": nt, "n_test": ne, "n_total": nt + ne})

    year_dist = {}
    if "year" in df.columns:
        for role in ("train", "test"):
            sub = df[df["split_role"].astype(str) == role]["year"]
            year_dist[role] = sub.fillna("").astype(str).value_counts().head(12).to_dict()

    payload["first_seen_year_distribution_head"] = year_dist
    if payload["sha_overlap_train_test"] == 0:
        sha_note = "Exact SHA duplication across splits: **clean** (0 overlap)."
    else:
        sha_note = f"⚠ SHA overlap count: **{payload['sha_overlap_train_test']}** — investigate pipeline policy."
    if len(pkg_both) == 0:
        pkg_note = "No non-empty package_name appears in both splits."
    else:
        pkg_note = (
            f"{len(pkg_both)} package name(s) appear in both train and test — random split may be easier than "
            "package-grouped evaluation."
        )
    payload["interpretation"] = f"{sha_note} {pkg_note}"

    (diagnostics_dir / "split_contamination_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    md = [
        f"# Split contamination check — `{run_id}`",
        "",
        f"- Exact SHA overlap train/test: **{payload['sha_overlap_train_test']}**",
        f"- Package names in both splits: **{payload['package_names_in_both_splits']}**",
        f"- Two-segment package prefix in both splits: **{payload['package_prefix_two_segment_overlap']}**",
        f"- Family + package pairs in both: **{payload['family_package_pairs_in_both']}**",
        f"- Samples on overlapping packages: **{payload['samples_affected_by_package_overlap']}**",
        f"- Families touched by overlapping packages: **{payload['families_affected_by_package_overlap']}**",
        "",
        "## Interpretation",
        "",
        payload["interpretation"],
        "",
        "See `train_test_package_overlap.csv`, `train_test_family_package_overlap.csv`.",
        "",
    ]
    (diagnostics_dir / "split_contamination_audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    pd.DataFrame(pkg_rows).to_csv(diagnostics_dir / "train_test_package_overlap.csv", index=False)
    pd.DataFrame(fprows).to_csv(diagnostics_dir / "train_test_family_package_overlap.csv", index=False)
    return payload


def write_smote_effect_check(*, diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    """Record SMOTE/ROS expansion; no-SMOTE baseline optional (not auto-run)."""
    diagnostics_dir = Path(diagnostics_dir)
    by_model = getattr(app_config, "RUNTIME_SMOTE_AUDIT_BY_MODEL", None)
    snap: dict[str, Any] = {}
    if isinstance(by_model, dict) and isinstance(by_model.get("random_forest"), dict):
        snap = dict(by_model["random_forest"])
    else:
        last = getattr(app_config, "RUNTIME_SMOTE_AUDIT_LAST", None)
        if isinstance(last, dict):
            snap = dict(last)
    prov = getattr(app_config, "RUNTIME_TRAINING_PROVENANCE_SUMMARY", None)
    if not isinstance(prov, dict):
        prov = {}

    rows = [
        {"metric": "run_id", "with_smote_value": run_id, "without_smote_value": "", "notes": ""},
        {
            "metric": "holdout_smote_enabled_last_fit",
            "with_smote_value": str(prov.get("holdout_train_smote_effective_last_fit")),
            "without_smote_value": "",
            "notes": "Per headline model last fit in factory",
        },
    ]
    for k, v in snap.items():
        rows.append({"metric": str(k), "with_smote_value": str(v), "without_smote_value": "", "notes": "SMOTE snapshot"})

    pd.DataFrame(rows).to_csv(diagnostics_dir / "smote_effect_check.csv", index=False)
    md = [
        f"# SMOTE effect check — `{run_id}`",
        "",
        "## With resampling (this run)",
        "",
        "```json",
        json.dumps(snap, indent=2, sort_keys=True, default=str),
        "```",
        "",
        "## Without SMOTE",
        "",
        "Not auto-computed in this pipeline revision. Re-run with `ENABLE_SMOTE_OVERSAMPLING=False` "
        "or add a dedicated baseline job to populate `without_smote_value` columns.",
        "",
        "## Interpretation",
        "",
        "If post-resample train rows ≫ pre-resample rows, Macro-F1 may be partly a resampling artifact — quantify with a no-SMOTE baseline.",
        "",
    ]
    (diagnostics_dir / "smote_effect_check.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    payload = {"run_id": run_id, "smote_snapshot": snap, "provenance_flags": prov}
    (diagnostics_dir / "smote_effect_check.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return payload


def write_leakage_safe_score_comparison(
    *,
    diagnostics_dir: Path,
    run_id: str,
    headline_macro_f1: float,
    model_key: str,
    primary_label_target: str,
) -> dict[str, Any]:
    """Map ablation_summary Macro-F1 (same model) to human-readable feature sets."""
    diagnostics_dir = Path(diagnostics_dir)
    ab = pd.DataFrame()
    for name in (f"ablation_summary_{run_id}.csv", "ablation_summary.latest.csv"):
        p = diagnostics_dir / name
        if p.is_file():
            try:
                ab = pd.read_csv(p)
                break
            except Exception:
                pass
    rows_out: list[dict[str, Any]] = []
    note = ""
    if ab.empty or "experiment" not in ab.columns or "macro_f1_score" not in ab.columns or "model" not in ab.columns:
        note = "ablation_summary not available"
    else:
        sub = ab.copy()
        sub["macro_f1_score"] = pd.to_numeric(sub["macro_f1_score"], errors="coerce")
        if "label_target" in sub.columns:
            sub = sub[sub["label_target"].astype(str) == str(primary_label_target)]
        mk_l = str(model_key).lower().replace("-", "_")
        sub["_mk"] = sub["model"].astype(str).str.lower().str.replace("-", "_", regex=False)
        sub = sub[sub["_mk"] == mk_l]
        if sub.empty:
            note = f"no ablation rows for model={model_key} label_target={primary_label_target}"
        for exp, grp in sub.groupby(sub["experiment"].astype(str), sort=False):
            best = float(grp["macro_f1_score"].max())
            label = operator_dashboard.format_feature_set_label(str(exp))
            rows_out.append(
                {
                    "feature_set_label": label,
                    "internal_experiment_key": str(exp),
                    "macro_f1": round(best, 6),
                    "delta_vs_headline_macro_f1": round(float(headline_macro_f1) - best, 6),
                }
            )
        rows_out.sort(key=lambda r: -float(r.get("macro_f1") or 0))

    full_row = next((r for r in rows_out if r["internal_experiment_key"] == "full_fused"), None)
    headline_used = float(full_row["macro_f1"]) if full_row is not None else float(headline_macro_f1)
    for r in rows_out:
        r["delta_vs_full_fused_ablation"] = round(headline_used - float(r.get("macro_f1") or 0.0), 6)

    pd.DataFrame(rows_out).to_csv(diagnostics_dir / "leakage_safe_score_comparison.csv", index=False)
    md = [
        f"# Leakage-safe score comparison — `{run_id}`",
        "",
        f"- Headline full-fused Macro-F1 (evaluation): **{headline_macro_f1:.4f}**",
        f"- Model slice: **{model_key}** | label_target filter: **{primary_label_target}**",
        "",
    ]
    if note:
        md.append(f"*{note}*")
        md.append("")
    if rows_out:
        try:
            md.append(pd.DataFrame(rows_out).to_markdown(index=False))
        except Exception:
            md.append("(see leakage_safe_score_comparison.csv)")
        md.append("")
    md.extend(
        [
            "## Interpretation",
            "",
            "- If **full_fused** ≫ **permissions_***, inspect non-permission modalities.",
            "- If **vendor_parsed_full** ≫ **vendor_parsed_no_family**, parsed vendor strings may track labels too closely.",
            "- Strong **permissions_grouped** alone suggests structural signal is largely Android surface.",
            "",
        ]
    )
    (diagnostics_dir / "leakage_safe_score_comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    payload = {
        "run_id": run_id,
        "headline_macro_f1_eval": headline_macro_f1,
        "rows": rows_out,
        "note": note,
    }
    (diagnostics_dir / "leakage_safe_score_comparison.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return payload


_SUSPICIOUS_PATTERNS = re.compile(
    r"(family_id|family_name|family_canonical|parsed_family|malware_type|type_slug|"
    r"true_family|predicted_family|classification_label|\blabel\b|package_name)",
    re.I,
)


def _modality_bucket(name: str) -> str:
    n = str(name).lower()
    if n.startswith("perm__") or n.startswith("perm_grp__"):
        return "permission"
    if _SUSPICIOUS_PATTERNS.search(n):
        return "suspicious_label_like"
    if "consensus" in n or "consensus_score" in n:
        return "vendor_consensus_score"
    if "malware_type_" in n or "family_" in n or "parsed_" in n:
        return "vendor_parsed_signal"
    if "detect" in n or "engine_" in n or n.startswith("vendor_"):
        return "vendor_detection_or_engine"
    return "metadata_or_other"


def write_top_feature_modality_audit(
    *,
    diagnostics_dir: Path,
    model_results: dict[str, Any],
) -> dict[str, Any]:
    """Bucket RF impurity importances into modalities; flag label-like names."""
    diagnostics_dir = Path(diagnostics_dir)
    rf = model_results.get("random_forest") if isinstance(model_results, dict) else None
    named: list[dict[str, Any]] = []
    if isinstance(rf, dict):
        raw = rf.get("metadata", {}).get("feature_importances_named")
        if isinstance(raw, list):
            named = [x for x in raw if isinstance(x, dict)]
    rows: list[dict[str, Any]] = []
    suspicious: list[dict[str, Any]] = []
    bucket_counts: Counter[str] = Counter()
    for item in named:
        fname = str(item.get("feature_name") or "")
        imp = item.get("importance")
        try:
            imp_f = float(imp)
        except (TypeError, ValueError):
            continue
        b = _modality_bucket(fname)
        bucket_counts[b] += imp_f
        rows.append({"feature_name": fname, "importance": imp_f, "modality_bucket": b})
        if b == "suspicious_label_like":
            suspicious.append({"feature_name": fname, "importance": imp_f})
    rows.sort(key=lambda r: -float(r.get("importance") or 0))
    top25 = rows[:25]
    pd.DataFrame(top25).to_csv(diagnostics_dir / "top_feature_modality_audit.csv", index=False)
    pd.DataFrame(suspicious).to_csv(diagnostics_dir / "suspicious_label_like_features.csv", index=False)
    summary = {k: round(float(v), 8) for k, v in bucket_counts.items()}
    payload = {
        "run_id": str(getattr(app_config, "RUNTIME_RUN_ID", "")),
        "importance_mass_by_modality": summary,
        "top_25": top25,
        "suspicious_label_like_count": len(suspicious),
    }
    (diagnostics_dir / "top_feature_modality_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    md = [
        "# Top feature modality audit (RF impurity)",
        "",
        "## Importance mass by coarse modality",
        "",
        "```json",
        json.dumps(summary, indent=2, sort_keys=True),
        "```",
        "",
        "## Top 25 features",
        "",
    ]
    if top25:
        try:
            md.append(pd.DataFrame(top25).to_markdown(index=False))
        except Exception:
            md.append("(see top_feature_modality_audit.csv)")
    else:
        md.append("(No RF importances_named in model payload — export RF metadata or run random_forest.)")
    md.extend(
        [
            "",
            "## Interpretation",
            "",
            "- If **suspicious_label_like** mass is large, inspect pruning / vendor parsed fields.",
            "- If **permission** dominates, the model is more structurally grounded in Android manifests.",
            "",
        ]
    )
    (diagnostics_dir / "top_feature_modality_audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return payload


def write_recommended_validation_plan(*, diagnostics_dir: Path, headline_macro_f1: float) -> None:
    diagnostics_dir = Path(diagnostics_dir)
    lines = [
        "# Recommended harder validation",
        "",
        "When headline Macro-F1 is very high, add at least one stricter validation before strong claims.",
        "",
        "## Suggested approaches",
        "",
        "1. **package_grouped split** — prevent the same `package_name` from appearing in both train and test.",
        "2. **family_package_grouped split** — prevent the same `(family_canonical, package_name)` pair from crossing.",
        "3. **time split** — train on older `first_seen` / VT timestamps, test on newer samples.",
        "4. **no-SMOTE baseline** — re-run with `ENABLE_SMOTE_OVERSAMPLING=False` and compare Macro-F1.",
        "5. **Leakage-safe fused model** — train on vendor_parsed_no_family + permissions only; compare to full_fused.",
        "",
        f"Current headline Macro-F1 (evaluation): **{headline_macro_f1:.4f}**",
        "",
    ]
    (diagnostics_dir / "recommended_validation_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_all_skeptic_audits(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    q1_payload: Mapping[str, Any],
    manifest_context: Mapping[str, Any],
    model_results: dict[str, Any],
    top_model_key: str,
    samples_df: pd.DataFrame | None,
    headline_macro_f1: float,
    headline_acc: float,
    headline_weighted_f1: float,
    drop_detail: list[Any],
    primary_label_target: str,
    type_lookup: dict[str, str],
) -> dict[str, Any]:
    """Run all skeptic writers; return structured snippets for terminal rendering."""
    diagnostics_dir = Path(diagnostics_dir)
    drop_detail = list(drop_detail) if isinstance(drop_detail, list) else []

    scope = write_headline_score_scope(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        q1=q1_payload,
        manifest_context=manifest_context,
        drop_detail=drop_detail,
    )
    test_n = manifest_context.get("test_sample_count")
    try:
        test_n_i = int(test_n) if test_n not in (None, "") else None
    except Exception:
        test_n_i = None

    headline_metrics = {
        "accuracy": float(headline_acc),
        "macro_f1": float(headline_macro_f1),
        "weighted_f1": float(headline_weighted_f1),
        "test_samples": test_n_i,
    }
    high = write_high_score_audit(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        model_key=top_model_key,
        headline=headline_metrics,
        scope=scope,
        drop_detail=drop_detail,
    )
    false_attr = write_false_attribution_audit(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        model_results=model_results,
        model_key=top_model_key,
        samples_df=samples_df,
        type_lookup=type_lookup,
    )
    split_a = write_split_contamination_audit(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        samples_df=samples_df,
    )
    smote = write_smote_effect_check(diagnostics_dir=diagnostics_dir, run_id=run_id)
    leak = write_leakage_safe_score_comparison(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        headline_macro_f1=headline_macro_f1,
        model_key=top_model_key,
        primary_label_target=primary_label_target,
    )
    feat = write_top_feature_modality_audit(diagnostics_dir=diagnostics_dir, model_results=model_results)
    if headline_macro_f1 >= 0.85:
        write_recommended_validation_plan(
            diagnostics_dir=diagnostics_dir, headline_macro_f1=headline_macro_f1
        )

    return {
        "profile_id": profile_id,
        "scope": scope,
        "high_score_audit": high,
        "false_attribution": false_attr,
        "split_contamination": split_a,
        "smote": smote,
        "leakage_comparison": leak,
        "feature_modality": feat,
        "headline_metrics": headline_metrics,
        "model_key": top_model_key,
    }


def print_scope_of_headline_score_terminal(skeptic: Mapping[str, Any], *, pr: Callable[[str], None], du: Any) -> None:
    """Print governed vs trainable headline task boundary (run first)."""
    scope = skeptic.get("scope") or {}
    gov = scope.get("governed_cohort") or {}
    tt = scope.get("trainable_family_classification_task") or {}
    du.print_section("SCOPE OF HEADLINE SCORE")
    pr("Governed cohort:")
    pr(f"  Samples: {gov.get('samples', '—')}")
    pr(f"  Families: {gov.get('families', '—')}")
    pr(f"  Types: {gov.get('malware_types', '—')}")
    pr("")
    pr("Trainable family-classification task:")
    pr(f"  Samples after support filtering: {tt.get('samples_after_support_filter', '—')}")
    pr(f"  Families after support filtering: {tt.get('families_after_support_filter', '—')}")
    pr(f"  Samples dropped before training: {tt.get('samples_dropped_before_training', '—')}")
    pr(f"  Families dropped before training (est.): {tt.get('families_dropped_before_training_est', '—')}")
    pr("")
    pr("Interpretation:")
    pr(f"  {scope.get('interpretation', '')}")
    pr("")
    pr("Why this matters:")
    pr(f"  {scope.get('why_this_matters', '')}")
    pr("")


def print_skeptic_audit_followup_terminal(bundle: dict[str, Any], *, pr: Callable[[str], None], du: Any) -> None:
    """Print high-score skeptic blocks after MODEL AND FAMILY FAILURE (not scope)."""
    scope = bundle.get("scope") or {}
    tt = scope.get("trainable_family_classification_task") or {}
    hm = bundle.get("headline_metrics") or {}
    mk = str(
        bundle.get("model_key")
        or (bundle.get("high_score_audit") or {}).get("headline_model")
        or "random_forest"
    )
    du.print_section("WHY IS PERFORMANCE THIS HIGH?")
    pr("Headline model:")
    pr(f"  Model: {mk}")
    pr(f"  Accuracy: {float(hm.get('accuracy') or 0):.4f}")
    pr(f"  Macro-F1: {float(hm.get('macro_f1') or 0):.4f}")
    pr(f"  Weighted F1: {float(hm.get('weighted_f1') or 0):.4f}")
    pr(f"  Test samples: {hm.get('test_samples', '—')}")
    pr(f"  Trainable families: {tt.get('families_after_support_filter', '—')}")
    pr("")
    pr("Possible inflation factors:")
    for block in (bundle.get("high_score_audit") or {}).get("possible_inflation_factors") or []:
        tag = block.get("tag", "")
        pr(f"  [{tag}]")
        for ln in block.get("lines") or []:
            pr(f"    {ln}")
    pr("")
    pr("Interpretation:")
    pr(f"  {(bundle.get('high_score_audit') or {}).get('interpretation', '')}")
    pr("")

    fa = bundle.get("false_attribution") or {}
    du.print_section("FALSE ATTRIBUTION AUDIT")
    pr(f"Holdout mis-predictions: {fa.get('holdout_wrong_predictions', '—')} | confidence: {'yes' if fa.get('confidence_available') else 'no'}")
    if fa.get("note"):
        pr(f"Note: {fa['note']}")
    pr("")
    pr("Most over-predicted families (by false positives on holdout):")
    for row in (fa.get("top_fp_families") or [])[:8]:
        pr(
            f"  {row.get('predicted_family')}: FP={row.get('false_positives')} TP={row.get('true_positives')} "
            f"fp_rate={float(row.get('fp_rate') or 0):.3f}"
        )
    pr("")
    pr("Most missed true families (false negatives):")
    for row in (fa.get("top_fn_families") or [])[:8]:
        pr(
            f"  {row.get('true_family')}: FN={row.get('false_negatives')} recall={float(row.get('recall') or 0):.3f} "
            f"support={row.get('support_holdout')}"
        )
    pr("")
    pr("Top confusion pairs (true → pred):")
    for row in (fa.get("top_confusion_pairs") or [])[:8]:
        pr(
            f"  {row.get('true_family')} → {row.get('predicted_family')}: n={row.get('count')} "
            f"same_type={row.get('shared_type', '?')}"
        )
    pr("")
    pr("Files: false_positive_by_predicted_family.csv, false_negative_by_true_family.csv, "
        "high_confidence_wrong_predictions.csv, top_confusion_pairs.csv")
    pr("")

    sc = bundle.get("split_contamination") or {}
    du.print_section("SPLIT CONTAMINATION CHECK")
    pr(f"Exact SHA overlap train/test: {sc.get('sha_overlap_train_test', '—')}")
    pr(f"Package names in both splits: {sc.get('package_names_in_both_splits', '—')}")
    pr(f"Two-segment package prefix in both: {sc.get('package_prefix_two_segment_overlap', '—')}")
    pr(f"Family + package pairs in both: {sc.get('family_package_pairs_in_both', '—')}")
    pr(f"Samples on overlapping packages: {sc.get('samples_affected_by_package_overlap', '—')}")
    pr(f"Families affected by package overlap: {sc.get('families_affected_by_package_overlap', '—')}")
    pr("")
    pr("Interpretation:")
    pr(f"  {sc.get('interpretation', '')}")
    pr("")

    sm = bundle.get("smote") or {}
    snap = sm.get("smote_snapshot") if isinstance(sm.get("smote_snapshot"), dict) else {}
    du.print_section("SMOTE EFFECT CHECK")
    pr(f"With SMOTE/ROS (headline): Macro-F1 ≈ {float(hm.get('macro_f1') or 0):.4f} | Acc ≈ {float(hm.get('accuracy') or 0):.4f}")
    pr("Without SMOTE: (not auto-run — see smote_effect_check.md / re-run with oversampling disabled)")
    if snap:
        pr(f"Snapshot: original_train_n={snap.get('original_train_n')} post_resample_train_n={snap.get('post_resample_train_n')} "
            f"method={snap.get('method')} k_neighbors={snap.get('k_neighbors', '—')}")
    pr("")

    lc = bundle.get("leakage_comparison") or {}
    du.print_section("LEAKAGE-SAFE SCORE COMPARISON")
    pr(f"Headline eval Macro-F1: {float(hm.get('macro_f1') or 0):.4f}")
    for row in (lc.get("rows") or [])[:12]:
        pr(
            f"  {row.get('feature_set_label')}: Macro-F1={row.get('macro_f1')} "
            f"(headline_eval − row = {row.get('delta_vs_headline_macro_f1')})"
        )
    if lc.get("note"):
        pr(f"  ({lc['note']})")
    pr("")

    fm = bundle.get("feature_modality") or {}
    du.print_section("TOP FEATURE MODALITY AUDIT (RF)")
    mass = fm.get("importance_mass_by_modality") or {}
    if mass:
        pr("Importance mass by bucket: " + ", ".join(f"{k}={v:.5f}" for k, v in sorted(mass.items(), key=lambda kv: -kv[1])))
    else:
        pr("(No RF importances in payload.)")
    pr("")
    if float(hm.get("macro_f1") or 0) >= 0.85:
        du.print_section("RECOMMENDED HARDER VALIDATION")
        pr("  1. package_grouped split")
        pr("  2. family_package_grouped split")
        pr("  3. time split by first_seen / VT timestamps")
        pr("  4. no-SMOTE baseline")
        pr("  5. leakage-safe fused model (vendor_parsed_no_family + permissions)")
        pr("See recommended_validation_plan.md")
        pr("")


def print_skeptic_audit_terminal(bundle: dict[str, Any], *, pr: Callable[[str], None], du: Any) -> None:
    """Print full skeptical audit (scope + follow-up); prefer split calls from research terminal."""
    print_scope_of_headline_score_terminal(bundle, pr=pr, du=du)
    print_skeptic_audit_followup_terminal(bundle, pr=pr, du=du)
