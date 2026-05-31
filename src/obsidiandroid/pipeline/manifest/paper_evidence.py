"""Helpers for strict paper-facing evidence exports and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.pipeline.manifest.confusion_matrix_paths import find_primary_confusion_matrix


_PERTURBATION_PROFILE_FAMILIES: dict[str, set[str]] = {
    "malicious_temporal_stability_locked": {
        "malicious_temporal_stability_locked",
        "malicious_temporal_stability",
        "malicious_temporal_consensus10",
        "malicious_temporal_family300",
    },
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _json_load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_manuscript_table_constants(
    *,
    run_id: str,
    profile_id: str,
    samples_df: pd.DataFrame | None,
    cohort_contract: dict[str, Any],
) -> dict[str, Any]:
    """Build manuscript-facing cohort constants from the exported sample universe."""
    work = samples_df.copy() if isinstance(samples_df, pd.DataFrame) else pd.DataFrame()
    sample_count = int(len(work))
    if not work.empty:
        family_series = (
            work.get("family_canonical", pd.Series(dtype="object"))
            .fillna("")
            .astype(str)
            .str.strip()
        )
        type_series = (
            work.get("type_slug", pd.Series(dtype="object"))
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )
        family_count = int(family_series[family_series != ""].nunique())
        type_count = int(type_series[type_series != ""].nunique())
        family_counts = family_series[family_series != ""].value_counts()
        top_family_share = float((family_counts.iloc[0] / sample_count) if sample_count and not family_counts.empty else 0.0)
    else:
        family_count = 0
        type_count = 0
        top_family_share = 0.0

    expected = cohort_contract.get("expected", {}) if isinstance(cohort_contract.get("expected"), dict) else {}
    return {
        "schema_version": "1.0",
        "run_id": str(run_id),
        "profile_id": str(profile_id),
        "sample_count": sample_count,
        "family_count": family_count,
        "type_count": type_count,
        "top_family_share": round(top_family_share, 12),
        "time_window": {
            "start_utc": str(expected.get("time_window_start_utc", "") or ""),
            "end_utc": str(expected.get("time_window_end_utc", "") or ""),
            "window_semantics": str(expected.get("time_window_semantics", "") or ""),
        },
        "label_vocabulary": {
            "training_label_field": "family_id",
            "display_label_field": "family_canonical",
        },
    }


def write_manuscript_table_constants(*, output_path: Path, payload: dict[str, Any]) -> Path:
    """Write manuscript-facing cohort constants."""
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def validate_paper_contract_bundle(
    *,
    profile: dict[str, Any],
    manifest: dict[str, Any],
    paper_constants_path: Path,
    manuscript_constants_path: Path,
) -> dict[str, Any]:
    """Compare locked paper constants across profile, manifest, and exported tables."""
    profile_lock = profile.get("paper_lock", {}) if isinstance(profile.get("paper_lock"), dict) else {}
    profile_expected = {
        "sample_count": _safe_int(profile_lock.get("expected_sample_count"), 0),
        "family_count": _safe_int(profile_lock.get("expected_family_count"), 0),
        "type_count": _safe_int(profile_lock.get("expected_type_count"), 0),
    }
    paper_constants = _json_load(paper_constants_path)
    manuscript_constants = _json_load(manuscript_constants_path)
    manifest_summary = manifest.get("paper_cohort_summary", {}) if isinstance(manifest.get("paper_cohort_summary"), dict) else {}
    checks: list[dict[str, Any]] = []

    for field in ("sample_count", "family_count", "type_count"):
        values = {
            "profile": profile_expected.get(field),
            "paper_constants": _safe_int(
                paper_constants.get("malware_type_count") if field == "type_count" else paper_constants.get(field),
                -1,
            ),
            "manifest": _safe_int(manifest_summary.get(field), -1),
            "manuscript_tables": _safe_int(manuscript_constants.get(field), -1),
        }
        passed = len(set(values.values())) == 1
        checks.append({"field": field, "passed": passed, "values": values})

    time_window = {
        "profile": {
            "start_utc": str(profile_lock.get("time_window_start_utc", "") or ""),
            "end_utc": str(profile_lock.get("time_window_end_utc", "") or ""),
        },
        "paper_constants": dict((paper_constants.get("time_window") or {})),
        "manuscript_tables": dict((manuscript_constants.get("time_window") or {})),
    }
    time_window_passed = (
        str(time_window["profile"].get("start_utc", "") or "") == str(time_window["paper_constants"].get("start_utc", "") or "")
        == str(time_window["manuscript_tables"].get("start_utc", "") or "")
        and str(time_window["profile"].get("end_utc", "") or "") == str(time_window["paper_constants"].get("end_utc", "") or "")
        == str(time_window["manuscript_tables"].get("end_utc", "") or "")
    )
    checks.append({"field": "time_window", "passed": time_window_passed, "values": time_window})

    vocab = manuscript_constants.get("label_vocabulary", {}) if isinstance(manuscript_constants.get("label_vocabulary"), dict) else {}
    vocab_passed = (
        str(vocab.get("training_label_field", "") or "") == "family_id"
        and str(vocab.get("display_label_field", "") or "") == "family_canonical"
    )
    checks.append(
        {
            "field": "label_vocabulary",
            "passed": vocab_passed,
            "values": vocab,
        }
    )
    return {
        "schema_version": "1.0",
        "profile_id": str(profile.get("profile_id", "unknown") or "unknown"),
        "passed": bool(all(bool(row.get("passed", False)) for row in checks)),
        "checks": checks,
        "paper_constants_path": str(paper_constants_path),
        "manuscript_constants_path": str(manuscript_constants_path),
    }


def build_feature_set_glossary_payload() -> dict[str, Any]:
    """Build paper feature-set glossary for manuscript-facing exports."""
    return {
        "schema_version": "1.0",
        "label_vocabulary": {
            "training_label_field": "family_id",
            "display_label_field": "family_canonical",
        },
        "feature_sets": [
            {
                "paper_feature_set": "permissions_only",
                "internal_experiments": ["permissions_grouped", "permissions_raw"],
                "feature_column_groups": ["perm__*", "perm_grp__*"],
                "notes": "Permission-only feature stacks; no vendor lexical columns.",
            },
            {
                "paper_feature_set": "vendor_only",
                "internal_experiments": ["vendor_no_parsed_family"],
                "feature_column_groups": ["vendor_detection_*", "vendor_parsed_threat_class_*", "vendor_parsed_malware_type_*"],
                "notes": "Vendor-derived features with Parsed Family removed; safer vendor lexical baseline.",
            },
            {
                "paper_feature_set": "vendor_permissions_fused",
                "internal_experiments": [
                    "permissions_grouped_plus_vendor_no_family",
                    "permissions_grouped_plus_vendor_safe",
                    "full_fused",
                ],
                "feature_column_groups": [
                    "perm__*",
                    "perm_grp__*",
                    "vendor_detection_*",
                    "vendor_parsed_threat_class_*",
                    "vendor_parsed_malware_type_*",
                ],
                "notes": "Fused permission + safer vendor features; paper-facing vocabulary keeps training target fixed to family_id.",
            },
        ],
    }


def write_feature_set_glossary(*, json_path: Path, md_path: Path) -> tuple[Path, Path]:
    """Write machine-readable and markdown feature-set glossary exports."""
    payload = build_feature_set_glossary_payload()
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Feature Set Glossary",
        "",
        "- Training target: `family_id`",
        "- Display / audit label: `family_canonical`",
        "",
        "| paper_feature_set | internal_experiments | feature_column_groups | notes |",
        "| --- | --- | --- | --- |",
    ]
    for row in payload["feature_sets"]:
        lines.append(
            "| {paper_feature_set} | {internal} | {groups} | {notes} |".format(
                paper_feature_set=row["paper_feature_set"],
                internal=", ".join(row["internal_experiments"]),
                groups=", ".join(row["feature_column_groups"]),
                notes=row["notes"],
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def _profile_family_candidates(profile_id: str) -> set[str]:
    for key, family in _PERTURBATION_PROFILE_FAMILIES.items():
        if profile_id == key or profile_id in family:
            return set(family)
    return {profile_id}


def _perturbation_axis_value(*, baseline_gates: dict[str, Any], row_gates: dict[str, Any]) -> tuple[str, str]:
    baseline_min = baseline_gates.get("min_malicious_detections")
    baseline_cap = baseline_gates.get("family_cap")
    row_min = row_gates.get("min_malicious_detections")
    row_cap = row_gates.get("family_cap")
    if row_min != baseline_min:
        return "min_malicious_detections", str(row_min)
    if row_cap != baseline_cap:
        return "family_cap", str(row_cap)
    return "baseline", "baseline"


def _extract_run_row(
    *,
    run_root: Path,
    baseline_gates: dict[str, Any],
    material_change_threshold: float,
) -> dict[str, Any] | None:
    manifest_path = run_root / "run_manifest.json"
    if not manifest_path.exists():
        return None
    manifest = _json_load(manifest_path)
    diagnostics_dir = run_root / "diagnostics"
    run_id = str(manifest.get("run_id", run_root.name) or run_root.name)
    contract_path = diagnostics_dir / f"experiment_contract_snapshot_{run_id}.json"
    eval_contract_path = diagnostics_dir / f"evaluation_contract_{run_id}.json"
    if not contract_path.exists() or not eval_contract_path.exists():
        return None
    contract = _json_load(contract_path)
    eval_contract = _json_load(eval_contract_path)
    cohort_contract = manifest.get("cohort_contract", {}) if isinstance(manifest.get("cohort_contract"), dict) else {}
    sample_id_lock = cohort_contract.get("sample_id_lock", {}) if isinstance(cohort_contract.get("sample_id_lock"), dict) else {}
    profile_id = str(manifest.get("profile_id", contract.get("profile_id", "unknown")) or "unknown")
    profile_gates = (manifest.get("profile_params", {}) or {}).get("cohort_gates", {})
    if not isinstance(profile_gates, dict):
        profile_gates = {}
    perturbation_axis, perturbation_value = _perturbation_axis_value(
        baseline_gates=baseline_gates,
        row_gates=profile_gates,
    )
    model_summary = manifest.get("model_summary", {}) if isinstance(manifest.get("model_summary"), dict) else {}
    row = {
        "run_id": run_id,
        "profile_id": profile_id,
        "cohort_hash": str(sample_id_lock.get("cohort_hash", "") or ""),
        "taxonomy_hash": str(sample_id_lock.get("taxonomy_hash", "") or ""),
        "perturbation_axis": perturbation_axis,
        "perturbation_value": perturbation_value,
        "sample_count": _safe_int(manifest.get("cohort_size"), 0),
        "family_count": _safe_int(
            (manifest.get("paper_cohort_summary", {}) or {}).get("family_count")
            or (manifest.get("cohort_limitation_summary", {}) or {}).get("total_cohort_families"),
            0,
        ),
        "type_count": _safe_int(
            (manifest.get("paper_cohort_summary", {}) or {}).get("type_count")
            or (cohort_contract.get("expected", {}) or {}).get("type_count"),
            0,
        ),
        "label_target": "family_id",
        "feature_set": "full_fused",
        "model": str(model_summary.get("top_model", "") or ""),
        "macro_f1": _safe_float(model_summary.get("top_macro_f1"), 0.0),
        "delta_macro_f1_vs_baseline": 0.0,
        "material_change_flag": False,
        "split_hash": str(((manifest.get("split") or {})).get("split_hash", "") or ""),
        "model_config_hash": str(manifest.get("model_config_hash", "") or ""),
        "feature_column_hash": str(
            (((eval_contract.get("feature_contract") or {})).get("headline_feature_column_hash", "")) or ""
        ),
        "_material_change_threshold": float(material_change_threshold),
    }
    return row


def build_perturbation_summary_rows(
    *,
    runs_root: Path,
    current_run_root: Path,
    profile: dict[str, Any],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Aggregate baseline and perturbation runs into canonical paper rows."""
    profile_id = str(profile.get("profile_id", manifest.get("profile_id", "unknown")) or "unknown")
    allowed_profiles = _profile_family_candidates(profile_id)
    baseline_gates = (profile.get("cohort_gates", {}) if isinstance(profile.get("cohort_gates"), dict) else {}) or {}
    threshold = _safe_float((profile.get("paper_lock", {}) or {}).get("material_change_abs_delta_macro_f1_gt"), 0.02)
    rows: list[dict[str, Any]] = []
    for candidate in sorted(runs_root.glob("*")):
        if not candidate.is_dir():
            continue
        row = _extract_run_row(
            run_root=candidate,
            baseline_gates=baseline_gates,
            material_change_threshold=threshold,
        )
        if not row or str(row.get("profile_id", "")) not in allowed_profiles:
            continue
        rows.append(row)

    current_present = any(str(row.get("run_id", "")) == str(manifest.get("run_id", "")) for row in rows)
    if not current_present:
        current_row = _extract_run_row(
            run_root=current_run_root,
            baseline_gates=baseline_gates,
            material_change_threshold=threshold,
        )
        if current_row is not None:
            rows.append(current_row)

    if not rows:
        return []

    baseline_row = next(
        (row for row in rows if str(row.get("perturbation_axis", "")) == "baseline"),
        rows[0],
    )
    baseline_macro = _safe_float(baseline_row.get("macro_f1"), 0.0)
    for row in rows:
        delta = round(_safe_float(row.get("macro_f1"), 0.0) - baseline_macro, 6)
        row["delta_macro_f1_vs_baseline"] = delta
        row["material_change_flag"] = bool(
            str(row.get("perturbation_axis", "")) != "baseline"
            and abs(delta) > float(row.pop("_material_change_threshold", threshold))
        )
        row.pop("_material_change_threshold", None)
    rows.sort(
        key=lambda item: (
            0 if str(item.get("perturbation_axis", "")) == "baseline" else 1,
            str(item.get("perturbation_axis", "")),
            str(item.get("perturbation_value", "")),
            str(item.get("run_id", "")),
        )
    )
    return rows


