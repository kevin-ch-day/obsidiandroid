"""Simple baselines vs ML Macro-F1 (same label column as primary training)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd


def _find_split_audit(diagnostics_dir: Path, run_id: str) -> Path | None:
    for name in (
        f"split_freeze_audit_{run_id}.csv",
        "split_freeze_audit.latest.csv",
    ):
        p = diagnostics_dir / name
        if p.exists():
            return p
    return None


def _baseline_majority_macro_f1(y_true: pd.Series, y_majority: Any) -> float | None:
    try:
        from sklearn.metrics import f1_score

        preds = pd.Series([y_majority] * len(y_true), index=y_true.index)
        return float(f1_score(y_true.astype(str), preds.astype(str), average="macro"))
    except Exception:
        return None


def _baseline_random_stratified_macro_f1(y_true: pd.Series, train_labels: pd.Series, seed: int = 42) -> float | None:
    """Predict test labels by IID draws from empirical train distribution."""
    try:
        import numpy as np
        from sklearn.metrics import f1_score

        rng = np.random.default_rng(seed)
        probs = train_labels.value_counts(normalize=True)
        classes = probs.index.to_numpy()
        p = probs.values.astype(float)
        draw = rng.choice(classes, size=len(y_true), p=p / p.sum())
        preds = pd.Series(draw, index=y_true.index)
        return float(f1_score(y_true.astype(str), preds.astype(str), average="macro"))
    except Exception:
        return None


def _type_majority_then_family_baseline(
    test_frame: pd.DataFrame,
    train_frame: pd.DataFrame,
    family_col: str = "family_canonical",
    type_col: str = "type_slug",
) -> float | None:
    """Given train/test with family+type, predict on test the mode family within each test row's type_slug from train."""
    try:
        from sklearn.metrics import f1_score

        if family_col not in test_frame.columns or type_col not in test_frame.columns:
            return None
        modes = train_frame.groupby(type_col)[family_col].agg(lambda s: s.mode().iloc[0] if len(s.mode()) else s.iloc[0])
        preds = test_frame[type_col].map(modes.to_dict()).fillna(test_frame[family_col].mode().iloc[0])
        return float(
            f1_score(
                test_frame[family_col].astype(str),
                preds.astype(str),
                average="macro",
            )
        )
    except Exception:
        return None


def write_baseline_comparison(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
) -> tuple[Path | None, Path | None]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    split_path = _find_split_audit(diagnostics_dir, run_id)

    csv_path = diagnostics_dir / "baseline_comparison.csv"
    md_path = diagnostics_dir / "baseline_comparison.md"

    rows: list[dict[str, Any]] = []

    model_rows: dict[str, float] = {}
    comp_path = diagnostics_dir / f"model_comparison_summary_{run_id}.csv"
    if not comp_path.exists():
        alt = diagnostics_dir / "model_comparison_summary.latest.csv"
        if alt.exists():
            comp_path = alt
    if comp_path.exists():
        try:
            mcdf = pd.read_csv(comp_path)
            if not mcdf.empty and "Model" in mcdf.columns and "Macro-F1 Score" in mcdf.columns:
                model_rows = {
                    str(r["Model"]): float(r["Macro-F1 Score"])
                    for _, r in mcdf.iterrows()
                    if pd.notna(r["Macro-F1 Score"])
                }
        except Exception:
            pass

    if split_path is None or samples_df is None or samples_df.empty or not split_path.exists():
        stub = "Missing split_audit or samples_df — cannot derive label baselines on this runner."
        csv_path.write_text(f"status,notes\nstub,{stub}\n", encoding="utf-8")
        md_path.write_text(f"# Baseline comparison\n\n{stub}\n", encoding="utf-8")
        return csv_path, md_path

    try:
        split_df = pd.read_csv(split_path)
        sid_col = "sample_id"
        if sid_col not in split_df.columns or "split_role" not in split_df.columns:
            raise ValueError("split audit missing columns")
        label_col = (
            "family_canonical"
            if "family_canonical" in split_df.columns
            else ("family_id" if "family_id" in split_df.columns else None)
        )
        if label_col is None:
            raise ValueError("split audit missing label column")

        samples = samples_df.copy()
        samples[sid_col] = pd.to_numeric(samples[sid_col], errors="coerce")
        split_df[sid_col] = pd.to_numeric(split_df[sid_col], errors="coerce")
        merged = split_df.merge(samples, on=sid_col, how="left", suffixes=("", "_cohort"))
        train_m = merged[merged["split_role"] == "train"]
        test_m = merged[merged["split_role"] == "test"]
        if train_m.empty or test_m.empty:
            raise ValueError("empty train or test in split audit")

        y_train = train_m[label_col]
        y_test = test_m[label_col]
        majority = y_train.mode().iloc[0]
        maj_f1 = _baseline_majority_macro_f1(y_test, majority)
        rand_f1 = _baseline_random_stratified_macro_f1(y_test, y_train)

        rows.append(
            {
                "baseline_name": "majority_class_train",
                "metric": "macro_f1",
                "value": maj_f1,
                "label_column": label_col,
                "population": f"test_n={len(test_m)} from split audit",
            }
        )
        rows.append(
            {
                "baseline_name": "random_iid_train_distribution",
                "metric": "macro_f1_mean_seed42",
                "value": rand_f1,
                "label_column": label_col,
                "population": f"test_n={len(test_m)}",
            }
        )

        if (
            label_col == "family_canonical"
            and "type_slug" in train_m.columns
            and "type_slug" in test_m.columns
        ):
            type_fam = _type_majority_then_family_baseline(test_m, train_m)
            rows.append(
                {
                    "baseline_name": "type_conditional_train_mode_family",
                    "metric": "macro_f1",
                    "value": type_fam,
                    "label_column": label_col,
                    "population": f"test_n={len(test_m)}",
                }
            )

        for model_key, mf1 in sorted(model_rows.items(), key=lambda x: -x[1]):
            if maj_f1 is not None:
                rows.append(
                    {
                        "baseline_name": f"lift_vs_majority[{model_key}]",
                        "metric": "delta_macro_f1",
                        "value": round(mf1 - maj_f1, 6),
                        "label_column": label_col,
                        "population": f"model Macro-F1 minus majority baseline ({maj_f1})",
                    }
                )
            break
    except Exception as exc:
        rows.append({"baseline_name": "error", "metric": "", "value": None, "label_column": "", "population": str(exc)})

    fieldnames = ["baseline_name", "metric", "value", "label_column", "population"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    lines = [
        "# Baseline comparison",
        "",
        "Macro-F1 baselines compare to the **test split declared in split_freeze_audit** merged with cohort labels.",
        "They do **not** reproduce post-low-support training label filtering unless that filtering is mirrored in cohort rows.",
        "",
        "| baseline | Macro-F1 (or Δ) | population |",
        "|----------|-----------------|------------|",
    ]
    for r in rows:
        if r.get("baseline_name"):
            lines.append(
                f"| {r.get('baseline_name')} | `{r.get('value')}` | {r.get('population')} |"
            )

    vendor_note = (
        "\n---\n**Vendor parsed-family oracle baseline**: not computed here "
        "(requires per-sample deterministic vendor-argmax family string join — add if you expose that table).\n\n"
        "**Permission-count-only baseline**: omit (weak proxy); extend with binned ``perm__total_count`` logistic if needed.\n"
    )
    md_path.write_text("\n".join(lines) + vendor_note, encoding="utf-8")
    return csv_path, md_path
