# Operations Playbook

This playbook lists checks for an ObsidianDroid deployment. It does not imply
that a scheduler, alerting stack, upstream replication job, or retention policy
is installed on a particular host. Verify those deployment facts locally and
keep Erebus and Permission Intel source mutations with their owning systems.

## Daily Checklist

- **Pipeline health:** If a run is scheduled, check its run manifest,
  `run_evidence_index.md`, and `diagnostics/run_observability_summary.json`
  before treating it as complete. Check an external scheduler only if this
  deployment uses one.
- **Data freshness:** Inspect bounded, read-only source evidence in the
  configured **primary** and **Permission Intel** schemas; the key surfaces
  include `malware_sample_catalog`,
  `virustotal_sample_vendor_engine_verdicts`, and the separately approved exact
  PI V2 export. On a gated host, do not use legacy observation queries as a daily
  prerequisite. Compare retained evidence timestamps and exact membership with
  the run's frozen source snapshot. See [`data_sources.md`](data_sources.md).
- **Backlog/debt triage exports:** Refresh live curation queues before review sessions. From the startup menu use **Data Diagnostics → Refresh backlog triage exports**, or run individual scripts under `scripts/diagnostics/`:
  - `report_android_missing_resolution_triage.py` → `output/diagnostics/android_missing_resolution_triage_latest.csv` plus VT-tail and per-lane worklists
  - `report_missing_primary_label_triage.py` → `missing_primary_label_triage_latest.csv`
  - `report_blank_resolved_family_triage.py` → `blank_resolved_family_triage_latest.csv` plus singleton provenance drill-downs
  - `report_android_policy_held_token_risk.py` → `android_policy_held_token_risk_latest.csv`
  - `report_profile_family_mapping_debt.py` → `profile_family_mapping_debt_latest.{json,csv}`
  - `report_vt_false_positive_review_triage.py` → `vt_false_positive_review_triage_latest.csv`
  - `report_backlog_debt_operator_summary.py` → consolidated `backlog_debt_operator_summary_latest.{json,md}`
- **Queue buffer review:** `malware_artifact_ingest_queue` belongs to Erebus.
  Use `database/sql/malware_artifact_ingest_queue_buffer_audit.sql` only for
  bounded read-only inspection. Do not turn ObsidianDroid's legacy prune
  script or direct DELETE SQL into a routine cleanup step; any deletion needs
  an exact Erebus-owned review, backup/recovery path, and separate authorization.
- **Storage usage:** Monitor `output/` growth. Verify artifact identity and
  preservation requirements before applying any reviewed retention policy.
- **Model drift signals:** If monitoring exists, inspect changes in measured
  metrics and feature distributions; retraining and model selection remain
  separate reviewed research actions.

## Weekly Checklist

- **Backfill review:** Inspect delayed upstream samples and run-scoped outputs.
  The legacy permission-trends warehouse writer is an explicit reviewed
  maintenance action, not part of the default read-only pipeline; see
  [`scripts/maintenance/README.md`](../scripts/maintenance/README.md).
- **Dependency updates:** Review security advisories and bump pinned packages when necessary. Re-run `pytest -q` and smoke-test the pipeline afterward.
- **Dashboard hygiene:** Validate BI dashboards and shared notebooks still reflect the current schema and metrics.

## Monthly Checklist

- **Model retraining:** When a new research run is warranted, freeze its source
  cohort and evaluate candidate models. Do not infer model promotion from a
  tuning command or a single metric.
- **Disaster recovery drill:** Follow the owning system's reviewed restore
  procedure for each upstream schema and preserve ObsidianDroid Core and
  filesystem artifacts according to their separate recovery contracts.
- **Documentation review:** Update user and developer guides with process changes discovered during the month.

## Incident Response

1. **Triage:** Identify whether the issue stems from data ingestion, model scoring, or downstream exports.
2. **Stabilize:** Pause scheduled jobs if they risk propagating bad data. Communicate status in the incident channel.
3. **Investigate:** Use the run manifest, evidence index, diagnostics, and
   logs under `output/` to pinpoint anomalies. The retired root `analysis/`
   package is not an operator entrypoint.
4. **Mitigate:** Apply targeted fixes (e.g., rerun a failed task, revert a configuration change). Document temporary workarounds.
5. **Recover:** Resume paused jobs, validate outputs, and update stakeholders.
6. **Postmortem:** Within 48 hours, publish a post-incident report detailing impact, root cause, fixes, and follow-up actions.

## On-Call Essentials

- Maintain runbooks for recurring alarms (e.g., database connection pool exhaustion, VirusTotal replication lag).
- Configure alert routing to reach on-call engineers via chat, SMS, or pager systems.
- Keep a rotation calendar with clear escalation paths and contact details.
- Ensure access to secrets management, orchestrator dashboards, and log aggregation tools.

## Change Management

- Use feature flags or configuration toggles for risky changes. Stage updates in a test environment before production rollout.
- Schedule maintenance windows for migrations affecting `database/` schemas or large backfills.
- Communicate upcoming changes to stakeholders and document expected impacts in release notes.

## Knowledge Base Suggestions

Capture recurring operational knowledge in a shared wiki or `docs/` additions, such as:

- Common error codes and remediation steps.
- Database schema diagrams and table ownership.
- Alert thresholds and rationale.
- Contacts for VirusTotal replication ownership and data engineering support.

Maintaining this playbook—and iterating after each incident—ensures ObsidianDroid remains reliable and auditable for investigators and downstream consumers.
