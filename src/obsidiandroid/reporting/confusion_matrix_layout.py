# Filename: src/obsidiandroid/reporting/confusion_matrix_layout.py
# Purpose: Hierarchical confusion-matrix paths, export-mode gating, and run catalog.

"""Confusion matrix output layout for reviewable experiment grids.

Maps ``RUNTIME_EXPERIMENT_ID`` values like ``vendor_full__lt_family_id`` into
folder segments, applies export density policy, and writes ``index.csv`` +
``README.md`` under ``conf_matrices/``.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import app_config

_SEGMENT_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _token(value: str) -> str:
    cleaned = _SEGMENT_SAFE.sub("_", str(value).strip())
    return cleaned.strip("_") or "unknown"


def parse_experiment_combo(experiment_id: str) -> tuple[str, str | None]:
    """Split ``vendor_full__lt_family_id`` → ``(vendor_full, family_id)``."""
    e = str(experiment_id or "").strip()
    if "__lt_" in e:
        fs, lt = e.split("__lt_", 1)
        return (_token(fs), _token(lt) if lt.strip() else None)
    if not e:
        return ("headline", None)
    return (_token(e), None)


def export_mode() -> str:
    """``full_grid`` | ``selected_ablation`` | ``headline_only`` (default)."""
    raw = str(getattr(app_config, "CONFUSION_MATRIX_EXPORT_MODE", "headline_only") or "").strip().lower()
    if raw in {"full_grid", "selected_ablation", "headline_only"}:
        return raw
    return "headline_only"


def headline_experiment_name() -> str:
    """Primary feature-set token for ``headline_only`` ablation exports."""
    return str(
        getattr(app_config, "CONFUSION_MATRIX_HEADLINE_EXPERIMENT", "vendor_no_parsed_family")
        or "vendor_no_parsed_family"
    ).strip()


SELECTED_ABLATION_EXPERIMENTS: frozenset[str] = frozenset(
    {
        "vendor_full",
        "vendor_no_parsed_family",
        "vendor_detection_binary_only",
        "vendor_consensus_scores_only",
        "permissions_raw",
        "permissions_grouped",
        "permissions_grouped_plus_vendor_no_family",
        "full_fused",
    }
)


def should_export_confusion_matrix(*, experiment_id: str) -> bool:
    """Return False when ablation grid should skip this cell (export mode)."""
    if not bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
        return True
    mode = export_mode()
    if mode == "full_grid":
        return True
    fs, lt = parse_experiment_combo(experiment_id)
    label = lt or "family_canonical_default"
    if mode == "headline_only":
        return fs == _token(headline_experiment_name()) and label == "family_id"
    if mode == "selected_ablation":
        return label == "family_id" and fs in SELECTED_ABLATION_EXPERIMENTS
    return True


def resolve_confusion_matrix_png_path(
    *,
    conf_matrices_dir: Path,
    model_name: str,
    experiment_id: str,
) -> Path:
    """Return destination path under ``conf_matrices_dir`` (creates parent segments only)."""
    model_t = _token(model_name)
    exp_raw = str(experiment_id or "").strip()
    if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
        fs, lt = parse_experiment_combo(experiment_id)
        label_dir = lt or "family_canonical_default"
        return conf_matrices_dir / "ablation" / fs / label_dir / f"{model_t}.png"
    if exp_raw:
        exp_t = _token(exp_raw)
        return conf_matrices_dir / f"confusion_matrix_{exp_t}__{model_t}.png"
    return conf_matrices_dir / "headline" / f"{model_t}.png"


def write_confusion_matrix_catalog(conf_matrices_dir: Path, *, run_id: str) -> tuple[Path | None, Path | None]:
    """Write ``index.csv`` and ``README.md`` summarizing matrices under this run."""
    if not conf_matrices_dir.is_dir():
        return None, None
    run = str(run_id or "").strip() or "unknown"
    rows: list[dict[str, Any]] = []
    for path in sorted(conf_matrices_dir.rglob("*.png")):
        rel = path.relative_to(conf_matrices_dir).as_posix()
        parts = path.relative_to(conf_matrices_dir).parts
        matrix_role = "legacy_flat"
        feature_set = ""
        label_target = ""
        model = ""
        is_headline = 0
        is_primary = 0
        if parts[0] == "headline" and len(parts) == 2:
            matrix_role = "headline"
            model = Path(parts[1]).stem
            is_headline = 1
            is_primary = int(model.lower() == "random_forest")
        elif parts[0] == "ablation" and len(parts) >= 4:
            matrix_role = "ablation"
            feature_set = parts[1]
            label_target = parts[2]
            model = Path(parts[3]).stem
        elif len(parts) == 1 and parts[0].startswith("confusion_matrix") and parts[0].endswith(".png"):
            matrix_role = "legacy_flat"
            stem = path.stem.replace("confusion_matrix_", "")
            if "__lt_" in stem:
                head, _, tail = stem.partition("__lt_")
                feature_set = head
                if "__" in tail:
                    label_target, _, model = tail.rpartition("__")
                else:
                    label_target, model = tail, ""
            elif "__" in stem:
                feature_set, _, model = stem.partition("__")
            else:
                model = stem
        try:
            stat = path.stat()
            size_b = int(stat.st_size)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            size_b = 0
            mtime = ""
        rows.append(
            {
                "run_id": run,
                "matrix_role": matrix_role,
                "feature_set": feature_set,
                "label_target": label_target,
                "model": model,
                "relative_path": rel,
                "is_headline": is_headline,
                "is_primary": is_primary,
                "is_alias": 0,
                "file_size_bytes": size_b,
                "modified_utc": mtime,
            }
        )
    index_path = conf_matrices_dir / "index.csv"
    fieldnames = [
        "run_id",
        "matrix_role",
        "feature_set",
        "label_target",
        "model",
        "relative_path",
        "is_headline",
        "is_primary",
        "is_alias",
        "file_size_bytes",
        "modified_utc",
    ]
    with index_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    readme = conf_matrices_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                f"# Confusion matrices (`run_id={run}`)",
                "",
                "## Layout",
                "",
                "- `headline/` — main training / headline evaluation (one PNG per model).",
                "- `ablation/<feature_set>/<label_target>/` — ablation grid cells.",
                "- Flat `confusion_matrix_*.png` files may remain from older runs or retention copies.",
                "",
                "- **`confusion_matrix_random_forest.png`** is only updated during main (non-ablation) "
                "training; it is the paper-facing headline RF alias and must not be overwritten by ablation exports.",
                "",
                "See `index.csv` for a machine-readable inventory of every PNG.",
                "",
                "## Export mode",
                "",
                f"Effective `CONFUSION_MATRIX_EXPORT_MODE`: **{export_mode()}** "
                "(profile `feature_flags.confusion_matrix_export_mode`).",
                "",
                "- `headline_only` — ablation emits only the primary feature set + `family_id`.",
                "- `selected_ablation` — `family_id` + a fixed set of feature-set experiments.",
                "- `full_grid` — every `(feature_set × label_target × model)` cell.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return index_path, readme


__all__ = [
    "export_mode",
    "headline_experiment_name",
    "parse_experiment_combo",
    "resolve_confusion_matrix_png_path",
    "should_export_confusion_matrix",
    "write_confusion_matrix_catalog",
    "SELECTED_ABLATION_EXPERIMENTS",
]
