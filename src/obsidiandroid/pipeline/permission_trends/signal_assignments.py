"""Build permission signal assignments and their evidence coverage."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from obsidiandroid.database.permission_current_interpretation import (
    is_androidx_dynamic_receiver_permission,
)
from obsidiandroid.diagnostics.research_validity.permission_signal_seed import (
    SIGNAL_CATALOG_ROWS,
    SIGNAL_MAPPING_ROWS,
    load_permission_signal_catalog_rows,
    load_permission_signal_mapping_rows,
)
from obsidiandroid.reporting.package_balanced_permission_analysis import assign_package_keys


def signal_catalog_frame() -> pd.DataFrame:
    """Return the Permission Intel signal catalog or its seeded fallback."""
    rows = load_permission_signal_catalog_rows()
    if not rows:
        rows = SIGNAL_CATALOG_ROWS
    return pd.DataFrame(rows).copy()


def signal_mapping_frame() -> pd.DataFrame:
    """Return the Permission Intel signal mappings or their seeded fallback."""
    rows = load_permission_signal_mapping_rows()
    if not rows:
        rows = SIGNAL_MAPPING_ROWS
    return pd.DataFrame(rows).copy()


def build_permission_signal_governance_coverage(
    permission_rows_df: pd.DataFrame,
    permission_signal_rows_df: pd.DataFrame,
    *,
    run_id: str,
) -> pd.DataFrame:
    """Count observed permissions and assignments by governance evidence tier."""
    columns = ["run_id", "metric", "value"]
    if not isinstance(permission_rows_df, pd.DataFrame) or permission_rows_df.empty:
        return pd.DataFrame(columns=columns)
    work = permission_rows_df.copy()
    for col in (
        "governance_precedence",
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_review_lane",
        "effective_resolution_semantics",
    ):
        series = work[col] if col in work.columns else pd.Series("", index=work.index, dtype="object")
        work[col] = series.fillna("").astype(str).str.strip().str.lower()
    work["has_effective_lane"] = work["effective_source_family_key"].ne("")
    work["has_candidate_lane"] = work["candidate_source_family_key"].ne("")
    work["has_review_lane"] = work["effective_review_lane"].ne("")
    work["has_any_governance_lane"] = (
        work["has_effective_lane"] | work["has_candidate_lane"] | work["has_review_lane"]
    )
    permission_tokens = work["permission_string"].fillna("").astype(str)
    work["is_androidx_guard_shape"] = permission_tokens.map(
        is_androidx_dynamic_receiver_permission
    )
    work["has_androidx_guard_effective_lane"] = work[
        "effective_source_family_key"
    ].eq("app_defined_dynamic_receiver_guard")
    work["has_androidx_guard_candidate_lane"] = work[
        "candidate_source_family_key"
    ].eq("app_defined_dynamic_receiver_guard")
    work["has_candidate_precedence"] = work["governance_precedence"].eq(
        "candidate"
    ) | work["effective_resolution_semantics"].eq("candidate")
    work["is_androidx_guard_effective"] = work["is_androidx_guard_shape"] & work[
        "has_androidx_guard_effective_lane"
    ] & ~work["has_candidate_precedence"]
    work["is_androidx_guard_candidate"] = work["is_androidx_guard_shape"] & (
        work["has_androidx_guard_candidate_lane"]
        | (
            work["has_androidx_guard_effective_lane"]
            & work["has_candidate_precedence"]
        )
    )
    work["is_androidx_guard_candidate_only"] = work[
        "is_androidx_guard_candidate"
    ] & ~work["is_androidx_guard_effective"]
    work["is_androidx_guard_effective_candidate_overlap"] = work[
        "is_androidx_guard_candidate"
    ] & work["is_androidx_guard_effective"]
    work["is_androidx_guard_shape_only"] = work["is_androidx_guard_shape"] & ~(
        work["is_androidx_guard_effective"] | work["is_androidx_guard_candidate"]
    )
    work["is_androidx_guard_lane_shape_mismatch"] = ~work[
        "is_androidx_guard_shape"
    ] & (
        work["has_androidx_guard_effective_lane"]
        | work["has_androidx_guard_candidate_lane"]
    )
    unique_pairs = work.drop_duplicates(subset=["sample_id", "permission_string"]).copy()
    signal_assignments = prepare_signal_assignments(permission_signal_rows_df)
    signal_pairs = signal_assignments.drop_duplicates(subset=["sample_id", "signal_key"])
    candidate_assignments = signal_assignments[
        signal_assignments["signal_evidence_tier"].eq("candidate_governance")
    ]
    raw_pattern_assignments = signal_assignments[
        signal_assignments["signal_evidence_tier"].eq("raw_pattern")
    ]
    rows = [
        {"run_id": run_id, "metric": "permission_row_count", "value": int(len(work))},
        {"run_id": run_id, "metric": "unique_sample_permission_pairs", "value": int(len(unique_pairs))},
        {"run_id": run_id, "metric": "rows_with_effective_lane", "value": int(work["has_effective_lane"].sum())},
        {"run_id": run_id, "metric": "rows_with_candidate_lane", "value": int(work["has_candidate_lane"].sum())},
        {"run_id": run_id, "metric": "rows_with_review_lane", "value": int(work["has_review_lane"].sum())},
        {
            "run_id": run_id,
            "metric": "rows_with_any_governance_lane",
            "value": int(work["has_any_governance_lane"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "unique_pairs_with_any_governance_lane",
            "value": int(unique_pairs["has_any_governance_lane"].sum()),
        },
        {"run_id": run_id, "metric": "signal_assignment_pairs", "value": int(len(signal_pairs))},
        {
            "run_id": run_id,
            "metric": "candidate_signal_assignment_pairs",
            "value": int(len(candidate_assignments)),
        },
        {
            "run_id": run_id,
            "metric": "candidate_model_eligible_pairs",
            "value": int(
                candidate_assignments["assignment_model_eligible"].astype(bool).sum()
            ),
        },
        {
            "run_id": run_id,
            "metric": "raw_pattern_signal_assignment_pairs",
            "value": int(len(raw_pattern_assignments)),
        },
        {
            "run_id": run_id,
            "metric": "raw_pattern_model_eligible_pairs",
            "value": int(
                raw_pattern_assignments["assignment_model_eligible"].astype(bool).sum()
            ),
        },
        {
            "run_id": run_id,
            "metric": "androidx_guard_shape_rows",
            "value": int(work["is_androidx_guard_shape"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "androidx_guard_effective_rows",
            "value": int(work["is_androidx_guard_effective"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "androidx_guard_candidate_rows",
            "value": int(work["is_androidx_guard_candidate"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "androidx_guard_candidate_only_rows",
            "value": int(work["is_androidx_guard_candidate_only"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "androidx_guard_effective_candidate_overlap_rows",
            "value": int(work["is_androidx_guard_effective_candidate_overlap"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "androidx_guard_shape_only_rows",
            "value": int(work["is_androidx_guard_shape_only"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "androidx_guard_lane_shape_mismatch_rows",
            "value": int(work["is_androidx_guard_lane_shape_mismatch"].sum()),
        },
    ]
    return pd.DataFrame(rows, columns=columns)


def assign_permission_signal_keys(
    permission_rows_df: pd.DataFrame, *, mapping_df: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Map observed permission rows to signal keys with evidence and eligibility."""
    assignment_columns = [
        "sample_id",
        "signal_key",
        "signal_evidence_tier",
        "assignment_model_eligible",
    ]
    if not isinstance(permission_rows_df, pd.DataFrame) or permission_rows_df.empty:
        return pd.DataFrame(columns=assignment_columns)
    work = permission_rows_df.copy()
    if "sample_id" not in work.columns or "permission_string" not in work.columns:
        return pd.DataFrame(columns=assignment_columns)
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="coerce")
    work = work.dropna(subset=["sample_id"]).copy()
    work["sample_id"] = work["sample_id"].astype(int)
    work["permission_string"] = work["permission_string"].fillna("").astype(str).str.strip().str.lower()
    work["permission_source"] = work.get("permission_source", "").fillna("").astype(str).str.upper()
    for col in (
        "governance_precedence",
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_review_lane",
        "effective_resolution_semantics",
    ):
        series = work[col] if col in work.columns else pd.Series("", index=work.index, dtype="object")
        work[col] = series.fillna("").astype(str).str.strip().str.lower()
    work = work[work["permission_string"] != ""].copy()
    if work.empty:
        return pd.DataFrame(columns=assignment_columns)

    exact_map: dict[str, set[str]] = {}
    prefix_map: list[tuple[str, str]] = []
    remediation_lane_map: dict[str, set[str]] = {}
    if mapping_df is None:
        mapping_df = signal_mapping_frame()
    for row in mapping_df.to_dict("records"):
        signal_key = str(row.get("signal_key", "")).strip()
        perm_name = str(row.get("perm_name", "")).strip().lower()
        basis = str(row.get("mapping_basis", "")).strip().lower()
        if not signal_key or not perm_name:
            continue
        if basis == "exact_permission":
            exact_map.setdefault(perm_name, set()).add(signal_key)
        elif basis == "prefix_pattern":
            prefix_map.append((perm_name, signal_key))
        elif basis == "remediation_lane":
            remediation_lane_map.setdefault(perm_name, set()).add(signal_key)

    rows: list[dict[str, Any]] = []
    legacy_push_re = re.compile(r"(?:\.permission)?\.c2d_message[a-z0-9_]*$", re.IGNORECASE)
    maps_receive_re = re.compile(r"\.permission\.maps_receive$", re.IGNORECASE)
    adm_re = re.compile(r"\.permission\.receive_adm_message$", re.IGNORECASE)
    apphub_re = re.compile(r"\.permission\.bind_apphub_service$", re.IGNORECASE)
    push_sdk_patterns = [
        re.compile(r"\.permission\.jpush_message$", re.IGNORECASE),
        re.compile(r"\.permission\.mipush_receive$", re.IGNORECASE),
        re.compile(r"\.permission\.push_provider$", re.IGNORECASE),
        re.compile(r"\.permission\.process_push_msg$", re.IGNORECASE),
        re.compile(r"getui\.permission\.getuiservice\.", re.IGNORECASE),
        re.compile(r"\.permission\.kubi_message$", re.IGNORECASE),
    ]
    launcher_patterns = [
        re.compile(r"com\.anddoes\.launcher\.permission\.update_count$", re.IGNORECASE),
        re.compile(r"com\.majeur\.launcher\.permission\.update_badge$", re.IGNORECASE),
        re.compile(r"me\.everything\.badger\.permission\.", re.IGNORECASE),
        re.compile(r"com\.android\.launcher[23]\.permission\.", re.IGNORECASE),
        re.compile(r"com\.google\.android\.launcher\.permission\.", re.IGNORECASE),
        re.compile(r"\.permission\.(?:read_settings|write_settings|receive_first_load_broadcast|receive_launch_broadcasts)$", re.IGNORECASE),
        re.compile(r"\.permission\.(?:install_shortcut|uninstall_shortcut)$", re.IGNORECASE),
        re.compile(r"\.permission\.(?:read_theme|receive_theme_update)$", re.IGNORECASE),
    ]
    lane_columns = [
        "sample_id",
        "permission_string",
        "permission_source",
        "governance_precedence",
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_review_lane",
        "effective_resolution_semantics",
    ]
    for row in work[lane_columns].drop_duplicates().to_dict(orient="records"):
        sample_id = int(row["sample_id"])
        perm = str(row["permission_string"]).strip().lower()
        source = str(row.get("permission_source", "")).strip().upper()
        effective_lane = str(row.get("effective_source_family_key", "")).strip().lower()
        candidate_lane = str(row.get("candidate_source_family_key", "")).strip().lower()
        review_lane = str(row.get("effective_review_lane", "")).strip().lower()
        precedence = str(row.get("governance_precedence", "")).strip().lower()
        resolution_semantics = str(
            row.get("effective_resolution_semantics", "")
        ).strip().lower()
        candidate_precedence = precedence == "candidate" or resolution_semantics == "candidate"
        is_androidx_guard = is_androidx_dynamic_receiver_permission(perm)
        signal_assignments: set[tuple[str, str, bool]] = set()

        def add_signal(signal_key: str, evidence_tier: str, *, model_eligible: bool) -> None:
            signal_assignments.add((signal_key, evidence_tier, model_eligible))

        for signal_key in exact_map.get(perm, set()):
            add_signal(signal_key, "exact_mapping", model_eligible=True)
        for prefix, signal_key in prefix_map:
            if perm.startswith(prefix):
                add_signal(signal_key, "prefix_mapping", model_eligible=True)
        if effective_lane != "app_defined_dynamic_receiver_guard":
            for signal_key in remediation_lane_map.get(effective_lane, set()):
                add_signal(
                    signal_key,
                    "candidate_governance"
                    if candidate_precedence
                    else "accepted_governance",
                    model_eligible=not candidate_precedence,
                )
        if candidate_lane != "app_defined_dynamic_receiver_guard":
            for signal_key in remediation_lane_map.get(candidate_lane, set()):
                add_signal(signal_key, "candidate_governance", model_eligible=False)
        for signal_key in remediation_lane_map.get(review_lane, set()):
            add_signal(signal_key, "review_governance", model_eligible=False)

        if is_androidx_guard:
            has_accepted_guard = (
                effective_lane == "app_defined_dynamic_receiver_guard"
                and not candidate_precedence
            )
            has_candidate_guard = (
                candidate_lane == "app_defined_dynamic_receiver_guard"
                or (
                    effective_lane == "app_defined_dynamic_receiver_guard"
                    and candidate_precedence
                )
            )
            if has_accepted_guard:
                add_signal(
                    "app_defined_scaffolding",
                    "accepted_governance",
                    model_eligible=True,
                )
            if has_candidate_guard:
                add_signal(
                    "app_defined_scaffolding",
                    "candidate_governance",
                    model_eligible=False,
                )
            if not has_accepted_guard and not has_candidate_guard:
                add_signal(
                    "app_defined_scaffolding",
                    "raw_pattern",
                    model_eligible=False,
                )
        if source == "GOOGLE":
            add_signal("google_gms_ecosystem", "source_classification", model_eligible=True)
        elif source == "OEM":
            add_signal("oem_vendor_ecosystem", "source_classification", model_eligible=True)
        elif source == "APP_DEFINED":
            if legacy_push_re.search(perm):
                add_signal("app_defined_scaffolding", "heuristic_pattern", model_eligible=True)
            elif maps_receive_re.search(perm):
                add_signal("app_defined_scaffolding", "heuristic_pattern", model_eligible=True)
            elif adm_re.search(perm):
                add_signal("app_defined_scaffolding", "heuristic_pattern", model_eligible=True)
            elif apphub_re.search(perm):
                add_signal("app_defined_scaffolding", "heuristic_pattern", model_eligible=True)
            elif any(pattern.search(perm) for pattern in push_sdk_patterns):
                add_signal("launcher_sdk_ecosystem_noise", "heuristic_pattern", model_eligible=True)
            elif any(pattern.search(perm) for pattern in launcher_patterns):
                add_signal("launcher_sdk_ecosystem_noise", "heuristic_pattern", model_eligible=True)
        if not signal_assignments:
            continue
        for signal_key, evidence_tier, model_eligible in sorted(signal_assignments):
            rows.append(
                {
                    "sample_id": sample_id,
                    "signal_key": signal_key,
                    "signal_evidence_tier": evidence_tier,
                    "assignment_model_eligible": model_eligible,
                }
            )
    out = pd.DataFrame(rows, columns=assignment_columns)
    if out.empty:
        return pd.DataFrame(columns=assignment_columns)
    return out.drop_duplicates(subset=assignment_columns).reset_index(drop=True)


