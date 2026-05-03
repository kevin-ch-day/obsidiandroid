"""Matplotlib/PIL helpers for strict paper export figures (Paper #2 pack)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _strip_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with whitespace-stripped column labels (common CSV/Excel issue)."""
    out = df.copy()
    out.columns = pd.Index([str(c).strip() for c in out.columns])
    return out


def _first_column_match(columns: pd.Index, candidates: tuple[str, ...]) -> str:
    """Return the first present column name, compared case-insensitively after strip."""
    lower_to_actual = {str(c).strip().lower(): str(c).strip() for c in columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lower_to_actual:
            return lower_to_actual[key]
    return ""


def render_pipeline_architecture_figure(*, output_path: Path) -> None:
    """Render compact pipeline architecture figure for paper exports."""
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"")
        return
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]

    steps = [
        "Cohort Selection",
        "Permission Extraction",
        "Feature Engineering",
        "Model Training (RF/XGB/LR)",
        "Evaluation + Exports",
    ]
    fig, ax = plt.subplots(figsize=(7.16, 2.4))
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0.01, 0.12), 0.43, 0.76, transform=ax.transAxes, color="#e6f2ff", zorder=0, ec="none"))
    ax.add_patch(plt.Rectangle((0.44, 0.12), 0.24, 0.76, transform=ax.transAxes, color="#fff2e6", zorder=0, ec="none"))
    ax.add_patch(plt.Rectangle((0.68, 0.12), 0.31, 0.76, transform=ax.transAxes, color="#e8f7eb", zorder=0, ec="none"))
    x_positions = [0.05, 0.25, 0.45, 0.67, 0.87]
    for idx, (xpos, label) in enumerate(zip(x_positions, steps)):
        ax.text(
            xpos,
            0.55,
            label,
            ha="center",
            va="center",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "#f6f8fb", "edgecolor": "#2f4f4f"},
            transform=ax.transAxes,
        )
        if idx < len(x_positions) - 1:
            ax.annotate(
                "",
                xy=(x_positions[idx + 1] - 0.08, 0.55),
                xytext=(xpos + 0.08, 0.55),
                arrowprops={"arrowstyle": "->", "lw": 1.0, "color": "#2f4f4f"},
                xycoords=ax.transAxes,
                textcoords=ax.transAxes,
            )
    ax.text(0.22, 0.16, "Data Preparation", ha="center", va="center", fontsize=8, color="#2a4365", transform=ax.transAxes)
    ax.text(0.56, 0.16, "Structural Analysis", ha="center", va="center", fontsize=8, color="#7b341e", transform=ax.transAxes)
    ax.text(0.84, 0.16, "ML Validation", ha="center", va="center", fontsize=8, color="#22543d", transform=ax.transAxes)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def render_paper_type_heatmap_from_table(
    *,
    type_prevalence_path: Path,
    discriminability_path: Path,
    output_path: Path,
    top_permissions: int,
) -> bool:
    """Render publication-style type permission heatmap from run-scoped tables."""
    if not type_prevalence_path.exists():
        return False
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        return False
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    try:
        df = pd.read_csv(type_prevalence_path)
    except Exception:
        return False
    required = {"type_slug", "permission", "prevalence"}
    if df.empty or not required.issubset(df.columns):
        return False
    df = df.copy()
    df["type_slug"] = df["type_slug"].fillna("").astype(str).str.strip().str.lower()
    df["permission"] = df["permission"].fillna("").astype(str).str.strip()
    df["prevalence"] = pd.to_numeric(df["prevalence"], errors="coerce").fillna(0.0)
    df = df[(df["type_slug"] != "") & (df["permission"] != "")]
    if df.empty:
        return False

    selected_permissions: list[str] = []
    if discriminability_path.exists():
        try:
            rank_df = pd.read_csv(discriminability_path)
            if "permission" in rank_df.columns:
                selected_permissions = (
                    rank_df["permission"].fillna("").astype(str).str.strip().loc[lambda s: s != ""].head(max(top_permissions, 1)).tolist()
                )
        except Exception:
            selected_permissions = []
    if not selected_permissions:
        selected_permissions = (
            df.groupby("permission", as_index=False)["prevalence"]
            .mean()
            .sort_values(by=["prevalence", "permission"], ascending=[False, True], kind="mergesort")
            .head(max(top_permissions, 1))["permission"]
            .astype(str)
            .tolist()
        )
    plot_df = df[df["permission"].isin(set(selected_permissions))].copy()
    if plot_df.empty:
        return False
    pivot = plot_df.pivot_table(index="type_slug", columns="permission", values="prevalence", fill_value=0.0)
    type_order = ["banker", "adware", "stealer", "sms-trojan", "rat", "spyware", "ransomware"]
    ordered_rows = [name for name in type_order if name in pivot.index] + [name for name in pivot.index if name not in type_order]
    pivot = pivot.reindex(index=ordered_rows)

    fig, ax = plt.subplots(figsize=(7.16, 3.8))
    im = ax.imshow(pivot.values, aspect="auto", cmap="Reds", vmin=0, vmax=1, interpolation="nearest")
    compact_cols = [str(col).split(".")[-1] for col in pivot.columns]
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(compact_cols, rotation=75, ha="right", fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index.tolist(), fontsize=9)
    ax.set_xlabel("Permission", fontsize=10)
    ax.set_ylabel("Malware Type", fontsize=10)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_xticks(np.arange(-0.5, len(pivot.columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(pivot.index), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=0.25, alpha=0.4)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Prevalence", rotation=90, fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    def permission_group(token: str) -> str:
        t = str(token).lower()
        if "sms" in t:
            return "SMS"
        if "contact" in t or "account" in t:
            return "Contacts"
        if "storage" in t or "external" in t or "media" in t:
            return "Storage"
        if "phone" in t or "call" in t:
            return "Phone"
        if "accessibility" in t or "overlay" in t or "install" in t or "boot" in t:
            return "System"
        return "Other"

    group_positions: dict[str, list[int]] = {}
    for idx, col in enumerate(pivot.columns.tolist()):
        group_positions.setdefault(permission_group(str(col).split(".")[-1]), []).append(idx)
    for group, positions in group_positions.items():
        if not positions:
            continue
        mid = (min(positions) + max(positions)) / max(len(pivot.columns) - 1, 1)
        ax.text(
            mid,
            1.08,
            group,
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=8,
            color="#333333",
        )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return True


def render_paper_dangerous_distribution_from_table(
    *,
    dangerous_distribution_path: Path,
    output_path: Path,
) -> bool:
    """Render publication-style dangerous permission distribution chart."""
    if not dangerous_distribution_path.exists():
        return False
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        return False
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    try:
        df = pd.read_csv(dangerous_distribution_path)
    except Exception:
        return False
    required = {"type_slug", "dangerous_count_strict_mean", "sample_count"}
    if df.empty or not required.issubset(df.columns):
        return False
    work = df.copy()
    work["type_slug"] = work["type_slug"].fillna("").astype(str).str.strip().str.lower()
    work["dangerous_count_strict_mean"] = pd.to_numeric(
        work["dangerous_count_strict_mean"], errors="coerce"
    ).fillna(0.0)
    work["sample_count"] = pd.to_numeric(work["sample_count"], errors="coerce").fillna(0).astype(int)
    work = work[work["type_slug"] != ""].copy()
    if work.empty:
        return False
    type_order = ["banker", "adware", "stealer", "sms-trojan", "rat", "spyware", "ransomware"]
    work["order"] = work["type_slug"].map({k: i for i, k in enumerate(type_order)}).fillna(99).astype(int)
    work = work.sort_values(by=["order", "type_slug"], ascending=[True, True], kind="mergesort")

    labels = [f"{t}\n(n={n})" for t, n in zip(work["type_slug"], work["sample_count"])]
    strict_vals = work["dangerous_count_strict_mean"].tolist()
    unknown_vals = (
        pd.to_numeric(work.get("dangerous_count_unknown_component_mean", 0.0), errors="coerce")
        .fillna(0.0)
        .tolist()
    )
    inclusive_vals = (
        pd.to_numeric(work.get("dangerous_count_inclusive_mean", work["dangerous_count_strict_mean"]), errors="coerce")
        .fillna(0.0)
        .tolist()
    )

    fig, ax = plt.subplots(figsize=(7.16, 3.8))
    x = np.arange(len(labels))
    width = 0.7
    b_strict = ax.bar(x, strict_vals, width, color="#c53030", label="Strict Dangerous")
    b_unknown = ax.bar(
        x,
        unknown_vals,
        width,
        bottom=np.array(strict_vals),
        color="#718096",
        label="Unknown-Protection Component",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Mean Dangerous Permission Count", fontsize=10)
    ax.set_xlabel("Malware Type", fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.3, linewidth=0.6)
    ax.legend(
        [b_strict, b_unknown],
        ["Strict Dangerous", "Unknown-Protection Component"],
        ncol=2,
        fontsize=7,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        frameon=False,
    )
    ax.tick_params(axis="y", labelsize=8)
    for idx, val in enumerate(inclusive_vals):
        ax.text(idx, val + 0.04, f"{val:.2f}", ha="center", va="bottom", fontsize=7)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return True


def render_paper_jsd_heatmap_from_pairs(
    *,
    jsd_pair_path: Path,
    output_path: Path,
) -> bool:
    """Render publication-style family JSD heatmap from compact pair table."""
    if not jsd_pair_path.exists():
        return False
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        return False
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    try:
        pairs = pd.read_csv(jsd_pair_path)
    except Exception:
        return False
    required = {"family_a", "family_b", "js_distance"}
    if pairs.empty or not required.issubset(pairs.columns):
        return False
    work = pairs.copy()
    work["family_a"] = work["family_a"].fillna("").astype(str).str.strip()
    work["family_b"] = work["family_b"].fillna("").astype(str).str.strip()
    work["js_distance"] = pd.to_numeric(work["js_distance"], errors="coerce").fillna(0.0)
    work = work[(work["family_a"] != "") & (work["family_b"] != "")]
    if work.empty:
        return False
    families = sorted(set(work["family_a"].tolist()) | set(work["family_b"].tolist()))
    idx = {name: pos for pos, name in enumerate(families)}
    matrix = np.zeros((len(families), len(families)), dtype=float)
    for _, row in work.iterrows():
        i = idx[str(row["family_a"])]
        j = idx[str(row["family_b"])]
        val = float(row["js_distance"])
        matrix[i, j] = val
        matrix[j, i] = val
    order = list(range(len(families)))
    try:
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import squareform

        dist_vec = squareform(matrix, checks=False)
        link = linkage(dist_vec, method="average")
        order = leaves_list(link).tolist()
    except Exception:
        order = list(range(len(families)))
    ordered_families = [families[i] for i in order]
    ordered_matrix = matrix[np.ix_(order, order)]

    fig, ax = plt.subplots(figsize=(7.16, 6.0))
    im = ax.imshow(ordered_matrix, aspect="equal", cmap="coolwarm", vmin=0, vmax=1, interpolation="nearest")
    ax.set_xticks(range(len(ordered_families)))
    ax.set_xticklabels(ordered_families, rotation=70, ha="right", fontsize=8)
    ax.set_yticks(range(len(ordered_families)))
    ax.set_yticklabels(ordered_families, fontsize=8)
    ax.set_xlabel("Family", fontsize=10)
    ax.set_ylabel("Family", fontsize=10)
    ax.tick_params(axis="both", labelsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("JSD", rotation=90, fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return True


def export_paper_figure_qc(*, fig_dir: Path, output_path: Path) -> Path:
    """Export simple figure QC report (dimensions and DPI metadata)."""
    rows: list[dict[str, Any]] = []
    try:
        from PIL import Image
    except Exception:
        Image = None  # type: ignore[assignment]
    for fig_path in sorted(fig_dir.glob("*.png")):
        row = {
            "figure_name": fig_path.name,
            "width_px": "",
            "height_px": "",
            "dpi_x": "",
            "dpi_y": "",
        }
        if Image is not None:
            try:
                with Image.open(fig_path) as im:
                    row["width_px"] = int(im.width)
                    row["height_px"] = int(im.height)
                    dpi = im.info.get("dpi")
                    if isinstance(dpi, tuple) and len(dpi) >= 2:
                        row["dpi_x"] = round(float(dpi[0]), 4)
                        row["dpi_y"] = round(float(dpi[1]), 4)
            except Exception:
                pass
        rows.append(row)
    qc_df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_df.to_csv(output_path, index=False)
    return output_path


def annotate_confusion_matrix_with_metrics(
    *,
    confusion_path: Path,
    model_comparison_csv: Path,
) -> bool:
    """Annotate exported confusion matrix with compact model metrics."""
    if not confusion_path.exists() or not model_comparison_csv.exists():
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return False
    try:
        model_df = pd.read_csv(model_comparison_csv)
    except Exception:
        return False
    work = _strip_column_names(model_df)
    if work.empty:
        return False
    model_col = _first_column_match(work.columns, ("Model", "model"))
    if not model_col:
        return False
    work[model_col] = work[model_col].fillna("").astype(str).str.strip().str.lower()
    row = work[work[model_col].isin({"rf", "random_forest"})].head(1)
    if row.empty:
        return False
    acc_col = _first_column_match(
        work.columns,
        ("Accuracy", "Acc", "accuracy"),
    )
    macro_col = _first_column_match(
        work.columns,
        ("Macro F1-Score", "MacroF1", "Macro F1", "macro_f1", "macro_f1_score"),
    )
    f1_col = _first_column_match(
        work.columns,
        ("F1-Score", "F1", "Weighted F1", "Weighted-F1", "weighted_f1"),
    )
    if not acc_col or not macro_col:
        return False
    acc = float(pd.to_numeric(row.iloc[0][acc_col], errors="coerce"))
    macro = float(pd.to_numeric(row.iloc[0][macro_col], errors="coerce"))
    if not np.isfinite(acc) or not np.isfinite(macro):
        return False
    f1_val: float | None = None
    if f1_col:
        f1_raw = float(pd.to_numeric(row.iloc[0][f1_col], errors="coerce"))
        if np.isfinite(f1_raw):
            f1_val = f1_raw
    if f1_val is not None:
        summary = f"Accuracy={acc:.4f}  Macro-F1={macro:.4f}  Weighted-F1={f1_val:.4f}"
    else:
        summary = f"Accuracy={acc:.4f}  Macro-F1={macro:.4f}"

    try:
        with Image.open(confusion_path) as img:
            img = img.convert("RGB")
            banner_h = max(56, int(img.height * 0.07))
            canvas = Image.new("RGB", (img.width, img.height + banner_h), color=(255, 255, 255))
            canvas.paste(img, (0, banner_h))
            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype("arial.ttf", size=max(16, int(banner_h * 0.36)))
            except Exception:
                font = ImageFont.load_default()
            draw.text((16, int((banner_h - 18) / 2)), summary, fill=(20, 20, 20), font=font)
            canvas.save(confusion_path, dpi=(300, 300))
    except Exception:
        return False
    return True
