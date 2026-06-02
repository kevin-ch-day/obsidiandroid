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

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.governance.family_tier_authority import (
    clean_tier_token,
    generic_coarse_token_set,
    major_family_name_set,
)
from obsidiandroid.governance.paper_family_display_policy import (
    paper_family_display_policy_payload,
)

# === Constants ===
# Legacy default when callers omit ``output_path`` (prefer run-scoped paths from export_manager).
DIR_CONFUSION_MATRICES = Path("output/conf_matrices")
DEFAULT_FIGSIZE = (14, 10)
DEFAULT_DPI = 300
LARGE_MATRIX_ANNOTATION_LIMIT = 24
DISPLAY_VARIANT_SUFFIX = "_display"

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
        _export_grouped_display_variant(
            cm=cm,
            class_labels=class_labels,
            output_path=output_path,
            chart_title=chart_title,
            cmap=cmap,
            dpi=dpi,
        )
        if verbose:
            du.print_success(f"[EXPORT] Confusion matrix:{du.format_console_path(output_path)}")
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
    render_profile = _render_profile(len(class_labels))
    plt.figure(figsize=render_profile["figsize"])

    # Determine threshold for text color
    vmax = np.max(cm) if np.max(cm) > 0 else 1
    threshold = vmax * 0.6

    # Plot heatmap
    ax = sns.heatmap(
        cm,
        annot=render_profile["annot"],
        fmt="d",
        cmap=cmap,
        xticklabels=class_labels,
        yticklabels=class_labels,
        linewidths=0.5,
        linecolor="gray",
        cbar=True,
        square=True,
        annot_kws=render_profile["annot_kws"],
    )

    # Adaptive text color inside cells
    if render_profile["annot"]:
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
    ax.set_xticklabels(
        ax.get_xticklabels(),
        rotation=render_profile["x_rotation"],
        ha="right",
        fontsize=render_profile["tick_fontsize"],
    )
    ax.set_yticklabels(
        ax.get_yticklabels(),
        rotation=0,
        fontsize=render_profile["tick_fontsize"],
    )
    plt.tight_layout()
    plt.grid(False)


def _render_profile(label_count: int) -> dict[str, object]:
    """Return adaptive rendering settings for one confusion matrix."""
    if label_count <= 12:
        return {
            "figsize": DEFAULT_FIGSIZE,
            "annot": True,
            "annot_kws": dict(ANNOT_KWARGS),
            "tick_fontsize": 10,
            "x_rotation": 45,
        }
    if label_count <= LARGE_MATRIX_ANNOTATION_LIMIT:
        scale = max(1.0, label_count / 12.0)
        return {
            "figsize": (min(20.0, 14.0 * scale), min(18.0, 10.0 * scale)),
            "annot": True,
            "annot_kws": {"size": 8, "weight": "bold"},
            "tick_fontsize": 8,
            "x_rotation": 60,
        }
    side = min(36.0, max(18.0, float(label_count) * 0.28))
    return {
        "figsize": (side, side),
        "annot": False,
        "annot_kws": {"size": 1},
        "tick_fontsize": max(4, int(10 - min(6, label_count / 18))),
        "x_rotation": 60,
    }


def display_variant_output_path(output_path: Path) -> Path:
    """Return the sibling output path for the display-optimized matrix variant."""
    path = Path(output_path)
    return path.with_name(f"{path.stem}{DISPLAY_VARIANT_SUFFIX}{path.suffix}")


def build_grouped_family_confusion_matrix(
    cm: np.ndarray,
    class_labels: List[str],
) -> tuple[np.ndarray, list[str]] | None:
    """Aggregate a family confusion matrix into paper-facing major/minor buckets."""
    training_label_field = str(
        getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "") or ""
    ).strip()
    if training_label_field != "family_id":
        return None

    policy = paper_family_display_policy_payload().get("family_confusion_matrix") or {}
    if not isinstance(policy, dict):
        return None

    threshold = int(policy.get("prefer_type_level_matrix_when_family_surface_exceeds", 25) or 25)
    if len(class_labels) <= threshold:
        return None

    major_names = major_family_name_set()
    generic_tokens = generic_coarse_token_set()
    normalized = [clean_tier_token(label, generic_tokens=set()) for label in class_labels]
    row_support = np.asarray(cm).sum(axis=1)
    top_k_major = max(1, int(policy.get("top_k_major_families", 12) or 12))

    major_indices = [idx for idx, token in enumerate(normalized) if token in major_names]
    major_indices = sorted(major_indices, key=lambda idx: (-row_support[idx], class_labels[idx]))
    kept_major_indices = set(major_indices[:top_k_major])

    other_major_label = str(policy.get("other_major_label", "Other Major") or "Other Major").strip()
    minor_label = str(policy.get("minor_long_tail_label", "Minor/Long-tail") or "Minor/Long-tail").strip()
    generic_label = str(policy.get("generic_coarse_label", "Generic/Coarse") or "Generic/Coarse").strip()
    unresolved_label = "Unresolved"

    grouped_order: list[str] = []
    grouped_members: dict[str, list[int]] = {}

    for idx, token in enumerate(normalized):
        if idx in kept_major_indices:
            bucket = class_labels[idx]
        elif token in major_names and bool(policy.get("group_other_major", True)):
            bucket = other_major_label
        elif token in generic_tokens and bool(policy.get("group_generic_coarse", True)):
            bucket = generic_label
        elif token:
            bucket = minor_label if bool(policy.get("group_minor_long_tail", True)) else class_labels[idx]
        else:
            bucket = unresolved_label
        if bucket not in grouped_members:
            grouped_members[bucket] = []
            grouped_order.append(bucket)
        grouped_members[bucket].append(idx)

    if len(grouped_order) >= len(class_labels):
        return None

    grouped_cm = np.zeros((len(grouped_order), len(grouped_order)), dtype=np.int64)
    for row_bucket, row_indices in grouped_members.items():
        row_pos = grouped_order.index(row_bucket)
        for col_bucket, col_indices in grouped_members.items():
            col_pos = grouped_order.index(col_bucket)
            grouped_cm[row_pos, col_pos] = int(np.asarray(cm)[np.ix_(row_indices, col_indices)].sum())
    return grouped_cm, grouped_order


def _export_grouped_display_variant(
    *,
    cm: np.ndarray,
    class_labels: List[str],
    output_path: Path,
    chart_title: str,
    cmap: str,
    dpi: int,
) -> Path | None:
    grouped = build_grouped_family_confusion_matrix(cm, class_labels)
    if grouped is None:
        return None
    grouped_cm, grouped_labels = grouped
    display_path = display_variant_output_path(output_path)
    _render_confusion_matrix_plot(
        grouped_cm,
        grouped_labels,
        f"{chart_title} (Display-Optimized)",
        cmap,
    )
    plt.savefig(display_path, dpi=dpi, bbox_inches="tight")
    plt.close("all")
    return display_path


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
    "build_grouped_family_confusion_matrix",
    "display_variant_output_path",
    "export_confusion_matrix_image",
    "preview_confusion_matrix_inline",
]
