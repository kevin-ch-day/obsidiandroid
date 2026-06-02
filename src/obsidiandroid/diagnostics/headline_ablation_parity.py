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


def _resolve_headline_feature_contract_path(
    diagnostics_dir: Path,
    run_id: str,
) -> Path | None:
    """Resolve the concrete feature-contract JSON path for the headline run."""
    ec = read_evaluation_contract(diagnostics_dir, run_id)
    fc = ec.get("feature_contract") if isinstance(ec, dict) else None
    if isinstance(fc, dict):
        raw = str(fc.get("headline_feature_contract_path") or "").strip()
        if raw:
            candidate = Path(raw)
            if candidate.is_file():
                return candidate
    for name in (f"feature_contract_{run_id}.json", "feature_contract.json", "feature_contract.latest.json"):
        candidate = diagnostics_dir / name
        if candidate.is_file():
            return candidate
    return None


def _summarize_headline_feature_modalities(
    diagnostics_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    """Summarize headline feature-column composition for parity interpretation."""
    path = _resolve_headline_feature_contract_path(diagnostics_dir, run_id)
    if path is None:
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(blob, dict):
        return {}
    columns = blob.get("feature_columns")
    if not isinstance(columns, list):
        return {}
    col_text = [str(col) for col in columns]
    permission_count = sum(
        1 for col in col_text
        if col.startswith("perm__") or col.startswith("perm_grp__") or col == "meta__permissions"
    )
    vendor_semantic_count = sum(
        1 for col in col_text
        if "parsed_family" in col.lower() or "threat_class" in col.lower() or "malware_type" in col.lower()
    )
    extra_non_vendor_permission_count = sum(
        1
        for col in col_text
        if not (
            col.startswith("perm__")
            or col.startswith("perm_grp__")
            or col == "meta__permissions"
            or "parsed_family" in col.lower()
            or "threat_class" in col.lower()
            or "malware_type" in col.lower()
            or col == "sample_id"
        )
    )
    return {
        "headline_feature_contract_path": str(path),
        "headline_permission_feature_count": int(permission_count),
        "headline_vendor_semantic_feature_count": int(vendor_semantic_count),
        "headline_extra_non_vendor_permission_feature_count": int(extra_non_vendor_permission_count),
    }


def read_ablation_full_fused_feature_column_hash(
    diagnostics_dir: Path,
    run_id: str,
    *,
    preferred_label_targets: list[str] | None = None,
) -> tuple[str | None, str | None]:
    """Hash from ablation grid row ``full_fused`` × preferred family label target."""
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
    targets = list(preferred_label_targets or ["family_id", "family_canonical_default"])
    matching_rows = [
        r for r in rows
        if str(r.get("experiment") or "").strip() == "full_fused"
    ]
    for target in targets:
        for r in matching_rows:
            if str(r.get("label_target") or "").strip() != target:
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
    preferred_targets = ["family_id", "family_canonical_default"]
    ec = read_evaluation_contract(diagnostics_dir, run_id)
    la_hint = ec.get("label_authority") if isinstance(ec, dict) else None
    training_field = ""
    if isinstance(manifest_context, dict):
        la = manifest_context.get("label_authority")
        if isinstance(la, dict):
            training_field = str(la.get("training_label_field") or "").strip()
    if not training_field and isinstance(la_hint, dict):
        training_field = str(la_hint.get("training_label_field") or "").strip()
    if training_field == "family_canonical":
        preferred_targets = ["family_canonical_default", "family_id"]
    elif training_field == "family_id":
        preferred_targets = ["family_id", "family_canonical_default"]
    ablation_hash, ablation_src = read_ablation_full_fused_feature_column_hash(
        diagnostics_dir,
        run_id,
        preferred_label_targets=preferred_targets,
    )
    modality_summary = _summarize_headline_feature_modalities(diagnostics_dir, run_id)

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
    extra_modalities = int(modality_summary.get("headline_extra_non_vendor_permission_feature_count", 0) or 0)
    if extra_modalities > 0:
        incommensurable_msg = (
            "Headline model and ablation full_fused are not directly comparable because the headline feature "
            f"contract includes {extra_modalities} additional non-vendor/non-permission feature column(s) "
            "beyond the ablation full_fused recipe."
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
        **modality_summary,
    }


__all__ = [
    "build_feature_contract_comparison",
    "read_ablation_full_fused_feature_column_hash",
    "read_evaluation_contract",
    "read_headline_feature_column_hash",
]
