"""Permission-token audit CSV for reviewer-facing lineage."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.database import db_engine
from obsidiandroid.orchestration.permission_features import PERMISSION_GROUP_DEFINITIONS
from obsidiandroid.orchestration.permission_features import _fetch_permission_rows  # pylint: disable=protected-access


_REMEDIATION_LANE_POLICIES: dict[str, dict[str, str]] = {
    "app_defined_legacy_push_permission": {
        "lane_class": "app_scaffolding",
        "default_action": "classify_as_app_defined_push_scaffolding",
        "malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "app_defined_dynamic_receiver_guard": {
        "lane_class": "androidx_library_scaffolding",
        "default_action": "classify_as_androidx_receiver_guard_scaffolding",
        "malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "third_party_sdk_or_launcher": {
        "lane_class": "ecosystem_noise",
        "default_action": "classify_as_launcher_or_sdk_ecosystem",
        "malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "google_service_permission": {
        "lane_class": "google_service_ecosystem",
        "default_action": "classify_as_google_service_permission",
        "malware_capability_posture": "separate_from_aosp_and_custom_permissions",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "oem_vendor_permission": {
        "lane_class": "oem_vendor_ecosystem",
        "default_action": "route_to_oem_vendor_space_governance",
        "malware_capability_posture": "separate_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "app_defined_maps_receive_permission": {
        "lane_class": "app_scaffolding",
        "default_action": "classify_as_legacy_maps_scaffolding",
        "malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "app_defined_custom_permission": {
        "lane_class": "app_defined_custom",
        "default_action": "review_as_app_defined_custom_permission",
        "malware_capability_posture": "needs_package_or_family_specific_review",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "review",
    },
    "third_party_push_sdk_permission": {
        "lane_class": "ecosystem_noise",
        "default_action": "classify_as_third_party_push_sdk_scaffolding",
        "malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "app_defined_adm_permission": {
        "lane_class": "app_scaffolding",
        "default_action": "classify_as_amazon_device_messaging_scaffolding",
        "malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "app_defined_apphub_permission": {
        "lane_class": "app_scaffolding",
        "default_action": "classify_as_apphub_binding_scaffolding",
        "malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": "yes",
        "include_in_behavioral_claims": "no",
    },
    "needs_source_validation": {
        "lane_class": "aosp_metadata_debt",
        "default_action": "validate_against_aosp_hidden_platform_or_module_sources",
        "malware_capability_posture": "hold_out_of_behavior_claims_until_validated",
        "include_in_model_features": "review",
        "include_in_behavioral_claims": "no",
    },
}


def _classify_perm_row(source: str, protection: str) -> tuple[str, str]:
    prot = str(protection or "").strip().upper()
    src_u = str(source or "").strip().upper()
    if "DANGEROUS" in prot:
        tier = "dangerous"
    elif "NORMAL" in prot:
        tier = "normal"
    elif src_u == "GOOGLE":
        tier = "google"
    elif src_u == "APP_DEFINED":
        tier = "app_defined"
    elif src_u in {"OEM", "APP_DEFINED"}:
        tier = "oem_vendor"
    else:
        tier = "unknown"
    return tier, src_u or "UNKNOWN"


def _feature_group_bucket(permission_string: str) -> str:
    text = permission_string.lower()
    for name, pattern in PERMISSION_GROUP_DEFINITIONS:
        if pattern.search(text):
            return name.replace("_count", "")
    return "ungrouped"


def build_permission_feature_audit_rows(
    samples_df: pd.DataFrame,
    *,
    min_support_cfg: int = 2,
) -> list[dict[str, Any]]:
    """Produce one CSV row per permission token."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty or "sample_id" not in samples_df.columns:
        return []

    ids = sorted({int(float(sid)) for sid in samples_df["sample_id"].tolist() if pd.notna(sid)})
    permission_df = _fetch_permission_rows(ids)
    if permission_df.empty:
        return []

    prune_names: set[str] = set()
    prune_rows = getattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", None)
    if isinstance(prune_rows, list):
        for row in prune_rows:
            if isinstance(row, dict):
                cn = row.get("column_name")
                if cn:
                    prune_names.add(str(cn))

    merged = samples_df.copy()
    if "family_canonical" not in merged.columns:
        merged["family_canonical"] = "unknown"
    if "type_slug" not in merged.columns:
        merged["type_slug"] = "unknown"

    pdf = permission_df.copy()
    pdf["permission_string"] = pdf["permission_string"].fillna("").astype(str).str.strip().str.lower()
    pdf = pdf[pdf["permission_string"] != ""]
    global_counts = pdf.groupby("permission_string")["sample_id"].nunique()

    fam_support = pdf.merge(merged[["sample_id", "family_canonical"]], on="sample_id", how="left")
    family_max = (
        fam_support.groupby(["permission_string", "family_canonical"])["sample_id"]
        .nunique()
        .groupby(level=0)
        .max()
    )

    typ_support = pdf.merge(merged[["sample_id", "type_slug"]], on="sample_id", how="left")
    type_max = (
        typ_support.groupby(["permission_string", "type_slug"])["sample_id"]
        .nunique()
        .groupby(level=0)
        .max()
    )

    rows: list[dict[str, Any]] = []
    token_rows = pdf.drop_duplicates("permission_string")
    for _, trow in token_rows.iterrows():
        perm_token = str(trow.get("permission_string", "")).strip().lower()
        if not perm_token:
            continue
        gc = int(global_counts.get(perm_token, 0))
        tier, _pis = _classify_perm_row(str(trow.get("permission_source", "")), str(trow.get("protection_level", "")))

        sanitized = re.sub(r"[^a-z0-9]+", "_", perm_token).strip("_") or "unknown"
        col_name = f"perm__{sanitized}"
        pi_src_col = ""
        try:
            if "permission_source" in pdf.columns:
                pi_src_col = str(
                    pdf.loc[pdf["permission_string"] == perm_token, "permission_source"].iloc[0]
                )
        except Exception:
            pi_src_col = ""

        retained = gc >= int(min_support_cfg)

        rows.append(
            {
                "permission_string": perm_token,
                "feature_column": col_name,
                "global_support": gc,
                "max_family_support": int(family_max.loc[perm_token])
                if perm_token in family_max.index
                else 0,
                "max_type_support": int(type_max.loc[perm_token])
                if perm_token in type_max.index
                else 0,
                "retained_after_pruning": "yes" if retained else "no",
                "pruned_as_leakage": "yes" if col_name in prune_names else "no",
                "pi_bucket_source": pi_src_col,
                "dangerous_bucket": tier,
                "feature_group": _feature_group_bucket(perm_token),
            }
        )

    rows.sort(key=lambda r: (-int(r.get("global_support", 0)), str(r.get("permission_string"))))
    return rows


