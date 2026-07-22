"""Run-scoped read-only Permission Intel protection-authority enrichment.

Queries Permission Intel with SELECT-only operations via
``obsidiandroid_pipeline_reader``. Freezes a one-row-per-token mapping for a
completed run and does not mutate databases or overwrite artifact-only reports.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import pandas as pd

from obsidiandroid.reporting.permission_governance_lanes import (
    CANONICAL_PROTECTION_LANES,
    LANE_AOSP_DANGEROUS,
    LANE_AOSP_NORMAL,
    LANE_AOSP_SIGNATURE,
    LANE_AOSP_SIGNATURE_PRIVILEGED,
    LANE_APP_DEFINED,
    LANE_GOOGLE_PLATFORM,
    LANE_OEM_PLATFORM,
    LANE_UNKNOWN_UNRESOLVED,
    classify_protection_lane,
)
from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)
from obsidiandroid.reporting.type_permission_protection import (
    EXPECTED_PERM_BEARING,
    EXPECTED_RUN_ID,
    compose_type_permission_protection,
    verify_completed_run,
)

ENRICHMENT_CONTRACT_VERSION = "1.0.0"
ENRICHED_LANE_CONTRACT_VERSION = "2.1.0"
ENRICHMENT_COMPOSER_VERSION = "1.0.0"
EXPECTED_TOKEN_COUNT = 13475
BATCH_SIZE = 400

KNOWN_BASES = frozenset({"normal", "dangerous", "signature"})
# Tokens that may appear in protection strings but are never bases.
FLAG_ONLY = frozenset(
    {
        "privileged",
        "appop",
        "appops",
        "instant",
        "role",
        "installer",
        "verifier",
        "preinstalled",
        "pre23",
        "development",
        "setup",
        "system",
        "module",
        "retailDemo",
        "retaildemo",
        "recents",
        "knownSigner",
        "knownsigner",
        "vendorPrivileged",
        "vendorprivileged",
        "oem",
    }
)

MATCH_STATUSES = (
    "exact_authority_match",
    "alias_resolved",
    "multiple_authority_conflict",
    "app_defined",
    "unknown",
    "non_permission",
    "unresolved",
)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return _sha256_text(blob)


def parse_protection_level_string(raw: Any) -> dict[str, Any]:
    """Deterministically parse Android multi-flag protection strings."""
    text = str(raw or "").strip()
    if not text:
        return {
            "raw_protection_level": "",
            "base_protection_level": "",
            "protection_flags": "",
            "parse_status": "blank",
            "multi_base_conflict": False,
        }
    # Normalize separators
    parts = [p.strip() for p in re.split(r"[|,]+", text) if p.strip()]
    # Handle glued forms like signatureOrSystem
    expanded: list[str] = []
    for part in parts:
        if part.lower() == "signatureorsystem":
            expanded.extend(["signature", "system"])
        elif part.lower() == "normal_or_signatureorsystem":
            expanded.extend(["normal", "signature", "system"])
        else:
            expanded.append(part)

    bases: list[str] = []
    flags: list[str] = []
    seen_flags: set[str] = set()
    for part in expanded:
        low = part.lower()
        if low in KNOWN_BASES:
            if low not in bases:
                bases.append(low)
        else:
            if low not in seen_flags:
                flags.append(low)
                seen_flags.add(low)

    multi = len(bases) > 1
    base = bases[0] if len(bases) == 1 else ("" if multi else "")
    if multi:
        # Prefer dangerous > signature > normal for recording primary, but mark conflict.
        for cand in ("dangerous", "signature", "normal"):
            if cand in bases:
                base = cand
                break
    return {
        "raw_protection_level": text,
        "base_protection_level": base,
        "protection_flags": ",".join(flags),
        "parse_status": "multi_base_conflict" if multi else ("ok" if base or flags else "unrecognized"),
        "multi_base_conflict": multi,
        "all_bases": "|".join(bases),
    }


def headline_lane_from_enrichment(
    *,
    run_pi_bucket_source: str,
    run_dangerous_bucket: str,
    match_status: str,
    base_protection_level: str,
    protection_flags: str,
    namespace_class: str,
) -> str:
    """Map enrichment + run namespace to a single headline lane (contract 2.1.0)."""
    if match_status == "multiple_authority_conflict":
        return LANE_UNKNOWN_UNRESOLVED
    if match_status == "non_permission":
        return LANE_UNKNOWN_UNRESOLVED
    if match_status == "app_defined" or _norm(namespace_class) == "app_defined" or _norm(run_pi_bucket_source) == "app_defined":
        return LANE_APP_DEFINED
    if _norm(namespace_class) == "oem" or _norm(run_pi_bucket_source) == "oem" or _norm(run_dangerous_bucket) == "oem_vendor":
        # OEM namespace wins unless we have structured AOSP signature from authority on same token
        if base_protection_level in KNOWN_BASES and _norm(namespace_class) in {"aosp", ""}:
            pass
        else:
            if _norm(run_pi_bucket_source) == "oem" or _norm(namespace_class) == "oem":
                return LANE_OEM_PLATFORM
    if _norm(namespace_class) == "google" or _norm(run_pi_bucket_source) == "google" or _norm(run_dangerous_bucket) == "google":
        return LANE_GOOGLE_PLATFORM

    if base_protection_level == "signature":
        flags = {_norm(x) for x in str(protection_flags).split(",") if x}
        if "privileged" in flags:
            return LANE_AOSP_SIGNATURE_PRIVILEGED
        return LANE_AOSP_SIGNATURE
    if base_protection_level == "dangerous":
        return LANE_AOSP_DANGEROUS
    if base_protection_level == "normal":
        return LANE_AOSP_NORMAL

    # Fall back to artifact-only classifier (no invented signature).
    return classify_protection_lane(
        pi_bucket_source=run_pi_bucket_source,
        dangerous_bucket=run_dangerous_bucket,
        base_protection_level="",
        protection_flags="",
    )


def load_run_token_universe(audit: pd.DataFrame) -> pd.DataFrame:
    """Deterministic sorted token universe from permission_feature_audit.csv."""
    frame = audit.copy()
    frame["normalized_token"] = frame["permission_string"].map(_norm)
    frame = frame.sort_values("normalized_token").reset_index(drop=True)
    if len(frame) != EXPECTED_TOKEN_COUNT:
        # Allow equality on unique tokens
        if frame["normalized_token"].nunique() != EXPECTED_TOKEN_COUNT and len(frame) != EXPECTED_TOKEN_COUNT:
            raise ValueError(
                f"expected {EXPECTED_TOKEN_COUNT} tokens, got rows={len(frame)} unique={frame['normalized_token'].nunique()}"
            )
    token_blob = "\n".join(frame["normalized_token"].tolist())
    return frame.assign(token_universe_hash=_sha256_text(token_blob))


def _default_pi_query_fn(sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
    from obsidiandroid.database.db_engine import execute_permission_query

    return execute_permission_query(
        sql, params=list(params) if params else None, fetch=True, as_dataframe=True
    )


def _batched_in_query(
    query_fn: Callable[..., pd.DataFrame],
    sql_template: str,
    tokens: Sequence[str],
    *,
    batch_size: int = BATCH_SIZE,
) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for i in range(0, len(tokens), batch_size):
        batch = list(tokens[i : i + batch_size])
        placeholders = ",".join(["%s"] * len(batch))
        sql = sql_template.format(placeholders=placeholders)
        part = query_fn(sql, batch)
        if part is not None and not part.empty:
            chunks.append(part)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


def fetch_permission_intel_authority(
    tokens: Sequence[str],
    *,
    query_fn: Callable[..., pd.DataFrame] | None = None,
    observed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Bounded SELECT-only PI lookups for the run token universe."""
    q = query_fn or _default_pi_query_fn
    observed = observed_at_utc or datetime.now(timezone.utc).isoformat()
    toks = sorted({_norm(t) for t in tokens if _norm(t)})

    aliases = _batched_in_query(
        q,
        """
        SELECT raw_token_norm, canonical_token_norm, rule_version,
               first_seen_at_utc, last_seen_at_utc
        FROM android_permission_token_alias
        WHERE raw_token_norm IN ({placeholders})
        """,
        toks,
    )
    alias_map = {}
    if not aliases.empty:
        for r in aliases.itertuples(index=False):
            alias_map[_norm(r.raw_token_norm)] = _norm(r.canonical_token_norm)

    lookup_tokens = sorted({alias_map.get(t, t) for t in toks} | set(toks))

    facts = _batched_in_query(
        q,
        """
        SELECT permission_string_norm, permission_string, source_family_key,
               authority_source_type, protection_level, visibility_class,
               lifecycle_status, authority_confidence, is_current_best,
               defining_package, updated_at_utc, authority_fact_id
        FROM android_permission_authority_fact
        WHERE is_current_best = 1
          AND permission_string_norm IN ({placeholders})
        """,
        lookup_tokens,
    )
    aosp = _batched_in_query(
        q,
        """
        SELECT constant_value_norm, protection_level, lifecycle_status,
               authority_source_type, source_family_key, record_updated_at_utc
        FROM android_permission_dict_aosp
        WHERE constant_value_norm IN ({placeholders})
        """,
        lookup_tokens,
    )
    oem = _batched_in_query(
        q,
        """
        SELECT permission_string_norm, protection_level, confidence,
               classification_source, record_updated_at_utc, vendor_id
        FROM android_permission_dict_oem
        WHERE permission_string_norm IN ({placeholders})
        """,
        lookup_tokens,
    )
    unknown = _batched_in_query(
        q,
        """
        SELECT permission_string_norm, triage_status, notes, seen_count,
               record_updated_at_utc
        FROM android_permission_dict_unknown
        WHERE permission_string_norm IN ({placeholders})
        """,
        lookup_tokens,
    )
    reviews = _batched_in_query(
        q,
        """
        SELECT permission_string_norm, review_status, decision_type, reviewed_at_utc
        FROM android_permission_review_state
        WHERE permission_string_norm IN ({placeholders})
        """,
        lookup_tokens,
    )

    # Conflict detection among current-best facts (should be rare).
    fact_conflicts: set[str] = set()
    if not facts.empty:
        g = facts.groupby(facts["permission_string_norm"].map(_norm))["protection_level"].nunique()
        fact_conflicts = set(g[g > 1].index.astype(str))

    return {
        "observed_at_utc": observed,
        "alias_map": alias_map,
        "aliases": aliases,
        "facts": facts,
        "aosp": aosp,
        "oem": oem,
        "unknown": unknown,
        "reviews": reviews,
        "fact_conflicts": fact_conflicts,
        "query_token_count": len(toks),
        "lookup_token_count": len(lookup_tokens),
    }


