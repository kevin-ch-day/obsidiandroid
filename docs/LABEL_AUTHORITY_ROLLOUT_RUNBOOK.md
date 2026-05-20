# Label Authority Rollout Runbook

This runbook describes the intended first deployment path for the label-authority
work in Erebus without changing ObsidianDroid training behavior.

## Goals

- expose existing governed family/type authority through one stable read-only view
- preserve current resolved family truth while making authority buckets explicit
- prepare for future label-noise diagnostics without relabeling samples

## Pre-flight

Confirm the live Erebus schema has the existing authority objects:

- `malware_sample_catalog`
- `android_malware_family`
- `android_malware_family_alias`
- `android_malware_type`
- `v_android_apk_family_norm`
- `v_android_apk_family_resolved`

Optional environment sanity check:

```bash
PYTHONPATH=src:. python scripts/diagnostics/report_family_type_authority_coverage.py
```

Before the view is applied, the script may report `Source mode: embedded_sql_fallback`.

## Apply Order

Use staging first when possible. The **current safe step** is the read-only view only.

1. Apply the read-only authority view:

```sql
SOURCE database/sql/view_android_sample_family_type_authority.sql;
```

2. Run the smoke checks:

```sql
SOURCE database/sql/view_android_sample_family_type_authority_smoke.sql;
```

3. Run the non-invasive coverage report:

```bash
PYTHONPATH=src:. python scripts/diagnostics/report_family_type_authority_coverage.py
```

Expected:

- `Source mode: live_view`
- authority buckets align with the SQL audit
- Devixor raw-vs-authority conflict remains visible
- missing-family and unknown-type queues align with curation priorities

## Deferred Foundation Work

Do **not** apply these as part of the current safe rollout:

- `label_authority_foundation.sql`
- `label_authority_backfill.sql`
- `label_authority_reference_seed.sql`
- `label_authority_vendor_evidence_backfill.sql`
- `label_authority_vendor_evidence_load_template.sql`
- `label_authority_audit.sql`
- `label_authority_schema_smoke.sql`

These remain future schema work for a broader label-authority foundation after the
read-only authority view is stable and trusted downstream.

## Later Parser-Enriched Export

When the broader foundation work is resumed, the SQL vendor-evidence seed preserves
raw labels only. To prepare a parser-enriched review file or a future bulk load:

```bash
PYTHONPATH=src:. python scripts/diagnostics/export_label_authority_vendor_evidence.py
```

Optional smaller export:

```bash
PYTHONPATH=src:. python scripts/diagnostics/export_label_authority_vendor_evidence.py --limit 500
```

This creates:

- `output/diagnostics/label_authority_vendor_evidence_seed_latest.csv`

Fields align with the `malware_family_label_evidence` table and include:

- `parsed_family_token`
- `parsed_type_token`
- `parsed_class_token`
- `generic_token_flag`
- parser name/version/confidence

You can then summarize the export and generate alias-review candidates:

```bash
PYTHONPATH=src:. python scripts/diagnostics/summarize_label_authority_vendor_evidence.py
```

This creates:

- `output/diagnostics/label_authority_vendor_evidence_summary_latest.md`
- `output/diagnostics/label_authority_alias_candidates_latest.csv`

You can also produce a read-only label-noise candidate report:

```bash
PYTHONPATH=src:. python scripts/diagnostics/report_label_noise_candidates.py
```

This creates:

- `output/diagnostics/label_noise_candidates_latest.csv`
- `output/diagnostics/label_noise_candidates_summary_latest.md`

## Later Bulk-Load Template

If the parser-enriched CSV looks clean enough for staging review later, the repository
includes a template load path:

```sql
SOURCE database/sql/label_authority_vendor_evidence_load_template.sql;
```

That script intentionally uses a temporary staging table first. Adjust the CSV path
inside the `LOAD DATA LOCAL INFILE` statement before running it.

## What To Review Now

- `v_android_sample_family_type_authority`
  - row count matches Android APK scope
  - authority bucket breakdown matches the SQL audit
  - raw-vs-authority status logic is understandable and stable
- `family_type_authority_coverage_latest.md`
  - missing-family candidate queue looks plausible
  - unknown-type family queue matches curation expectations
  - temporal year/type concentration is visible

## What To Review Before Future Foundation Work

- `malware_family_authority_fact`
  - sample count
  - authority overrides vs catalog resolution
- `malware_family_alias_fact`
  - self-alias and canonical-name coverage
  - no bad mappings to inactive families
- `vendor_label_generic_token_fact`
  - starter token policy is intentionally conservative
  - add vendor-specific overrides only after audit
- `malware_family_label_evidence`
  - core vendor coverage
  - generic-label dominance
  - high-disagreement samples

## What Not To Do In This Phase

- do not rewrite current family labels
- do not treat AV evidence as ground truth
- do not exclude noise candidates from training yet
- do not merge ScytaleDroid lineage facts into Erebus without a separate review