def write_permission_feature_audit_csv(
    *,
    diagnostics_dir: Path,
    samples_df: pd.DataFrame | None,
) -> Path | None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    cfg = safe_int_config_value(getattr(app_config, "PERMISSION_MIN_SUPPORT", 2), default=2)
    target = diagnostics_dir / "permission_feature_audit.csv"
    if samples_df is None or samples_df.empty:
        target.write_text("status,notes\nstub,empty_samples\n", encoding="utf-8")
        return target
    audit_rows = build_permission_feature_audit_rows(samples_df, min_support_cfg=cfg)
    if not audit_rows:
        target.write_text("status,notes\nempty,no_permission_rows\n", encoding="utf-8")
        return target
    fieldnames = sorted({key for row in audit_rows for key in row.keys()})
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)
    return target


def write_permission_intel_audit_artifacts(
    *,
    diagnostics_dir: Path,
    samples_df: pd.DataFrame | None,
) -> list[Path]:
    """Write run-scoped Permission Intel audit artifacts for the active cohort."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    summary_path = diagnostics_dir / "permission_intel_audit_summary.csv"
    missing_type_path = diagnostics_dir / "permission_intel_missing_by_type.csv"
    missing_family_path = diagnostics_dir / "permission_intel_missing_by_family.csv"
    unknown_path = diagnostics_dir / "permission_intel_unknown_permissions.csv"
    remediation_path = diagnostics_dir / "permission_intel_remediation_lanes.csv"
    lifecycle_path = diagnostics_dir / "permission_intel_workflow_gaps.csv"
    aosp_metadata_path = diagnostics_dir / "permission_intel_aosp_metadata_debt.csv"
    signal_catalog_path = diagnostics_dir / "permission_intel_signal_catalog_summary.csv"
    signal_review_path = diagnostics_dir / "permission_intel_signal_mapping_review.csv"
    report_path = diagnostics_dir / "permission_intel_audit_report.md"

    if samples_df is None or samples_df.empty or "sample_id" not in samples_df.columns:
        summary_path.write_text("metric,value,notes\nstatus,stub,empty_samples\n", encoding="utf-8")
        report_path.write_text("# Permission Intel Audit\n\nNo samples dataframe.\n", encoding="utf-8")
        return [summary_path, report_path]

    work = samples_df.copy()
    for col in ["family_canonical", "type_slug", "sample_label_kind", "source_batch_label"]:
        if col not in work.columns:
            work[col] = ""
    ids = sorted({int(float(sid)) for sid in work["sample_id"].tolist() if pd.notna(sid)})
    permission_df = _fetch_permission_rows(ids)
    if permission_df.empty:
        summary_path.write_text("metric,value,notes\nstatus,empty,no_permission_rows\n", encoding="utf-8")
        report_path.write_text("# Permission Intel Audit\n\nNo Permission Intel rows returned for this cohort.\n", encoding="utf-8")
        return [summary_path, report_path]

    pdf = permission_df.copy()
    pdf["sample_id"] = pd.to_numeric(pdf["sample_id"], errors="coerce").fillna(-1).astype(int)
    pdf["permission_string"] = pdf["permission_string"].fillna("").astype(str).str.strip().str.lower()
    pdf["permission_source"] = pdf["permission_source"].fillna("UNKNOWN").astype(str).str.strip().str.upper()
    pdf["protection_level"] = pdf["protection_level"].fillna("UNKNOWN").astype(str).str.strip().str.upper()
    pdf = pdf[pdf["permission_string"] != ""].copy()

    observed_ids = set(pdf["sample_id"].dropna().astype(int).tolist())
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="coerce").fillna(-1).astype(int)
    work["has_permission_intel"] = work["sample_id"].isin(observed_ids)
    missing = work[~work["has_permission_intel"]].copy()

    source_per_sample = pdf.groupby("sample_id")["permission_source"].nunique()
    unknown_df = pdf[pdf["permission_source"] == "UNKNOWN"].copy()
    unknown_perm_df = (
        unknown_df.groupby("permission_string")["sample_id"]
        .nunique()
        .reset_index(name="sample_support")
        .sort_values(["sample_support", "permission_string"], ascending=[False, True], kind="mergesort")
    )

    summary_rows = [
        {"metric": "cohort_samples", "value": int(len(work)), "notes": ""},
        {"metric": "samples_with_permission_intel", "value": int(len(observed_ids & set(work["sample_id"].tolist()))), "notes": ""},
        {"metric": "samples_without_permission_intel", "value": int(len(missing)), "notes": ""},
        {
            "metric": "permission_intel_coverage_pct",
            "value": round(float((len(work) - len(missing)) / max(len(work), 1)) * 100.0, 6),
            "notes": "cohort sample coverage",
        },
        {"metric": "permission_rows", "value": int(len(pdf)), "notes": ""},
        {"metric": "distinct_permissions", "value": int(pdf["permission_string"].nunique()), "notes": ""},
        {"metric": "samples_multi_source_class", "value": int((source_per_sample > 1).sum()), "notes": ""},
        {"metric": "unknown_permission_rows", "value": int(len(unknown_df)), "notes": ""},
        {"metric": "unknown_permission_samples", "value": int(unknown_df["sample_id"].nunique()), "notes": ""},
        {"metric": "unknown_distinct_permissions", "value": int(unknown_df["permission_string"].nunique()), "notes": ""},
        {
            "metric": "dangerous_permission_row_rate",
            "value": round(float(pdf["protection_level"].str.contains("DANGEROUS", regex=False).mean()), 6),
            "notes": "",
        },
        {
            "metric": "unknown_protection_row_rate",
            "value": round(float((pdf["protection_level"].str.strip() == "UNKNOWN").mean()), 6),
            "notes": "",
        },
    ]
    for source_name, count in pdf["permission_source"].value_counts().items():
        summary_rows.append(
            {"metric": f"rows_source_{str(source_name).lower()}", "value": int(count), "notes": ""}
        )

    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

    missing_by_type = (
        missing.groupby("type_slug", dropna=False)["sample_id"]
        .nunique()
        .reset_index(name="sample_count")
        .sort_values(["sample_count", "type_slug"], ascending=[False, True], kind="mergesort")
    )
    missing_by_type.to_csv(missing_type_path, index=False)

    missing_by_family = (
        missing.groupby(["family_canonical", "type_slug"], dropna=False)["sample_id"]
        .nunique()
        .reset_index(name="sample_count")
        .sort_values(["sample_count", "family_canonical", "type_slug"], ascending=[False, True, True], kind="mergesort")
    )
    missing_by_family.to_csv(missing_family_path, index=False)

    if unknown_perm_df.empty:
        pd.DataFrame(columns=["permission_string", "sample_support"]).to_csv(unknown_path, index=False)
    else:
        unknown_perm_df.to_csv(unknown_path, index=False)

    remediation_df = _build_permission_intel_remediation_lanes_df()
    remediation_df.to_csv(remediation_path, index=False)

    lifecycle_df = _build_permission_intel_workflow_gap_df()
    lifecycle_df.to_csv(lifecycle_path, index=False)

    aosp_metadata_df = _build_permission_intel_aosp_metadata_gap_df()
    aosp_metadata_df.to_csv(aosp_metadata_path, index=False)

    signal_catalog_df = _build_permission_signal_catalog_summary_df()
    signal_catalog_df.to_csv(signal_catalog_path, index=False)

    signal_review_df = _build_permission_signal_mapping_review_df()
    signal_review_df.to_csv(signal_review_path, index=False)

    lines = [
        "# Permission Intel Audit",
        "",
        f"- Cohort samples: {int(len(work))}",
        f"- Samples with Permission Intel rows: {int(len(work) - len(missing))}",
        f"- Samples without Permission Intel rows: {int(len(missing))}",
        f"- Coverage: {round(float((len(work) - len(missing)) / max(len(work), 1)) * 100.0, 3)}%",
        f"- Distinct observed permissions: {int(pdf['permission_string'].nunique())}",
        f"- Samples with mixed permission source classes: {int((source_per_sample > 1).sum())}",
        f"- UNKNOWN permission rows: {int(len(unknown_df))} across {int(unknown_df['sample_id'].nunique())} samples",
        "",
        "Interpretation:",
        "- Permission declarations are static declared-capability signals, not proof of runtime behavior.",
        "- Missing PI rows should stay visible as corpus-health debt, not be silently dropped from diagnostics.",
        "- UNKNOWN permissions should be reviewed as taxonomy/authority debt before strong behavioral claims are made.",
        "- App scaffolding, launcher/SDK ecosystem noise, Google service permissions, and OEM/vendor-space permissions should not be treated as equivalent malware-capability signal.",
        "",
        "Signal interpretation summary:",
    ]
    if signal_catalog_df.empty:
        lines.extend(
            [
                "- Signal catalog not seeded yet.",
            ]
        )
    else:
        behavior_safe = signal_catalog_df[signal_catalog_df["include_in_behavioral_claims"] == True]  # noqa: E712
        model_only = signal_catalog_df[
            (signal_catalog_df["include_in_model_features"] == True)  # noqa: E712
            & (signal_catalog_df["include_in_behavioral_claims"] == False)  # noqa: E712
        ]
        exclusions = signal_catalog_df[
            signal_catalog_df["authority_lane"].isin(
                [
                    "app_scaffolding",
                    "ecosystem_noise",
                    "google_service_ecosystem",
                    "oem_vendor_ecosystem",
                ]
            )
        ]
        behavior_safe_labels = ", ".join(behavior_safe["signal_key"].head(10).tolist()) or "none"
        model_only_labels = ", ".join(model_only["signal_key"].head(10).tolist()) or "none"
        exclusion_labels = ", ".join(exclusions["signal_key"].head(10).tolist()) or "none"
        lines.extend(
            [
                f"- Behavior-claim-safe signals: {behavior_safe_labels}",
                f"- Model-only / fingerprint signals: {model_only_labels}",
                f"- Ecosystem / scaffolding exclusions: {exclusion_labels}",
            ]
        )
    if not signal_review_df.empty:
        lines.append(f"- Mappings requiring review: {int(len(signal_review_df))}")
    lines.extend(
        [
            "",
        "Top missing-by-type rows:",
        ]
    )
    for _, row in missing_by_type.head(10).iterrows():
        lines.append(f"- {row['type_slug'] or '<blank>'}: n={int(row['sample_count'])}")
    lines.extend(["", "Top UNKNOWN permission tokens:"])
    for _, row in unknown_perm_df.head(10).iterrows():
        lines.append(f"- {row['permission_string']}: samples={int(row['sample_support'])}")
    if not remediation_df.empty:
        lines.extend(["", "Concentrated remediation lanes:"])
        for _, row in remediation_df.head(10).iterrows():
            lines.append(
                "- "
                f"{row['source_family_key']}: tokens={int(row['token_count'])}, "
                f"seen={int(row['total_seen'])}, lane={row['lane_class']}, "
                f"action={row['default_action']}"
            )
    if not aosp_metadata_df.empty:
        lines.extend(["", "AOSP metadata debt:"])
        for _, row in aosp_metadata_df.iterrows():
            lines.append(f"- {row['metadata_completeness_class']}: n={int(row['token_count'])}")
    if not signal_review_df.empty:
        lines.extend(["", "Mappings requiring review:"])
        for _, row in signal_review_df.head(10).iterrows():
            lines.append(
                "- "
                f"{row['signal_key']} / {row['perm_name']} "
                f"(basis={row['mapping_basis']}, confidence={row['confidence']}, "
                f"behavioral={'yes' if bool(row['include_in_behavioral_claims']) else 'no'})"
            )
    if not lifecycle_df.empty:
        lines.extend(["", "Workflow table gaps:"])
        for _, row in lifecycle_df[lifecycle_df["is_empty"] == True].iterrows():  # noqa: E712
            lines.append(
                f"- {row['table_name']}: empty ({row['expected_role']})"
            )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return [
        summary_path,
        missing_type_path,
        missing_family_path,
        unknown_path,
        remediation_path,
        lifecycle_path,
        aosp_metadata_path,
        signal_catalog_path,
        signal_review_path,
        report_path,
    ]


def _build_permission_intel_remediation_lanes_df() -> pd.DataFrame:
    query = """
        WITH unresolved AS (
            SELECT
                candidate_source_family_key,
                candidate_source_family_label,
                candidate_review_lane,
                seen_count,
                example_package_name,
                example_sample_id
            FROM vw_permission_unknown_unresolved_candidates
        )
        SELECT
            candidate_source_family_key AS source_family_key,
            candidate_source_family_label AS source_family_label,
            candidate_review_lane AS review_lane,
            COUNT(*) AS token_count,
            SUM(seen_count) AS total_seen,
            COUNT(DISTINCT example_sample_id) AS sample_count,
            COUNT(DISTINCT example_package_name) AS package_count
        FROM unresolved
        GROUP BY
            candidate_source_family_key,
            candidate_source_family_label,
            candidate_review_lane
        ORDER BY total_seen DESC, token_count DESC, source_family_key
    """
    frame = db_engine.execute_permission_query(query, fetch=True, as_dataframe=True)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(
            columns=[
                "source_family_key",
                "source_family_label",
                "review_lane",
                "token_count",
                "total_seen",
                "sample_count",
                "package_count",
                "lane_class",
                "default_action",
                "malware_capability_posture",
                "include_in_model_features",
                "include_in_behavioral_claims",
            ]
        )
    frame = frame.copy()
    frame["source_family_key"] = frame["source_family_key"].fillna("").astype(str)
    for column in (
        "lane_class",
        "default_action",
        "malware_capability_posture",
        "include_in_model_features",
        "include_in_behavioral_claims",
    ):
        frame[column] = frame["source_family_key"].map(
            lambda key, field=column: _REMEDIATION_LANE_POLICIES.get(str(key), {}).get(field, "review_required")
        )
    return frame


def _build_permission_intel_workflow_gap_df() -> pd.DataFrame:
    tables = {
        "permission_signal_catalog": "signal_catalog_seed",
        "permission_signal_mappings": "signal_mapping_seed",
        "android_permission_run_aosp_import": "aosp_import_provenance",
        "android_permission_triage_audit": "triage_operator_audit",
    }
    union = " UNION ALL ".join(
        [
            f"SELECT '{table}' AS table_name, '{role}' AS expected_role, COUNT(*) AS row_count FROM `{table}`"
            for table, role in tables.items()
        ]
    )
    frame = db_engine.execute_permission_query(union, fetch=True, as_dataframe=True)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["table_name", "expected_role", "row_count", "is_empty"])
    frame = frame.copy()
    frame["row_count"] = pd.to_numeric(frame["row_count"], errors="coerce").fillna(0).astype(int)
    frame["is_empty"] = frame["row_count"] <= 0
    return frame.sort_values(["is_empty", "table_name"], ascending=[False, True], kind="mergesort")


def _build_permission_intel_aosp_metadata_gap_df() -> pd.DataFrame:
    query = """
        SELECT
            metadata_completeness_class,
            COUNT(*) AS token_count,
            SUM(missing_protection_level) AS missing_protection_level_count,
            SUM(missing_description) AS missing_description_count,
            SUM(missing_added_in_api_level) AS missing_added_in_api_level_count
        FROM vw_permission_aosp_metadata_completeness
        GROUP BY metadata_completeness_class
        ORDER BY token_count DESC, metadata_completeness_class
    """
    frame = db_engine.execute_permission_query(query, fetch=True, as_dataframe=True)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(
            columns=[
                "metadata_completeness_class",
                "token_count",
                "missing_protection_level_count",
                "missing_description_count",
                "missing_added_in_api_level_count",
            ]
        )
    return frame


def _build_permission_signal_catalog_summary_df() -> pd.DataFrame:
    query = """
        SELECT
            signal_key,
            display_name,
            authority_lane,
            default_malware_capability_posture,
            include_in_model_features,
            include_in_behavioral_claims,
            mitre_candidate_only,
            default_weight
        FROM permission_signal_catalog
        ORDER BY
            include_in_behavioral_claims DESC,
            include_in_model_features DESC,
            signal_key
    """
    frame = db_engine.execute_permission_query(query, fetch=True, as_dataframe=True)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(
            columns=[
                "signal_key",
                "display_name",
                "authority_lane",
                "default_malware_capability_posture",
                "include_in_model_features",
                "include_in_behavioral_claims",
                "mitre_candidate_only",
                "default_weight",
            ]
        )
    return frame


def _build_permission_signal_mapping_review_df() -> pd.DataFrame:
    query = """
        SELECT
            signal_key,
            perm_name,
            namespace,
            mapping_basis,
            source_family_key,
            include_in_model_features,
            include_in_behavioral_claims,
            candidate_behavior_area,
            mitre_candidate_tactic,
            confidence
        FROM permission_signal_mappings
        WHERE
            include_in_behavioral_claims = 0
            OR confidence <> 'high'
            OR source_family_key IS NOT NULL
        ORDER BY
            include_in_behavioral_claims ASC,
            confidence,
            signal_key,
            perm_name
    """
    frame = db_engine.execute_permission_query(query, fetch=True, as_dataframe=True)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(
            columns=[
                "signal_key",
                "perm_name",
                "namespace",
                "mapping_basis",
                "source_family_key",
                "include_in_model_features",
                "include_in_behavioral_claims",
                "candidate_behavior_area",
                "mitre_candidate_tactic",
                "confidence",
            ]
        )
    return frame