def build_enrichment_table(
    run_audit: pd.DataFrame,
    pi_bundle: Mapping[str, Any],
) -> pd.DataFrame:
    """One enrichment row per run token."""
    universe = load_run_token_universe(run_audit)
    alias_map: dict[str, str] = dict(pi_bundle.get("alias_map") or {})
    facts = pi_bundle.get("facts")
    aosp = pi_bundle.get("aosp")
    oem = pi_bundle.get("oem")
    unknown = pi_bundle.get("unknown")
    reviews = pi_bundle.get("reviews")
    fact_conflicts: set[str] = set(pi_bundle.get("fact_conflicts") or set())
    observed = str(pi_bundle.get("observed_at_utc") or "")

    fact_by = {}
    if isinstance(facts, pd.DataFrame) and not facts.empty:
        for r in facts.itertuples(index=False):
            key = _norm(r.permission_string_norm)
            fact_by.setdefault(key, []).append(r)
    aosp_by = {}
    if isinstance(aosp, pd.DataFrame) and not aosp.empty:
        for r in aosp.itertuples(index=False):
            aosp_by[_norm(r.constant_value_norm)] = r
    oem_by = {}
    if isinstance(oem, pd.DataFrame) and not oem.empty:
        for r in oem.itertuples(index=False):
            oem_by[_norm(r.permission_string_norm)] = r
    unk_by = {}
    if isinstance(unknown, pd.DataFrame) and not unknown.empty:
        for r in unknown.itertuples(index=False):
            unk_by[_norm(r.permission_string_norm)] = r
    rev_by = {}
    if isinstance(reviews, pd.DataFrame) and not reviews.empty:
        for r in reviews.itertuples(index=False):
            rev_by[_norm(r.permission_string_norm)] = r

    rows: list[dict[str, Any]] = []
    for r in universe.itertuples(index=False):
        token = _norm(r.normalized_token)
        run_src = str(getattr(r, "pi_bucket_source", "") or "")
        run_dang = str(getattr(r, "dangerous_bucket", "") or "")
        alias_src = ""
        canonical = token
        if token in alias_map and alias_map[token] != token:
            alias_src = token
            canonical = alias_map[token]

        match_status = "unresolved"
        authority_source = ""
        namespace_class = ""
        raw_pl = ""
        review_status = ""
        conflict_status = "none"
        active_state = ""

        if canonical in fact_conflicts or token in fact_conflicts:
            match_status = "multiple_authority_conflict"
            conflict_status = "multiple_current_best_protection_levels"
            facts_list = fact_by.get(canonical) or fact_by.get(token) or []
            if facts_list:
                raw_pl = str(getattr(facts_list[0], "protection_level", "") or "")
                authority_source = str(getattr(facts_list[0], "authority_source_type", "") or "")
        elif canonical in fact_by or token in fact_by:
            fr = (fact_by.get(canonical) or fact_by.get(token) or [None])[0]
            raw_pl = str(getattr(fr, "protection_level", "") or "")
            authority_source = str(getattr(fr, "authority_source_type", "") or "")
            active_state = str(getattr(fr, "lifecycle_status", "") or "")
            namespace_class = "aosp"
            match_status = "alias_resolved" if alias_src else "exact_authority_match"
            if not raw_pl:
                # authority row exists but blank protection → try AOSP dict
                if canonical in aosp_by:
                    ar = aosp_by[canonical]
                    raw_pl = str(getattr(ar, "protection_level", "") or "")
                    authority_source = authority_source or "android_permission_dict_aosp"
        elif canonical in aosp_by:
            ar = aosp_by[canonical]
            raw_pl = str(getattr(ar, "protection_level", "") or "")
            authority_source = "android_permission_dict_aosp"
            namespace_class = "aosp"
            active_state = str(getattr(ar, "lifecycle_status", "") or "")
            match_status = "alias_resolved" if alias_src else "exact_authority_match"
        elif canonical in oem_by or token in oem_by:
            orow = oem_by.get(canonical) or oem_by.get(token)
            raw_pl = str(getattr(orow, "protection_level", "") or "")
            authority_source = "android_permission_dict_oem"
            namespace_class = "oem"
            match_status = "alias_resolved" if alias_src else "exact_authority_match"
        elif _norm(run_src) == "app_defined" or _norm(run_dang) == "app_defined":
            match_status = "app_defined"
            namespace_class = "app_defined"
            authority_source = "run_audit_pi_bucket_source"
        elif _norm(run_src) == "oem":
            namespace_class = "oem"
            match_status = "unresolved"
            authority_source = "run_audit_pi_bucket_source"
        elif _norm(run_src) == "google":
            namespace_class = "google"
            match_status = "unresolved"
            authority_source = "run_audit_pi_bucket_source"
        elif canonical in unk_by or token in unk_by:
            match_status = "unknown"
            authority_source = "android_permission_dict_unknown"
        else:
            match_status = "unresolved"

        parsed = parse_protection_level_string(raw_pl)
        if parsed["multi_base_conflict"] and match_status != "multiple_authority_conflict":
            match_status = "multiple_authority_conflict"
            conflict_status = "multi_base_in_protection_string"
        if parsed.get("protection_flags", "").find("package_defined") >= 0 and not parsed["base_protection_level"]:
            match_status = "non_permission" if match_status in {"exact_authority_match", "alias_resolved", "unresolved"} else match_status

        rev = rev_by.get(canonical) or rev_by.get(token)
        if rev is not None:
            review_status = str(getattr(rev, "review_status", "") or "")

        headline = headline_lane_from_enrichment(
            run_pi_bucket_source=run_src,
            run_dangerous_bucket=run_dang,
            match_status=match_status,
            base_protection_level=str(parsed["base_protection_level"]),
            protection_flags=str(parsed["protection_flags"]),
            namespace_class=namespace_class,
        )

        payload = {
            "normalized_token": token,
            "canonical_permission": canonical,
            "authority_source": authority_source,
            "namespace_class": namespace_class,
            "raw_protection_level": parsed["raw_protection_level"],
            "base_protection_level": parsed["base_protection_level"],
            "protection_flags": parsed["protection_flags"],
            "headline_lane": headline,
            "match_status": match_status,
            "conflict_status": conflict_status,
            "active_accepted_authority_state": active_state,
            "alias_source": alias_src,
            "review_status": review_status,
            "run_pi_bucket_source": run_src,
            "run_dangerous_bucket": run_dang,
            "run_global_support": int(pd.to_numeric(getattr(r, "global_support", 0), errors="coerce") or 0),
            "run_feature_column": str(getattr(r, "feature_column", "") or ""),
            "source_observation_utc": observed,
        }
        payload["source_row_hash"] = _row_hash(payload)
        rows.append(payload)

    out = pd.DataFrame(rows).sort_values("normalized_token").reset_index(drop=True)
    if len(out) != len(universe):
        raise RuntimeError(f"token loss: enrichment={len(out)} universe={len(universe)}")
    return out


