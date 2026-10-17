# Normal Runtime Source-Connection Policy

ObsidianDroid has three distinct database boundaries. The two upstream source
schemas are read by normal analysis. `obsidiandroid_core_prod` is a separate
ObsidianDroid-owned evidence ledger. Normal profile execution defaults to
read-only source access and filesystem run artifacts; the explicit native
analysis-persistence route has its own plan, writer, and Core contract in
[ANALYSIS_PERSISTENCE_V1.md](ANALYSIS_PERSISTENCE_V1.md). This document's
mode table governs the legacy source-warehouse path, not that explicit route.

## Explicit runtime modes

`OBSIDIANDROID_RESULTS_PERSISTENCE_MODE` is required to select legacy database
output behavior.  The default is `read_only`:

| Mode | Source grants | Legacy Erebus warehouse | Core persistence |
| --- | --- | --- | --- |
| `read_only` (default) | `SELECT` only | disabled | not selected by normal profile mode |
| `legacy_warehouse` | historical writer grants | enabled, temporary compatibility path | not selected by this mode |

The application never falls back from one mode to the other.  The first
desktop acceptance run must use `read_only`; the profile menu prints the
effective mode before a profile is selected.

The legacy path is `stage_permission_trends_report.py` →
`stage_results_warehouse.py`.  It creates and upserts historical
`analysis_*`/permission-trends warehouse tables in Erebus.  It is not a Core
path and must not be enabled with a reader credential.

## Normal pipeline reader

`obsidiandroid_pipeline_reader@localhost` is the dedicated normal-analysis
identity. The verified 2026-10-17 PI V2 production boundary grants schema-level
`SELECT` on `erebus_threat_intel_prod`, but only gate-table `SELECT` in
`android_permission_intel`. Direct reads of `android_permission_obs_sample` and
`android_permission_enrich_vt_current` are denied. No Core grants, DML, DDL,
routine or grantable privileges were introduced by consumer activation.

The earlier schema-wide PI SELECT bootstrap is superseded on this gated host.
Do not restore that grant to satisfy an old visibility check. Exact V2 research
consumption uses the separately root-approved export and its validated consumer;
legacy database readers remain blocked. Other hosts must verify their own reviewed
account contract rather than infer it from this dated workstation observation.

- `obsidiandroid_erebus_reader@localhost` remains the separate Phase 2C identity.
- `erebus_app@127.0.0.1` remains a separate Erebus application identity; its
  broader read-only grants do not define the research-reader contract.

### Split-database health under the V2 gate

`python -m obsidiandroid.database.split_db_health` distinguishes connection health,
legacy table visibility and effective legacy access. `permission_obs_sample_in_pi`
reports visibility to the current account; false does not prove the table is absent.
For gate BLOCK, `LEGACY_ACCESS_PROTECTED` requires actual SELECT probes of both
legacy surfaces to fail with table/column privilege denial (1142/1143). A successful
legacy read reports `UNSAFE_LEGACY_ACCESS`; missing tables, malformed gates and
unexpected query failures report `UNVERIFIED`, and the CLI fails. A pre-V2 host
with no gate can retain its existing visible-table health behavior.

Successful connectivity plus either verified protected access or the supported
legacy-readable state passes this connectivity/access diagnostic. The report
always sets `permission_v2_consumer_status` to `NOT_CHECKED`: it does not establish
export approval, feature eligibility or research completeness. Use the separate
anchored consumer acceptance for those claims. No health check changes grants,
releases BLOCK, or starts model training.

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
cohort-readiness support views. Historical direct Permission Intel paths still
reference observation, dictionary and enrichment tables, but they are not the
approved recovered-evidence interface on the V2-gated host. Their storage
inventory does not grant current read authority. Exact V2 consumption uses the
separately approved export; unsupported legacy paths remain unavailable.

Optional diagnostics use the same read boundary for temporal, family-mapping,
and parser-health reports.  Maintenance scripts, including ingest-tranche and
backfill tools, are not startup-menu analysis paths and may contain explicit
source DML; they remain maintenance-only.  Phase 2C has its own five-table
extract reader.  Future Core imports use the separately guarded Phase 2D
route.  The only normal runtime source writer is the historical
permission-trends warehouse exporter; it is disabled in `read_only` mode.

### Runtime audit outcome

`make audit-runtime-db` shares the split-health access classifier. Under verified
legacy protection it reports observation reads as `blocked_as_intended` and
skips dictionary availability checks not required by the exact export route.
The report includes `audit_ok`; the CLI exits nonzero for failed or unverified
required checks. It never reports V2 consumer approval: that remains an independent
anchored acceptance check. `check_connections=False` remains explicitly unchecked.
