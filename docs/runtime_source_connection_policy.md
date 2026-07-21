# Normal Runtime Source-Connection Policy

ObsidianDroid has three distinct database boundaries.  The two upstream source
schemas are read by normal analysis; `obsidiandroid_core_prod` is an
ObsidianDroid-owned evidence ledger and remains disabled until a separately
authorized phase enables it.  Filesystem run artifacts remain the output
authority for normal analysis today.

## Explicit runtime modes

`OBSIDIANDROID_RESULTS_PERSISTENCE_MODE` is required to select legacy database
output behavior.  The default is `read_only`:

| Mode | Source grants | Legacy Erebus warehouse | Core persistence |
| --- | --- | --- | --- |
| `read_only` (default) | `SELECT` only | disabled | disabled |
| `legacy_warehouse` | historical writer grants | enabled, temporary compatibility path | disabled |

The application never falls back from one mode to the other.  The first
desktop acceptance run must use `read_only`; the profile menu prints the
effective mode before a profile is selected.

The legacy path is `stage_permission_trends_report.py` →
`stage_results_warehouse.py`.  It creates and upserts historical
`analysis_*`/permission-trends warehouse tables in Erebus.  It is not a Core
path and must not be enabled with a reader credential.

## Normal pipeline reader

`obsidiandroid_pipeline_reader@localhost` is the dedicated normal-analysis
identity. It has schema-level `SELECT` on `erebus_threat_intel_prod` and
`android_permission_intel`, and no grants on Core or rehearsal schemas. It has
no DML, DDL, routine, or global privileges beyond MariaDB's implicit `USAGE`.

- `obsidiandroid_erebus_reader@localhost` remains restricted to five Phase 2C
  recovery surfaces and is never a normal pipeline credential.
- `erebus_app@localhost` retains broad legacy write and routine privileges on
  both source schemas, so it is not suitable for read-only acceptance runs.

Schema-level `SELECT` for the dedicated reader is intentional: the
normal pipeline uses a broad, evolving group of catalog, VirusTotal,
family/type authority, cohort-readiness, permission-observation, dictionary,
and view surfaces.  Object-by-object grants would be fragile and risk an
incomplete runtime contract.

The applied account contract is:

```sql
CREATE USER 'obsidiandroid_pipeline_reader'@'localhost' IDENTIFIED BY '<generated secret>';
GRANT SELECT ON `erebus_threat_intel_prod`.* TO 'obsidiandroid_pipeline_reader'@'localhost';
GRANT SELECT ON `android_permission_intel`.* TO 'obsidiandroid_pipeline_reader'@'localhost';
```

Store the generated secret only in
`~/.config/obsidiandroid/pipeline-reader.cnf`, owned by the operator and mode
`0600`.  Do not use the administrator option file, a Phase 2C credential file,
or a repository file.  A non-secret `.env.local` reference may name that file:

```text
OBSIDIAN_DB_OPTION_FILE=/home/<operator>/.config/obsidiandroid/pipeline-reader.cnf
OBSIDIAN_DB_NAME=erebus_threat_intel_prod
OBSIDIAN_PERMISSION_INTEL_DB_NAME=android_permission_intel
OBSIDIANDROID_CORE_PERSISTENCE_ENABLED=false
```

## Safe audit

Run `make audit-runtime-db` before profile selection.  It emits only
credential-redacted configuration state and bounded `SELECT` health checks for
the normal source surfaces; it never connects to Core, writes source data, or
starts a pipeline.

Routine menu profile selection uses a bounded viability probe, not the full
cohort aggregate/count diagnostic:

- Census profiles that admit unmapped families (`require_mapped_family: false`
  without type/family/quality filters) use a catalog + hash-registry
  `LIMIT 1` existence probe.
- Mapped/typed profiles use a **filtered** authority candidate window: an
  unfiltered `LIMIT` on the authority view (cheap on MariaDB), Python-side
  type/family/active filters, then catalog + hash-registry + time checks.  If
  the first window has no matching typed rows, the probe falls back to a
  catalog-seeded authority point lookup (`sample_id IN (...)`) so typed profiles
  are not false-negatived by an unlucky early authority sample.

A positive result proves at least one eligible row (or one family meeting the
configured support floor inside the filtered window). A statement timeout or an
exhausted filtered window after catalog/time filtering is reported as
inconclusive rather than as an empty cohort when authority candidates existed.
An authority filter that returns no candidates is reported as an empty gated
cohort. `get_type_cohort_gate_stats()` remains the explicit, potentially
expensive diagnostic path for exact counts and marginal exclusions.

Menu "Current Android Catalog Coverage" is ungated inventory
(`android_platform` readiness). Governed runs also apply the reproducibility
time window, hash-registry join, and profile cohort gates; those counts are
often smaller than the inventory headline.

## Static read/write boundary inventory

Normal analysis requires broad source reads.  The current code routes Erebus
catalog and VirusTotal reads through `obsidiandroid.database.db_engine` and
the following representative modules: `db_sample_metadata_fetchers.py`,
`db_cohort_readiness.py`, `authority_contracts.py`,
`db_av_engine_stats.py`, and `db_fetch_av_engine_raw_results.py`.  Required
objects include `malware_sample_catalog`, VirusTotal verdict and engine
surfaces, `vt_sample_verdict_confidence_current`,
`v_android_sample_family_type_authority`, taxonomy/alias facts, and
cohort-readiness support views.  Permission Intel reads use
`android_permission_obs_sample`, `android_permission_dict_aosp`,
`android_permission_dict_oem`, `android_permission_dict_unknown`, and related
enrichment/readiness views.

Optional diagnostics use the same read boundary for temporal, family-mapping,
and parser-health reports.  Maintenance scripts, including ingest-tranche and
backfill tools, are not startup-menu analysis paths and may contain explicit
source DML; they remain maintenance-only.  Phase 2C has its own five-table
extract reader.  Future Core imports use the separately guarded Phase 2D
route.  The only normal runtime source writer is the historical
permission-trends warehouse exporter; it is disabled in `read_only` mode.
