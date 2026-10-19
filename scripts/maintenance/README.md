# Maintenance commands

Scripts in this directory can modify database records or operational state.
They are not normal diagnostics and should be run only with explicit operator
authorization after reviewing their dry-run output.

| Script | Effect | Safeguard |
| --- | --- | --- |
| `backfill_permission_trends_warehouse.py` | Persists an existing permission-trends bundle into warehouse tables. | Run only for a reviewed run ID and bundle; this is an explicit persistence operation. |
| `cleanup_output_artifacts.py` | Removes stale output artifacts and runtime logs while retaining configured recent runs and any explicit `--retain-run-id` historical evidence. | Default is dry-run; deletion requires `--apply`. |
| `fresh_pipeline_reset.py` | Wipes configured pipeline output to create a clean next-run layout. | Default is dry-run; destructive reset requires `--yes`. |

Run from the repository root. Keep a runbook or review record for every apply
operation; these commands are intentionally separated from read-only reports.

The former `normalize_observed_filenames.py` and
`prune_malware_artifact_ingest_queue.py` commands are retired. Catalog filename
repair and ingest-queue deletion belong to Erebus, the upstream data owner;
ObsidianDroid no longer provides these mutation paths. Their source remains
in Git history. Any upstream repair requires an owner-reviewed operation.