def validate_perturbation_summary_rows(rows: list[dict[str, Any]]) -> None:
    """Validate required cohort/split hashes for perturbation exports."""
    missing = [
        row["run_id"]
        for row in rows
        if not str(row.get("split_hash", "") or "").strip()
        or not str(row.get("cohort_hash", "") or "").strip()
    ]
    if missing:
        raise ValueError(
            "perturbation summary rows missing split_hash/cohort_hash: " + ", ".join(sorted(missing))
        )


def write_perturbation_summary(
    *,
    docs_dir: Path,
    runs_root: Path,
    current_run_root: Path,
    profile: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Path]:
    """Write canonical paper perturbation summary bundle."""
    rows = build_perturbation_summary_rows(
        runs_root=runs_root,
        current_run_root=current_run_root,
        profile=profile,
        manifest=manifest,
    )
    validate_perturbation_summary_rows(rows)
    df = pd.DataFrame(rows)
    csv_path = docs_dir / "perturbation_summary.csv"
    json_path = docs_dir / "perturbation_summary.json"
    md_path = docs_dir / "perturbation_summary.md"
    df.to_csv(csv_path, index=False, float_format="%.6f")
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Perturbation Summary",
        "",
        "| run_id | profile_id | perturbation_axis | perturbation_value | model | macro_f1 | delta_macro_f1_vs_baseline | material_change_flag | split_hash | cohort_hash |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {run_id} | {profile_id} | {perturbation_axis} | {perturbation_value} | {model} | {macro_f1:.6f} | {delta:.6f} | {flag} | `{split_hash}` | `{cohort_hash}` |".format(
                run_id=row.get("run_id", ""),
                profile_id=row.get("profile_id", ""),
                perturbation_axis=row.get("perturbation_axis", ""),
                perturbation_value=row.get("perturbation_value", ""),
                model=row.get("model", ""),
                macro_f1=_safe_float(row.get("macro_f1"), 0.0),
                delta=_safe_float(row.get("delta_macro_f1_vs_baseline"), 0.0),
                flag=str(bool(row.get("material_change_flag", False))).lower(),
                split_hash=row.get("split_hash", ""),
                cohort_hash=row.get("cohort_hash", ""),
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "md": md_path}