def build_lane_transition_table(
    *,
    run_audit: pd.DataFrame,
    enrichment: pd.DataFrame,
) -> pd.DataFrame:
    """Compare artifact-only lanes vs enriched lanes."""
    from obsidiandroid.reporting.permission_governance_lanes import attach_protection_lanes

    old = attach_protection_lanes(run_audit)
    old["normalized_token"] = old["permission_string"].map(_norm)
    merged = enrichment.merge(
        old[["normalized_token", "protection_governance_lane", "global_support"]],
        on="normalized_token",
        how="left",
        suffixes=("", "_old"),
    )
    rows = []
    for r in merged.itertuples(index=False):
        old_lane = str(getattr(r, "protection_governance_lane", "") or "")
        new_lane = str(getattr(r, "headline_lane", "") or "")
        reason = "unchanged"
        if old_lane != new_lane:
            if old_lane == LANE_UNKNOWN_UNRESOLVED and new_lane.startswith("aosp_"):
                reason = "authority_enriched_from_unknown"
            elif new_lane in {LANE_AOSP_SIGNATURE, LANE_AOSP_SIGNATURE_PRIVILEGED}:
                reason = "structured_signature_populated"
            elif old_lane != new_lane:
                reason = f"reclassified:{old_lane}->{new_lane}"
        rows.append(
            {
                "normalized_token": r.normalized_token,
                "old_lane": old_lane,
                "enriched_lane": new_lane,
                "transition_reason": reason,
                "match_status": getattr(r, "match_status", ""),
                "run_support": int(pd.to_numeric(getattr(r, "global_support", 0), errors="coerce") or 0),
                "observation_count": int(pd.to_numeric(getattr(r, "global_support", 0), errors="coerce") or 0),
                "affected_sample_count": int(pd.to_numeric(getattr(r, "global_support", 0), errors="coerce") or 0),
                "raw_protection_level": getattr(r, "raw_protection_level", ""),
                "base_protection_level": getattr(r, "base_protection_level", ""),
                "protection_flags": getattr(r, "protection_flags", ""),
            }
        )
    return pd.DataFrame(rows)


