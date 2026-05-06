"""Headline vs ablation ``full_fused`` feature-contract parity (shared helpers)."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _prefer_run_scoped(paths: list[Path], run_id: str) -> Path | None:
    tagged = [p for p in paths if run_id in p.name]
    if tagged:
        return sorted(tagged, key=lambda p: len(p.name), reverse=True)[0]
    return paths[0] if paths else None


def read_evaluation_contract(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    """Load ``evaluation_contract`` JSON when manifest finalization has written it."""
    for name in (f"evaluation_contract_{run_id}.json", "evaluation_contract.latest.json"):
        p = diagnostics_dir / name
        if not p.is_file():
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            return blob if isinstance(blob, dict) else {}
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def read_headline_feature_column_hash(
    diagnostics_dir: Path,
    run_id: str,
    *,
    runtime_hash: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve headline matrix hash: runtime > evaluation_contract > model_comparison CSV."""
    rh = (runtime_hash or "").strip()
    if rh:
        return rh, "runtime_headline_feature_column_hash"

    ec = read_evaluation_contract(diagnostics_dir, run_id)
    fc = ec.get("feature_contract") if isinstance(ec, dict) else None
    if isinstance(fc, dict):
        h = fc.get("headline_feature_column_hash")
        if isinstance(h, str) and h.strip():
            return h.strip(), "evaluation_contract_json"

    globs = sorted(
        diagnostics_dir.glob("model_comparison_summary*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    path = _prefer_run_scoped(globs, run_id)
    if path is None or not path.is_file():
        return None, None
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None, str(path)
    if not rows:
        return None, str(path)
    h = rows[0].get("headline_feature_column_hash")
    if isinstance(h, str) and h.strip():
        return h.strip(), str(path)
    return None, str(path)


def read_ablation_full_fused_feature_column_hash(
    diagnostics_dir: Path, run_id: str
) -> tuple[str | None, str | None]:
    """Hash from ablation grid row ``full_fused`` × ``family_canonical_default``."""
    globs = sorted(
        diagnostics_dir.glob("ablation_summary*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    path = _prefer_run_scoped(globs, run_id)
    if path is None or not path.is_file():
        return None, None
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None, str(path)
    for r in rows:
        if str(r.get("experiment") or "").strip() != "full_fused":
            continue
        if str(r.get("label_target") or "").strip() != "family_canonical_default":
            continue
        h = r.get("feature_column_hash")
        if isinstance(h, str) and h.strip():
            return h.strip(), str(path)
    return None, str(path)


def build_feature_contract_comparison(
    diagnostics_dir: Path,
    run_id: str,
    *,
    manifest_context: Mapping[str, Any] | None = None,
    runtime_headline_hash: str | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable contract comparison record."""
    headline_hash, headline_src = read_headline_feature_column_hash(
        diagnostics_dir, run_id, runtime_hash=runtime_headline_hash
    )
    ablation_hash, ablation_src = read_ablation_full_fused_feature_column_hash(diagnostics_dir, run_id)

    split_hash = ""
    label_target = ""
    if isinstance(manifest_context, dict):
        sp = manifest_context.get("split")
        if isinstance(sp, dict):
            split_hash = str(sp.get("split_hash") or "").strip()
        la = manifest_context.get("label_authority")
        if isinstance(la, dict):
            disp = str(la.get("display_label_field") or "").strip()
            train = str(la.get("training_label_field") or "").strip()
            if disp or train:
                label_target = f"display={disp}; train={train}"

    ec = read_evaluation_contract(diagnostics_dir, run_id)
    sc = ec.get("split_contract") if isinstance(ec, dict) else None
    if isinstance(sc, dict) and not split_hash:
        split_hash = str(sc.get("split_hash") or "").strip()
    if not label_target and isinstance(ec, dict):
        la_ec = ec.get("label_authority")
        if isinstance(la_ec, dict):
            disp = str(la_ec.get("display_label_field") or "").strip()
            train = str(la_ec.get("training_label_field") or "").strip()
            active_n = la_ec.get("active_training_classes")
            parts: list[str] = []
            if disp or train:
                parts.append(f"display={disp or '—'}; train={train or '—'}")
            if active_n is not None:
                parts.append(f"active_training_classes={active_n}")
            label_target = " | ".join(parts)

    apples: bool | None
    if headline_hash and ablation_hash:
        apples = headline_hash == ablation_hash
    else:
        apples = None

    incommensurable_msg = (
        "Headline model and ablation full_fused are not directly comparable because feature contracts differ."
    )

    return {
        "run_id": run_id,
        "headline_feature_column_hash": headline_hash,
        "headline_hash_source": headline_src,
        "ablation_full_fused_feature_column_hash": ablation_hash,
        "ablation_summary_source": ablation_src,
        "split_hash": split_hash,
        "label_target": label_target,
        "apples_to_apples": apples,
        "incommensurable_message": incommensurable_msg,
    }


__all__ = [
    "build_feature_contract_comparison",
    "read_ablation_full_fused_feature_column_hash",
    "read_evaluation_contract",
    "read_headline_feature_column_hash",
]
