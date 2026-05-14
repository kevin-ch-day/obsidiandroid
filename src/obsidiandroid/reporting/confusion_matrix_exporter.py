# Purpose : Exports high-quality confusion matrix visualizations as PNG images
# Usage   : Used by model evaluation and training comparison utilities

from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from obsidiandroid.cli.ui import display as du

# === Constants ===
# Legacy default when callers omit ``output_path`` (prefer run-scoped paths from export_manager).
DIR_CONFUSION_MATRICES = Path("output/conf_matrices")
DEFAULT_FIGSIZE = (14, 10)
DEFAULT_DPI = 300

COLOR_PALETTE = "YlGnBu"  # High-contrast blue-green colormap
BWMODE_PALETTE = "Greys"  # Print-safe grayscale

ANNOT_KWARGS = {"size": 10, "weight": "bold"}


# === Export Confusion Matrix Image ===
def export_confusion_matrix_image(
    cm: np.ndarray,
    class_labels: List[str],
    model_name: str,
    output_path: Optional[Path] = None,
    color_mode: Literal["color", "bw"] = "color",
    title: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    verbose: bool = True,
) -> str:
    # Sanitize model name to prevent double-prefix and file extension issues
    clean_name = str(model_name).strip().lower()
    if clean_name.startswith("confusion_matrix_"):
        clean_name = clean_name.replace("confusion_matrix_", "")
    if clean_name.endswith(".png"):
        clean_name = clean_name.replace(".png", "")

    # Final output path (mkdir only the directory we actually write to).
    output_path = output_path or DIR_CONFUSION_MATRICES / f"confusion_matrix_{clean_name}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Choose appropriate colormap
    cmap = COLOR_PALETTE if color_mode == "color" else BWMODE_PALETTE
    chart_title = title or f"Confusion Matrix - {model_name.upper()}"

    # Render and save the figure
    try:
        _render_confusion_matrix_plot(cm, class_labels, chart_title, cmap)
        plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
        plt.close("all")
        if verbose:
            du.print_success(f"Confusion matrix saved to: {output_path}")
        return str(output_path)
    except Exception as e:
        du.print_error(f"[EXPORT FAILED] {type(e).__name__}: {e}")
        return ""


# === Render Confusion Matrix Plot (Internal Use Only) ===
def _render_confusion_matrix_plot(
    cm: np.ndarray,
    class_labels: List[str],
    title: Optional[str],
    cmap: str,
):
    # Set up figure
    plt.figure(figsize=DEFAULT_FIGSIZE)

    # Determine threshold for text color
    vmax = np.max(cm) if np.max(cm) > 0 else 1
    threshold = vmax * 0.6

    # Plot heatmap
    ax = sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap=cmap,
        xticklabels=class_labels,
        yticklabels=class_labels,
        linewidths=0.5,
        linecolor="gray",
        cbar=True,
        square=True,
        annot_kws=ANNOT_KWARGS,
    )

    # Adaptive text color inside cells
    for text in ax.texts:
        value = text.get_text()
        try:
            numeric = int(value)
            text.set_color("white" if numeric > threshold else "black")
        except ValueError:
            pass

    # Configure axis and title
    plt.title(title, fontsize=16, weight="bold", pad=20)
    plt.xlabel("Predicted Family", fontsize=13, labelpad=10)
    plt.ylabel("True Family", fontsize=13, labelpad=10)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right", fontsize=10)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=10)
    plt.tight_layout()
    plt.grid(False)


# === Preview in Notebooks (Optional Debug Tool) ===
def preview_confusion_matrix_inline(
    cm: np.ndarray,
    class_labels: List[str],
    color_mode: Literal["color", "bw"] = "color",
    title: str = "Confusion Matrix Preview",
):
    # Inline preview of confusion matrix (Jupyter or notebook use)
    cmap = COLOR_PALETTE if color_mode == "color" else BWMODE_PALETTE
    _render_confusion_matrix_plot(cm, class_labels, title, cmap)
    plt.show()


__all__ = [
    "export_confusion_matrix_image",
    "preview_confusion_matrix_inline",
]