def enrichment_lane_lookup(enrichment: pd.DataFrame) -> dict[str, str]:
    return {
        _norm(r.normalized_token): str(r.headline_lane)
        for r in enrichment.itertuples(index=False)
    }


def build_live_vs_run_drift_note(*, observed_at_utc: str) -> str:
    return f"""# Live-versus-run scope drift note

Observation UTC: `{observed_at_utc}`

This note records that **live database counts** and **frozen run counts** are
different scopes. Live counts must not be mixed into the frozen-run analysis.

| Entity | Frozen run (`20260721T231415Z__e0c43b`) | Later live DB observation | Likely reason category |
| --- | ---: | ---: | --- |
| Godfather | 1,286 | 1,303 | source growth and/or profile/quality gate drift |
| Gigabud | 496 | 860 | profile/quality filter and/or source growth (row-level audit deferred) |
| Kuguo→retired `pua` mappings | ~670 (proposal impact) | 689 mapped | source growth / mapping refresh |
| Android ≥2020 SQL scope | 9,748 | (live catalog may grow) | source growth |
| Prepared cohort | 9,716 | n/a (run-frozen) | quality filter vs SQL scope |

Query contract: read-only `SELECT` via `obsidiandroid_pipeline_reader` on
`erebus_threat_intel_prod` / `android_permission_intel` for verification only.
Exact exclusion reasons for Gigabud/Godfather deltas require a deferred
row-level cohort audit.
"""


