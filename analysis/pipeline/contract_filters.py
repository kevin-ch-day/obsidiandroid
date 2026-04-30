"""Contract-level cohort filtering helpers for sample staging."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import app_config


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
        mal = pd.to_numeric(out.get("vt_malicious_count", 0), errors="coerce").fillna(0)
        susp = pd.to_numeric(out.get("vt_suspicious_count", 0), errors="coerce").fillna(0)
        out = out[(mal + susp) >= min_mal].copy()
        _record("min_malicious_detections", before, len(out), f">={min_mal}")

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
            chunks: list[pd.DataFrame] = []
            grouped = out.groupby("family_canonical", dropna=False, sort=True)
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

    if not gate_rows:
        _record("no_contract_filter", len(samples_df), len(out), "no additional gates")
    return out, gate_rows