def build_promoted_paper_model_binding(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    manifest: dict[str, Any],
    evidence_mode: bool,
    feature_column_hash: str = "",
) -> dict[str, Any]:
    """Build strict promoted-paper-model evidence binding for the manifest."""
    run_id = str(manifest.get("run_id", "unknown") or "unknown")
    top_model = str(((manifest.get("model_summary") or {})).get("top_model", "") or "").strip()
    split_hash = str(((manifest.get("split") or {})).get("split_hash", "") or "")
    predictions_path = diagnostics_dir / f"headline_test_predictions_{run_id}.csv"
    if not predictions_path.exists():
        raise ValueError(f"promoted headline predictions missing: {predictions_path}")
    pred_df = pd.read_csv(predictions_path)
    pred_hashes = {
        str(value).strip()
        for value in pred_df.get("split_hash", pd.Series(dtype="object")).fillna("").astype(str).tolist()
        if str(value).strip()
    }
    if pred_hashes != {split_hash}:
        raise ValueError(
            f"promoted headline prediction split_hash mismatch: expected={split_hash!r} observed={sorted(pred_hashes)!r}"
        )
    confusion_path = find_primary_confusion_matrix(
        run_root=run_root,
        top_model=top_model or "random_forest",
        evidence_mode=bool(evidence_mode),
    )
    if confusion_path is None or not confusion_path.exists():
        raise ValueError(f"promoted confusion matrix missing for model={top_model or 'unknown'}")
    cohort_contract = manifest.get("cohort_contract", {}) if isinstance(manifest.get("cohort_contract"), dict) else {}
    sample_lock = cohort_contract.get("sample_id_lock", {}) if isinstance(cohort_contract.get("sample_id_lock"), dict) else {}
    feature_hash = str(feature_column_hash or "").strip()
    if not feature_hash:
        eval_contract_path = diagnostics_dir / f"evaluation_contract_{run_id}.json"
        if eval_contract_path.exists():
            feature_hash = str(
                (
                    (_json_load(eval_contract_path).get("feature_contract") or {}).get(
                        "headline_feature_column_hash",
                        "",
                    )
                )
                or ""
            ).strip()
    return {
        "model": top_model,
        "label_target": "family_id",
        "display_label_field": "family_canonical",
        "split_hash": split_hash,
        "confusion_matrix_split_hash": split_hash,
        "heldout_predictions_split_hash": split_hash,
        "split_audit_path": str(((manifest.get("split") or {})).get("split_audit_path", "") or ""),
        "confusion_matrix_path": str(confusion_path.resolve()),
        "heldout_predictions_csv": str(predictions_path.resolve()),
        "heldout_errors_csv": str((diagnostics_dir / f"headline_test_errors_{run_id}.csv").resolve()),
        "feature_column_hash": feature_hash,
        "model_config_hash": str(manifest.get("model_config_hash", "") or ""),
        "cohort_hash": str(sample_lock.get("cohort_hash", "") or ""),
        "taxonomy_hash": str(sample_lock.get("taxonomy_hash", "") or ""),
    }


def write_promoted_paper_model_binding(*, output_path: Path, payload: dict[str, Any]) -> Path:
    """Write promoted-paper-model binding JSON."""
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