def apply_applite_dual_status_patch() -> dict[str, str]:
    """Return the dual-status vocabulary for Applite (docs/composer fields)."""
    return {
        "local_authority_status": "governed_curated",
        "external_context_status": "sparse_or_thin",
    }


def compose_permission_authority_enrichment(
    *,
    run_root: Path,
    run_id: str = EXPECTED_RUN_ID,
    output_dir: Path | None = None,
    enriched_protection_dir: Path | None = None,
    enriched_pairwise_dir: Path | None = None,
    repo_root: Path | None = None,
    query_fn: Callable[..., pd.DataFrame] | None = None,
    skip_enriched_compose: bool = False,
    pi_bundle: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract PI enrichment, write frozen mapping, optionally recompose enriched reports."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    identity = verify_completed_run(run_root, expected_run_id=run_id)
    run_id = identity["run_id"]
    audit_path = run_root / "diagnostics" / "permission_feature_audit.csv"
    audit = pd.read_csv(audit_path)
    universe = load_run_token_universe(audit)
    token_hash = str(universe["token_universe_hash"].iloc[0])

    observed = datetime.now(timezone.utc).isoformat()
    bundle = dict(pi_bundle) if pi_bundle is not None else fetch_permission_intel_authority(
        universe["normalized_token"].tolist(),
        query_fn=query_fn,
        observed_at_utc=observed,
    )
    if "observed_at_utc" not in bundle:
        bundle["observed_at_utc"] = observed

    enrichment = build_enrichment_table(audit, bundle)
    transitions = build_lane_transition_table(run_audit=audit, enrichment=enrichment)

    out_dir = Path(output_dir) if output_dir else run_root / "diagnostics" / "permission_authority_enrichment"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Refuse to write into artifact-only dirs
    for banned in (
        run_root / "diagnostics" / "type_permission_protection",
        run_root / "diagnostics" / "type_permission_pairwise_protection",
    ):
        if out_dir.resolve() == banned.resolve():
            raise RuntimeError("refusing to overwrite artifact-only protection directory")

    enrich_path = out_dir / "permission_authority_enrichment.csv"
    enrichment.to_csv(enrich_path, index=False)
    trans_path = out_dir / "permission_lane_transition.csv"
    transitions.to_csv(trans_path, index=False)
    drift_path = out_dir / "live_versus_run_drift_note.md"
    drift_path.write_text(build_live_vs_run_drift_note(observed_at_utc=str(bundle["observed_at_utc"])), encoding="utf-8")
    applite_path = out_dir / "applite_dual_status.json"
    applite_path.write_text(json.dumps(apply_applite_dual_status_patch(), indent=2) + "\n", encoding="utf-8")

    vocab_rows: list[dict[str, Any]] = []
    for raw, n in enrichment["raw_protection_level"].fillna("").value_counts().items():
        sub = enrichment[enrichment["raw_protection_level"].fillna("") == raw]
        vocab_rows.append(
            {
                "raw_protection_level": raw,
                "token_count": int(n),
                "base_protection_level": str(sub["base_protection_level"].iloc[0]) if len(sub) else "",
                "example_protection_flags": str(sub["protection_flags"].iloc[0]) if len(sub) else "",
                "dominant_headline_lane": str(sub["headline_lane"].value_counts().index[0])
                if len(sub)
                else "",
            }
        )
    vocab_path = out_dir / "protection_level_vocabulary.csv"
    pd.DataFrame(vocab_rows).to_csv(vocab_path, index=False)
    conflict_path = out_dir / "authority_conflicts.csv"
    enrichment.loc[
        enrichment["match_status"] == "multiple_authority_conflict",
        [
            "normalized_token",
            "raw_protection_level",
            "conflict_status",
            "match_status",
            "headline_lane",
            "authority_source",
        ],
    ].to_csv(conflict_path, index=False)

    # Summaries
    lane_counts = enrichment["headline_lane"].value_counts().to_dict()
    moved = transitions[transitions["old_lane"] != transitions["enriched_lane"]]
    summary = {
        "token_count": int(len(enrichment)),
        "token_universe_hash": token_hash,
        "lane_counts_enriched": {k: int(v) for k, v in lane_counts.items()},
        "tokens_moved": int(len(moved)),
        "tokens_moved_out_of_unknown": int(
            ((transitions["old_lane"] == LANE_UNKNOWN_UNRESOLVED) & (transitions["enriched_lane"] != LANE_UNKNOWN_UNRESOLVED)).sum()
        ),
        "signature_tokens": int((enrichment["headline_lane"] == LANE_AOSP_SIGNATURE).sum()),
        "signature_privileged_tokens": int(
            (enrichment["headline_lane"] == LANE_AOSP_SIGNATURE_PRIVILEGED).sum()
        ),
        "match_status_counts": {k: int(v) for k, v in enrichment["match_status"].value_counts().items()},
        "applite_dual_status": apply_applite_dual_status_patch(),
    }

    query_hash = _sha256_text(
        json.dumps(
            {
                "batch_size": BATCH_SIZE,
                "tables": [
                    "android_permission_token_alias",
                    "android_permission_authority_fact",
                    "android_permission_dict_aosp",
                    "android_permission_dict_oem",
                    "android_permission_dict_unknown",
                    "android_permission_review_state",
                ],
                "token_universe_hash": token_hash,
                "query_token_count": bundle.get("query_token_count"),
                "lookup_token_count": bundle.get("lookup_token_count"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    output_hashes = {
        enrich_path.name: sha256_file(enrich_path),
        trans_path.name: sha256_file(trans_path),
        drift_path.name: sha256_file(drift_path),
        applite_path.name: sha256_file(applite_path),
        vocab_path.name: sha256_file(vocab_path),
        conflict_path.name: sha256_file(conflict_path),
    }

    enriched_manifest = None
    if not skip_enriched_compose:
        e_prot = (
            Path(enriched_protection_dir)
            if enriched_protection_dir
            else run_root / "diagnostics" / "type_permission_protection_enriched"
        )
        e_pair = (
            Path(enriched_pairwise_dir)
            if enriched_pairwise_dir
            else run_root / "diagnostics" / "type_permission_pairwise_protection_enriched"
        )
        if e_prot.resolve() == (run_root / "diagnostics" / "type_permission_protection").resolve():
            raise RuntimeError("refusing to overwrite artifact-only protection dir")
        enriched_manifest = compose_type_permission_protection(
            run_root=run_root,
            run_id=run_id,
            output_dir=e_prot,
            pairwise_output_dir=e_pair,
            repo_root=repo_root,
            load_aligned_features=True,
            enrichment_csv=enrich_path,
            lane_contract_version=ENRICHED_LANE_CONTRACT_VERSION,
            enrichment_kind="POST_RUN_READ_ONLY_AUTHORITY_ENRICHMENT",
        )
        # Pairwise comparison vs artifact-only
        art_pair = run_root / "diagnostics" / "type_permission_protection" / "type_permission_pairwise_protection.csv"
        enr_pair = e_prot / "type_permission_pairwise_protection.csv"
        if art_pair.is_file() and enr_pair.is_file():
            cmp = _pairwise_comparison(art_pair, enr_pair)
            cmp_path = out_dir / "artifact_vs_enriched_pairwise_comparison.csv"
            cmp.to_csv(cmp_path, index=False)
            output_hashes[cmp_path.name] = sha256_file(cmp_path)

    manifest = {
        "composer": "permission_authority_enrichment",
        "composer_version": ENRICHMENT_COMPOSER_VERSION,
        "enrichment_contract_version": ENRICHMENT_CONTRACT_VERSION,
        "enriched_lane_contract_version": ENRICHED_LANE_CONTRACT_VERSION,
        "enrichment_kind": "POST_RUN_READ_ONLY_AUTHORITY_ENRICHMENT",
        "original_run_time_authority_frozen": False,
        "source_run_artifacts": "frozen",
        "permission_intel_observation_utc": bundle["observed_at_utc"],
        "generated_at_utc": generated_at,
        "run_id": run_id,
        "profile_id": identity["profile_id"],
        "repository_commit_at_run": identity["repository_commit"],
        "repository_commit_at_compose": resolve_git_commit(repo_root) if repo_root else "",
        "dataset_hash": identity["dataset_hash"],
        "token_universe_hash": token_hash,
        "permission_intel_query_hash": query_hash,
        "source_schema_contract": "docs/PERMISSION_INTEL_AUTHORITY_SOURCE_CONTRACT.md",
        "expected_token_count": EXPECTED_TOKEN_COUNT,
        "permission_bearing_sample_count": EXPECTED_PERM_BEARING,
        "summary": summary,
        "input_hashes": {
            "permission_feature_audit": sha256_file(audit_path),
            "run_manifest": sha256_file(run_root / "run_manifest.json"),
        },
        "output_hashes": output_hashes,
        "boundaries": {
            "database_writes": False,
            "core_access": False,
            "taxonomy_mutation": False,
            "pipeline_execution": False,
            "artifact_only_reports_mutated": False,
            "permission_intel_writes": False,
        },
        "run_status": identity["run_status"],
        "enriched_protection_manifest": enriched_manifest,
    }
    man_path = out_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_hashes["manifest.json"] = sha256_file(man_path)
    manifest["output_hashes"] = output_hashes
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sha_lines = [f"{digest}  {name}" for name, digest in sorted(output_hashes.items())]
    (out_dir / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    return manifest


def _pairwise_comparison(artifact_csv: Path, enriched_csv: Path) -> pd.DataFrame:
    def _safe_read(path: Path) -> pd.DataFrame:
        try:
            if path.stat().st_size == 0:
                return pd.DataFrame()
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    a = _safe_read(artifact_csv)
    e = _safe_read(enriched_csv)
    def _counts(df: pd.DataFrame) -> dict[str, int]:
        out = {
            "rows": int(len(df)),
            "within_lane": int((df.get("lane_pair_class") == "within_lane").sum()) if "lane_pair_class" in df else 0,
            "cross_lane": int((df.get("lane_pair_class") == "cross_lane").sum()) if "lane_pair_class" in df else 0,
        }
        if "reportability_status" in df.columns:
            for status, n in df["reportability_status"].value_counts().items():
                out[f"status::{status}"] = int(n)
        if "leave_largest_family_result" in df.columns:
            for status, n in df["leave_largest_family_result"].value_counts().items():
                out[f"leave::{status}"] = int(n)
        return out
    ca, ce = _counts(a), _counts(e)
    keys = sorted(set(ca) | set(ce))
    return pd.DataFrame(
        [
            {
                "metric": k,
                "artifact_only": ca.get(k, 0),
                "authority_enriched": ce.get(k, 0),
                "delta_enriched_minus_artifact": ce.get(k, 0) - ca.get(k, 0),
            }
            for k in keys
        ]
    )


__all__ = [
    "ENRICHMENT_CONTRACT_VERSION",
    "ENRICHED_LANE_CONTRACT_VERSION",
    "parse_protection_level_string",
    "headline_lane_from_enrichment",
    "build_enrichment_table",
    "compose_permission_authority_enrichment",
    "fetch_permission_intel_authority",
    "enrichment_lane_lookup",
    "apply_applite_dual_status_patch",
]
