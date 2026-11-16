"""Figures: one function per figure; each writes PNG + SVG + the CSV behind it. Palette is readable on dark and light
backgrounds (Okabe-Ito). Platform markers come ONLY from the annotation file and are drawn as labeled vertical lines."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#999999"]


def load_annotations(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("causal_claim_permitted", False):
        raise ValueError("annotation file must not permit causal claims")
    return data


def _annotate(ax, annotations: dict | None, years_shown: tuple[int, int]) -> None:
    if not annotations:
        return
    for ev in annotations.get("events", []):
        if years_shown[0] <= ev["year"] <= years_shown[1]:
            ax.axvline(ev["year"], color="#999999", linestyle=":", linewidth=1)
            ax.text(ev["year"], ax.get_ylim()[1], ev["label"], rotation=90, fontsize=6, va="top", ha="right", color="#666666")


def _save(fig, out: Path, name: str, table: pd.DataFrame) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out / f"{name}.png", dpi=130, facecolor="white"); fig.savefig(out / f"{name}.svg", facecolor="white"); plt.close(fig)
    table.to_csv(out / f"{name}.csv", index=False)
    return {"png": f"{name}.png", "svg": f"{name}.svg", "csv": f"{name}.csv"}


def fig_rows_clusters(table: pd.DataFrame, out: Path, name: str = "T1_rows_clusters") -> dict:
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(table["year"], table["rows"], color=PALETTE[5], label="rows"); ax.bar(table["year"], table["clusters"], color=PALETTE[0], label="distinct permission profiles")
    ax.bar(table["year"], table["resigned_2017_rows"], color=PALETTE[3], label="re-signed 2017 corpus")
    ax.set_xlabel("first-submission year"); ax.set_ylabel("detected malware"); ax.legend(); ax.set_title("T1 detected malware per year")
    return _save(fig, out, name, table)


def fig_prevalence_lines(table: pd.DataFrame, out: Path, name: str, annotations: dict | None = None, value_col: str = "weighted_prevalence", title: str = "") -> dict:
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (perm, g) in enumerate(table.groupby("permission")):
        c = PALETTE[i % len(PALETTE)]; ax.plot(g["year"], g[value_col], marker="o", color=c, label=perm.replace("android.permission.", ""))
        if "lo95" in g and g["lo95"].notna().any():
            ax.fill_between(g["year"], g["lo95"], g["hi95"], color=c, alpha=0.12)
    ax.set_ylim(0, 1)
    numeric_axis = pd.to_numeric(table["year"], errors="coerce").notna().all()
    if annotations and numeric_axis:
        _annotate(ax, annotations, (int(table["year"].min()), int(table["year"].max())))
    ax.set_xlabel("first-submission year" if numeric_axis else "axis level"); ax.set_ylabel(value_col.replace("_", " ")); ax.legend(fontsize=6, ncol=2); ax.set_title(title or name)
    return _save(fig, out, name, table)


def fig_matched(table: pd.DataFrame, out: Path, name: str = "T4_matched", title: str = "T4 matched benign vs malware") -> dict:
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (perm, g) in enumerate(table.groupby("permission")):
        c = PALETTE[i % len(PALETTE)]; lab = perm.replace("android.permission.", "")
        ax.plot(g["year"], g["malware"], marker="o", color=c, label=f"{lab} malware"); ax.plot(g["year"], g["benign"], marker="x", linestyle="--", color=c, label=f"{lab} benign")
    ax.set_ylim(0, 1); ax.set_xlabel("first-submission year"); ax.legend(fontsize=5, ncol=3); ax.set_title(title)
    return _save(fig, out, name, table)


def fig_heatmap(table: pd.DataFrame, out: Path, name: str, index: str, columns: str, values: str, title: str) -> dict:
    """Cells with no measurement stay missing (hatched grey), never zero. The CSV behind the figure keeps NaN for them."""
    import numpy as np
    piv = table.pivot_table(index=index, columns=columns, values=values, aggfunc="first")
    fig, ax = plt.subplots(figsize=(10, max(3, 0.25 * len(piv))))
    data = np.ma.masked_invalid(piv.to_numpy(dtype=float)); cmap = plt.get_cmap("viridis").with_extremes(bad="#dddddd")
    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=0, vmax=1); ax.set_yticks(range(len(piv.index))); ax.set_yticklabels([str(x).replace("android.permission.", "") for x in piv.index], fontsize=7)
    ax.set_xticks(range(len(piv.columns))); ax.set_xticklabels(piv.columns, fontsize=7, rotation=45); fig.colorbar(im); ax.set_title(title + " (grey = not measured)")
    flat = piv.reset_index().melt(id_vars=index, var_name=columns, value_name=values)
    return _save(fig, out, name, flat)


def fig_jsd(table: pd.DataFrame, out: Path, name: str = "T6_jsd", highlight: tuple[str, str] = ("banker", "rat")) -> dict:
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, ((a, b), g) in enumerate(table.groupby(["type_a", "type_b"])):
        hl = {a, b} == set(highlight); ax.plot(g["year"], g["js_distance"], marker="o" if hl else ".", linewidth=2.5 if hl else 0.7, color=PALETTE[3] if hl else PALETTE[i % len(PALETTE)], alpha=1 if hl else 0.6, label=f"{a}-{b}")
    ax.set_ylim(0, 1); ax.set_xlabel("first-submission year"); ax.set_ylabel("Jensen-Shannon distance (base 2)"); ax.legend(fontsize=5, ncol=3); ax.set_title("T6 type convergence")
    return _save(fig, out, name, table)


def fig_concentration(table: pd.DataFrame, out: Path, name: str = "T7_concentration") -> dict:
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(table["year"], table["top10_signer_share"], marker="o", color=PALETTE[0], label="top-10 signer share"); ax.plot(table["year"], table["top10_profile_share"], marker="s", color=PALETTE[1], label="top-10 profile share")
    ax.plot(table["year"], table["signer_herfindahl"], linestyle="--", color=PALETTE[0], label="signer HHI"); ax.plot(table["year"], table["profile_herfindahl"], linestyle="--", color=PALETTE[1], label="profile HHI")
    ax.plot(table["year"], table["test_key_share"], linestyle="-.", color=PALETTE[3], label="test-key share")
    ax.set_ylim(0, 1); ax.set_xlabel("first-submission year"); ax.legend(fontsize=7); ax.set_title("T7 signer and profile concentration")
    return _save(fig, out, name, table)


def fig_scorecard(table: pd.DataFrame, out: Path, name: str = "scorecard") -> dict:
    fig, ax = plt.subplots(figsize=(10, 2.8)); ax.axis("off")
    cells = [[r["prediction"], r["verdict"], str(r["decided_by"])[:70]] for _, r in table.iterrows()]
    tbl = ax.table(cellText=cells, colLabels=["prediction", "verdict", "decided by"], loc="center"); tbl.auto_set_font_size(False); tbl.set_fontsize(8); ax.set_title("pre-registered scorecard")
    return _save(fig, out, name, table)