def prepare_signal_assignments(permission_signal_rows_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize assignment fields for prevalence and coverage calculations."""
    columns = [
        "sample_id",
        "signal_key",
        "signal_evidence_tier",
        "assignment_model_eligible",
    ]
    if not isinstance(permission_signal_rows_df, pd.DataFrame) or permission_signal_rows_df.empty:
        return pd.DataFrame(columns=columns)
    if not {"sample_id", "signal_key"}.issubset(permission_signal_rows_df.columns):
        return pd.DataFrame(columns=columns)
    out = permission_signal_rows_df.copy()
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce")
    out = out.dropna(subset=["sample_id"]).copy()
    out["sample_id"] = out["sample_id"].astype(int)
    out["signal_key"] = out["signal_key"].fillna("").astype(str).str.strip()
    if "signal_evidence_tier" not in out.columns:
        out["signal_evidence_tier"] = "legacy_unspecified"
    out["signal_evidence_tier"] = (
        out["signal_evidence_tier"]
        .fillna("legacy_unspecified")
        .astype(str)
        .str.strip()
        .str.lower()
        .replace("", "legacy_unspecified")
    )
    if "assignment_model_eligible" not in out.columns:
        out["assignment_model_eligible"] = True
    else:
        out["assignment_model_eligible"] = out["assignment_model_eligible"].map(
            lambda value: value
            if isinstance(value, bool)
            else str(value).strip().lower() in {"1", "true", "yes", "on"}
        )
    out = out[out["signal_key"] != ""].copy()
    return out[columns].drop_duplicates().reset_index(drop=True)


def prepare_signal_sample_core(
    sample_core_df: pd.DataFrame,
    *,
    grouping_columns: list[str],
) -> pd.DataFrame:
    """Select sample membership and attach package keys for signal reports."""
    columns = ["sample_id", *grouping_columns]
    columns.extend(
        column
        for column in ("package_name", "android_package_name")
        if column in sample_core_df.columns
    )
    out = sample_core_df[columns].copy()
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce")
    out = out.dropna(subset=["sample_id"]).copy()
    out["sample_id"] = out["sample_id"].astype(int)
    out = out.drop_duplicates(subset=["sample_id"], keep="first")
    return assign_package_keys(out)
