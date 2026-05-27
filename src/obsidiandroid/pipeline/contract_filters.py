"""Contract-level cohort filtering helpers for sample staging."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.diagnostics import family_label_confidence_audit
from obsidiandroid.orchestration.profile_filters import malicious_signal_or_taxonomy_mask


def apply_contract_filters(
    *,
    samples_df: pd.DataFrame,
    gates: dict[str, Any],
    run_id: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Apply contract-level cohort filters with deterministic bookkeeping."""
    out = samples_df.copy()
    gate_rows: list[dict[str, Any]] = []
    step = 1

    def _record(name: str, before: int, after: int, details: str = "") -> None:
        nonlocal step
        gate_rows.append(
            {
                "run_id": run_id,
                "step": step,
                "gate_name": name,
                "count_before": int(before),
                "count_after": int(after),
                "dropped": int(max(before - after, 0)),
                "details": details,
            }
        )
        step += 1

    evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_MODE", False))
    paper_mode = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
    exclude_unknown = bool(
        getattr(app_config, "RUNTIME_EXCLUDE_UNKNOWN_FROM_MAIN_RESULTS", False)
        or evidence_mode
        or paper_mode
    )
    if not exclude_unknown:
        exclude_unknown = bool(gates.get("exclude_unknown_type_slug", False))
    if exclude_unknown:
        before = len(out)
        normalized = (
            out["family_canonical"].fillna("").astype(str).str.strip().str.lower()
            if "family_canonical" in out.columns
            else pd.Series([""], index=out.index, dtype="object")
        )
        type_slug_norm = (
            out["type_slug"].fillna("").astype(str).str.strip().str.lower()
            if "type_slug" in out.columns
            else pd.Series([""], index=out.index, dtype="object")
        )
        invalid = {"", "unknown", "other", "unmapped", "none", "null"}
        family_ok = ~normalized.isin(invalid)
        type_ok = ~type_slug_norm.isin({"", "unknown"})
        out = out[family_ok & type_ok].copy()
        _record("exclude_unknown_type_slug", before, len(out), "family_canonical/type_slug not in unknown-set")

    min_mal = int(gates.get("min_malicious_detections", 0) or 0)
    if min_mal > 0:
        before = len(out)
        mal = pd.to_numeric(out.get("vt_malicious_count", pd.Series(pd.NA, index=out.index)), errors="coerce")
        susp = pd.to_numeric(out.get("vt_suspicious_count", pd.Series(pd.NA, index=out.index)), errors="coerce")
        consensus_total = mal.fillna(0) + susp.fillna(0)
        unknown_consensus = mal.isna() & susp.isna()
        rescued_unknown = unknown_consensus & malicious_signal_or_taxonomy_mask(out)
        out = out[(consensus_total >= min_mal) | rescued_unknown].copy()
        _record(
            "min_malicious_detections",
            before,
            len(out),
            f">={min_mal}; rescued_unknown_consensus={int(rescued_unknown.sum())}",
        )

    include_families = gates.get("include_families", []) or []
    include_families = [str(f).strip().lower() for f in include_families if str(f).strip()]
    if include_families and "family_canonical" in out.columns:
        before = len(out)
        fam = out["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        out = out[fam.isin(set(include_families))].copy()
        _record("include_families", before, len(out), f"{len(include_families)} family filters")

    exclude_families = gates.get("exclude_families", []) or []
    exclude_families = [str(f).strip().lower() for f in exclude_families if str(f).strip()]
    if exclude_families and "family_canonical" in out.columns:
        before = len(out)
        fam = out["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        sql_excluded = tuple(samples_df.attrs.get("sql_exclude_families_applied", ()))
        requested = tuple(exclude_families)
        if sql_excluded == requested:
            residual = int(fam.isin(set(exclude_families)).sum())
            if residual > 0:
                out = out[~fam.isin(set(exclude_families))].copy()
                _record(
                    "exclude_families_assertion",
                    before,
                    len(out),
                    f"sql filter mismatch fallback removed={residual}",
                )
            else:
                _record("exclude_families", before, len(out), "already_applied_in_sql")
        else:
            out = out[~fam.isin(set(exclude_families))].copy()
            _record("exclude_families", before, len(out), f"{len(exclude_families)} family filters")

    family_cap = gates.get("family_cap")
    if family_cap is not None and "family_canonical" in out.columns:
        cap_value = int(family_cap)
        if cap_value > 0:
            before = len(out)
            seed = int(gates.get("family_cap_seed", getattr(app_config, "RANDOM_STATE", 42)))
            sql_cap_applied = bool(samples_df.attrs.get("family_cap_applied_in_sql", False))
            sql_cap_value = samples_df.attrs.get("family_cap_sql_value")
            sql_cap_seed = samples_df.attrs.get("family_cap_sql_seed")
            grouped = out.groupby("family_canonical", dropna=False, sort=True)
            residual = int(max((len(group) for _, group in grouped), default=0))
            if sql_cap_applied and sql_cap_value == cap_value and residual <= cap_value:
                _record("family_cap", before, len(out), f"already_applied_in_sql;cap={cap_value};seed={sql_cap_seed}")
            else:
                chunks: list[pd.DataFrame] = []
                for _, group in grouped:
                    if len(group) <= cap_value:
                        chunks.append(group)
                    else:
                        chunks.append(group.sample(n=cap_value, random_state=seed))
                out = (
                    pd.concat(chunks, axis=0)
                    .sort_values("sample_id" if "sample_id" in out.columns else out.index.name or out.columns[0])
                    .reset_index(drop=True)
                )
                _record("family_cap", before, len(out), f"cap={cap_value};seed={seed}")

    type_cap = gates.get("type_cap")
    if type_cap is not None and "type_slug" in out.columns:
        cap_value = int(type_cap)
        if cap_value > 0:
            before = len(out)
            seed = int(gates.get("type_cap_seed", getattr(app_config, "RANDOM_STATE", 42)))
            sql_cap_applied = bool(samples_df.attrs.get("type_cap_applied_in_sql", False))
            sql_cap_value = samples_df.attrs.get("type_cap_sql_value")
            sql_cap_seed = samples_df.attrs.get("type_cap_sql_seed")
            grouped = out.groupby("type_slug", dropna=False, sort=True)
            residual = int(max((len(group) for _, group in grouped), default=0))
            if sql_cap_applied and sql_cap_value == cap_value and residual <= cap_value:
                _record("type_cap", before, len(out), f"already_applied_in_sql;cap={cap_value};seed={sql_cap_seed}")
            else:
                chunks: list[pd.DataFrame] = []
                for _, group in grouped:
                    if len(group) <= cap_value:
                        chunks.append(group)
                    else:
                        chunks.append(group.sample(n=cap_value, random_state=seed))
                out = (
                    pd.concat(chunks, axis=0)
                    .sort_values("sample_id" if "sample_id" in out.columns else out.index.name or out.columns[0])
                    .reset_index(drop=True)
                )
                _record("type_cap", before, len(out), f"cap={cap_value};seed={seed}")
    type_cap_by_slug = gates.get("type_cap_by_slug")
    if isinstance(type_cap_by_slug, dict) and "type_slug" in out.columns:
        normalized_caps = {
            str(key).strip().lower(): int(value)
            for key, value in type_cap_by_slug.items()
            if str(key).strip() and isinstance(value, int) and value > 0
        }
        if normalized_caps:
            before = len(out)
            sql_cap_applied = bool(samples_df.attrs.get("type_cap_by_slug_applied_in_sql", False))
            sql_cap_value = samples_df.attrs.get("type_cap_by_slug_sql_value")
            if sql_cap_applied and sql_cap_value == normalized_caps:
                _record("type_cap_by_slug", before, len(out), "already_applied_in_sql")
            else:
                seed = int(gates.get("type_cap_seed", getattr(app_config, "RANDOM_STATE", 42)))
                chunks: list[pd.DataFrame] = []
                grouped = out.groupby("type_slug", dropna=False, sort=True)
                for slug, group in grouped:
                    cap_value = normalized_caps.get(str(slug).strip().lower())
                    if cap_value is None or len(group) <= cap_value:
                        chunks.append(group)
                    else:
                        chunks.append(group.sample(n=cap_value, random_state=seed))
                out = (
                    pd.concat(chunks, axis=0)
                    .sort_values("sample_id" if "sample_id" in out.columns else out.index.name or out.columns[0])
                    .reset_index(drop=True)
                )
                _record("type_cap_by_slug", before, len(out), f"caps={normalized_caps};seed={seed}")

    min_confidence = gates.get("min_family_label_confidence_score")
    if min_confidence not in (None, ""):
        threshold = int(min_confidence)
        before = len(out)
        payload = family_label_confidence_audit.build_family_label_confidence_payload(
            out,
            min_support=int(gates.get("min_samples_per_family", 3) or 3),
            top_n=max(len(out), 1),
        )
        sample_rows = payload.get("sample_rows", []) if isinstance(payload, dict) else []
        score_by_sample_id = {
            str(row.get("sample_id")): int(row.get("label_confidence_score", 0))
            for row in sample_rows
            if row.get("sample_id") is not None
        }
        sample_keys = out["sample_id"].map(lambda value: str(int(float(value))) if pd.notna(value) and str(value).strip() not in {"", "nan"} else str(value))
        scores = sample_keys.map(lambda key: score_by_sample_id.get(str(key), 100))
        out = out[scores >= threshold].copy()
        dropped = int(before - len(out))
        _record(
            "min_family_label_confidence_score",
            before,
            len(out),
            f">={threshold}; dropped={dropped}",
        )

    if not gate_rows:
        _record("no_contract_filter", len(samples_df), len(out), "no additional gates")
    return out, gate_rows
