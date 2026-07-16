# Operations Playbook

This playbook equips site reliability engineers and operators with procedures for running ObsidianDroid in production, maintaining data freshness, and responding to incidents. Adapt the checklist to match your organization's tooling and SLAs.

## Daily Checklist

- **Pipeline health:** Verify the latest scheduled `main.py` run completed successfully. Review orchestrator dashboards (e.g., Airflow, Prefect) for failed tasks.
- **Data freshness:** Confirm replication jobs populated the expected **primary** and **Permission Intel** tables (canonical names include `malware_sample_catalog`, `virustotal_sample_vendor_engine_verdicts`, `android_permission_obs_sample`; legacy `vt_*` aliases may appear in older notes). Reference [`data_sources.md`](data_sources.md) for schema specifics and validation steps.
- **Backlog/debt triage exports:** Refresh live curation queues before review sessions. From the startup menu use **Data Diagnostics → Refresh backlog triage exports**, or run individual scripts under `scripts/diagnostics/`:
  - `report_android_missing_resolution_triage.py` → `output/diagnostics/android_missing_resolution_triage_latest.csv` plus VT-tail and per-lane worklists
  - `report_missing_primary_label_triage.py` → `missing_primary_label_triage_latest.csv`
  - `report_blank_resolved_family_triage.py` → `blank_resolved_family_triage_latest.csv` plus singleton provenance drill-downs
  - `report_android_policy_held_token_risk.py` → `android_policy_held_token_risk_latest.csv`
  - `report_profile_family_mapping_debt.py` → `profile_family_mapping_debt_latest.{json,csv}`
  - `report_vt_false_positive_review_triage.py` → `vt_false_positive_review_triage_latest.csv`
  - `report_backlog_debt_operator_summary.py` → consolidated `backlog_debt_operator_summary_latest.{json,md}`
- **Queue buffer hygiene:** Treat `malware_artifact_ingest_queue` as a transient buffer. Successful `DONE` + `OK` rows that already exist in `malware_sample_catalog` should be pruned instead of retained. Use `python scripts/maintenance/prune_malware_artifact_ingest_queue.py` for a dry run, then rerun with `--commit` when the summary looks correct. During live backlog waves, prefer `--workload-lane <lane>` so cleanup stays scoped to the buffer you are reviewing. For direct SQL operator fallback, use `database/sql/malware_artifact_ingest_queue_buffer_audit.sql` to inspect queue shape and `database/sql/malware_artifact_ingest_queue_prune_materialized_nonprocessing_rows.sql` to remove non-processing rows that are already materialized.
- **Storage usage:** Monitor `output/` for growth. Inspection CLIs live under `scripts/diagnostics/`. Archive or prune artifacts older than retention targets.
- **Model drift signals:** Check monitoring alerts for sudden drops in precision/recall or shifts in feature distributions. Trigger retraining if thresholds are crossed.

## Weekly Checklist

- **Backfill review:** Ensure delayed samples and warehouse-dependent aggregates are caught up using **your** ETL/backlog procedures. When Permission Intel warehouse backfills are enabled, use **`scripts/maintenance/backfill_permission_trends_warehouse.py`** (see **`scripts/maintenance/README.md`**). This repo does **not** ship **`scripts/backfill_labels.py`**.
- **Dependency updates:** Review security advisories and bump pinned packages when necessary. Re-run `pytest -q` and smoke-test the pipeline afterward.
- **Dashboard hygiene:** Validate BI dashboards and shared notebooks still reflect the current schema and metrics.

## Monthly Checklist

- **Model retraining:** Schedule `python -m obsidiandroid.evaluation.model_tuning` (or your production tuning driver) with the latest labeled dataset. Promote the champion model once evaluation metrics meet acceptance criteria.
- **Disaster recovery drill:** Practice restoring the database snapshot and rehydrating VirusTotal tables from backups.
- **Documentation review:** Update user and developer guides with process changes discovered during the month.

## Incident Response

1. **Triage:** Identify whether the issue stems from data ingestion, model scoring, or downstream exports.
2. **Stabilize:** Pause scheduled jobs if they risk propagating bad data. Communicate status in the incident channel.
3. **Investigate:** Use `analysis/` notebooks and logs under `output/` to pinpoint anomalies. Capture diagnostics for postmortems.
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
