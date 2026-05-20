"""Internal helpers for high-score skeptic audits (I/O, labels, modality bucketing)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.json_io import read_json_dict


def safe_read_split_audit(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def unique_families_from_drop_detail(drop_detail: list[Any]) -> int:
    fams: set[str] = set()
    for row in drop_detail:
        if isinstance(row, dict):
            f = row.get("family")
            if f is not None and str(f).strip():
                fams.add(str(f).strip())
    return len(fams)


def label_display(raw: Any, label_map: dict[str, str]) -> str:
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


def build_label_map(model_results: dict[str, Any], model_key: str, diagnostics_dir: Path, run_id: str) -> dict[str, str]:
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    out: dict[str, str] = {}
    if isinstance(res, dict):
        m = res.get("label_name_map")
        if isinstance(m, dict):
            out = {str(k): str(v) for k, v in m.items() if str(k).strip() and str(v).strip()}
    if not out:
        p = oh.resolve_label_name_map_path(diagnostics_dir, run_id)
        blob = read_json_dict(p)
        m2 = blob.get("label_name_map")
        if isinstance(m2, dict):
            out = {str(k): str(v) for k, v in m2.items() if str(k).strip() and str(v).strip()}
    return out


def write_false_attribution_empty(diagnostics_dir: Path, payload: dict[str, Any]) -> None:
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


def package_prefix_two_segments(package: str) -> str:
    s = str(package).strip().lower()
    if not s:
        return ""
    parts = [p for p in s.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return s


_SUSPICIOUS_PATTERNS = re.compile(
    r"(family_id|family_name|family_canonical|parsed_family|malware_type|type_slug|"
    r"true_family|predicted_family|classification_label|\blabel\b|package_name)",
    re.I,
)


def modality_bucket(name: str) -> str:
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
