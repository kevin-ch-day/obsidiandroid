"""Shared vocabulary for cohort row counts (SQL scope vs prepared dataframe).

**Cohort SQL scope** — Head count of catalog rows matching the profile cohort definition
(same joins, time contract, and taxonomy gates as the SQL loader). This is *not* the length
of ``samples_df`` when Python-side dedupe or extra filters apply.

**Prepared cohort** — Rows in ``samples_df`` after ``load_and_prepare_samples`` (what AV
and feature stages consume).

Canonical JSON keys (use in new code and docs):

* ``cohort_sql_scope_row_count`` — mirrors legacy ``gate_total_candidates`` /
  ``raw_candidate_rows`` (those duplicates meant the same SQL scope count).
* ``cohort_prepared_row_count`` — mirrors legacy ``governed_cohort_rows`` for this stage.

Legacy keys remain populated on manifests and observability summaries so older tooling
keeps working.

**Profile operator knobs** (YAML keys are stable; descriptions match semantics):

* ``cohort_gates.upstream_expected_min_gate_total`` — optional floor for the SQL scope
  head count (``total_candidates`` / ``cohort_sql_scope_row_count``). Used to warn when a
  DB snapshot looks incomplete (e.g. Erebus rebuild). Override with environment variable
  ``SCYTALEDROID_COHORT_EXPECTED_MIN_GATE_TOTAL``.
"""

from __future__ import annotations

from typing import Any

# --- Canonical keys (preferred) ---
KEY_COHORT_SQL_SCOPE_ROW_COUNT = "cohort_sql_scope_row_count"
KEY_COHORT_PREPARED_ROW_COUNT = "cohort_prepared_row_count"

# --- Legacy mirrors (same integers as above when set by the runner) ---
LEGACY_KEY_GATE_TOTAL_CANDIDATES = "gate_total_candidates"
LEGACY_KEY_RAW_CANDIDATE_ROWS = "raw_candidate_rows"
LEGACY_KEY_GOVERNED_COHORT_ROWS = "governed_cohort_rows"

# Preflight bundle written for samples-only / cohort audits
KEY_SAMPLES_STAGE_COHORT_COUNTS = "samples_stage_cohort_counts"


def read_sql_scope_row_count(manifest_context: dict[str, Any] | None) -> int | None:
    """SQL-scope head count from manifest context (canonical key first, then legacy)."""
    if not isinstance(manifest_context, dict):
        return None
    for key in (
        KEY_COHORT_SQL_SCOPE_ROW_COUNT,
        LEGACY_KEY_GATE_TOTAL_CANDIDATES,
        LEGACY_KEY_RAW_CANDIDATE_ROWS,
    ):
        raw = manifest_context.get(key)
        if raw is None or raw == "":
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def read_prepared_cohort_row_count(manifest_context: dict[str, Any] | None) -> int | None:
    """Prepared-cohort row count from manifest context."""
    if not isinstance(manifest_context, dict):
        return None
    for key in (KEY_COHORT_PREPARED_ROW_COUNT, LEGACY_KEY_GOVERNED_COHORT_ROWS):
        raw = manifest_context.get(key)
        if raw is None or raw == "":
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def attach_cohort_row_counts_to_manifest_context(
    manifest_context: dict[str, Any],
    *,
    sql_scope_row_count: int,
    prepared_row_count: int,
) -> None:
    """Write canonical + legacy cohort count keys (legacy = compatibility only)."""
    manifest_context[KEY_COHORT_SQL_SCOPE_ROW_COUNT] = int(sql_scope_row_count)
    manifest_context[KEY_COHORT_PREPARED_ROW_COUNT] = int(prepared_row_count)
    manifest_context[LEGACY_KEY_GATE_TOTAL_CANDIDATES] = int(sql_scope_row_count)
    manifest_context[LEGACY_KEY_RAW_CANDIDATE_ROWS] = int(sql_scope_row_count)
    manifest_context[LEGACY_KEY_GOVERNED_COHORT_ROWS] = int(prepared_row_count)
