# Operations Playbook

This playbook equips site reliability engineers and operators with procedures for running ObsidianDroid in production, maintaining data freshness, and responding to incidents. Adapt the checklist to match your organization's tooling and SLAs.

## Daily Checklist

- **Pipeline health:** Verify the latest scheduled `main.py` run completed successfully. Review orchestrator dashboards (e.g., Airflow, Prefect) for failed tasks.
- **Data freshness:** Confirm VirusTotal replication jobs populated the expected tables (`vt_av_engines*`, `vt_permissions`, `vt_file_metadata`, `vt_network_metadata`). Reference [`data_sources.md`](data_sources.md) for schema specifics and validation steps.
- **Storage usage:** Monitor the `output/` and `data_inspect/` directories for growth. Archive or prune artifacts older than retention targets.
- **Model drift signals:** Check monitoring alerts for sudden drops in precision/recall or shifts in feature distributions. Trigger retraining if thresholds are crossed.

## Weekly Checklist

- **Backfill review:** Ensure delayed samples are captured by running `scripts/backfill_labels.py` against the backlog.
- **Dependency updates:** Review security advisories and bump pinned packages when necessary. Re-run `pytest -q` and smoke-test the pipeline afterward.
- **Dashboard hygiene:** Validate BI dashboards and shared notebooks still reflect the current schema and metrics.

## Monthly Checklist

- **Model retraining:** Schedule `model_tuning.py` with the latest labeled dataset. Promote the champion model once evaluation metrics meet acceptance criteria.
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
