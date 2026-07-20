# Maintenance commands

Scripts in this directory can modify database records or operational state.
They are not normal diagnostics and should be run only with explicit operator
authorization after reviewing their dry-run output.

| Script | Effect | Safeguard |
| --- | --- | --- |
| `backfill_permission_trends_warehouse.py` | Persists an existing permission-trends bundle into warehouse tables. | Run only for a reviewed run ID and bundle; this is an explicit persistence operation. |
| `cleanup_output_artifacts.py` | Removes stale output artifacts and runtime logs while retaining configured recent runs and any explicit `--retain-run-id` historical evidence. | Default is dry-run; deletion requires `--apply`. |
| `fresh_pipeline_reset.py` | Wipes configured pipeline output to create a clean next-run layout. | Default is dry-run; destructive reset requires `--yes`. |
| `normalize_observed_filenames.py` | Updates clearly malformed Android `observed_filename` values in the catalog. | Review candidates first; updates require `--commit`. |
| `prune_malware_artifact_ingest_queue.py` | Deletes `DONE` + `OK` queue rows already materialized in the catalog. | Default is dry-run; deletion requires `--commit`, with optional `--workload-lane` scope. |

Run from the repository root. Keep a runbook or review record for every apply
operation; these commands are intentionally separated from read-only reports.
