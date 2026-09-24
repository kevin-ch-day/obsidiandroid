# Bounded pre-runtime assessment batches

`obsidiandroid.assessment_batch.BatchAssessmentService` reuses the Operational
Assessment V1 composer and immutable assessment store. The CLI is an adapter;
future API/UI consumers can use the same service without invoking a subprocess.
No provider requests, evidence acquisition, schema migrations or malware execution
occur in this service.

## Review and apply

From the repository with its virtual environment:

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.cli.assessment_batch --help
```

Supply `--manifest`, `--snapshot`, `--database`, `--db-option-file`, and a fresh
`--output` path. Dry run is the default; `--dry-run` is explicit. Production
access additionally requires `--allow-production`. For application, add
`--apply --plan reviewed-plan.json --expect-plan-digest EXACT_DIGEST` and use a
new output path. Never reuse a receipt filename.

The manifest (`obsidiandroid.batch-manifest.v1`) lists 1–250 unique canonical
SHA-256 values, UTC evidence cutoff, snapshot reference/digest, and optional
`pinned_revisions` mapping. Snapshot `obsidiandroid.batch-evidence.v1` contains
`entries` and their canonical content SHA-256. Each entry has `sha256`,
`evidence_cutoff_at`, normalized `engine_evidence`, and attributed `context`.
The reference implementation and validation contract are in
`src/obsidiandroid/assessment_batch/service.py`.

A reviewed plan binds normalized inputs and the V1 composer version. Apply
recomputes the plan, then checks the expected current revision under the existing
MariaDB artifact transaction lock. Identical evidence reuses the revision;
new evidence may justify an appended revision even if conclusions stay unchanged.
Changing only the cutoff or snapshot filename does not create a revision.

Transactions are per artifact, not batch-wide. On failure, processing stops and
remaining hashes receive explicit not-attempted outcomes. A flushed/fsynced JSONL
journal accompanies the exclusive receipt file. Inspect both and current/history
before recovery; never assume a lost client receipt means a transaction rolled
back. Batches must not be silently retried against changed evidence.

## Scientific interpretation and frozen history

Source signatures, catalog labels and static context do not become governed
family/type assignments automatically. Fields remain independent. V1's literal
field states are supported/conflict/unresolved; insufficient evidence is a batch
evaluation outcome, including unsupported artifact identity, not a newly invented
field taxonomy. Static validity does not prove malware family or runtime behavior.

New records preserve the evidence cutoff and snapshot/static references in
`provenance.batch_context`. Pinned historical records remain byte-for-byte intact;
the frozen cohort mapping records their original snapshot cutoff separately.
Do not stamp a new cutoff onto an old revision. Preserve per-revision cutoff basis.

Existing assessment current/history/by-ID API responses return full provenance.
The stored-record `explain` diagnostic also exposes cutoff, snapshot reference and
static baseline reference. Legacy records without batch metadata return null;
consult the frozen sidecar mapping instead of inventing a date. No new HTTP service
is deployed by this workflow.

`assessment_batch.analysis.summarize` produces descriptive availability and
agreement metrics with explicit denominators. Provider/vendor lineages are not
proven independent. Unparsed AV labels are not parsed ad hoc; zero comparable
source-family pairs means the source disagreement rate is not estimable.
Missing observations do not prove absence of permissions. Availability comparisons
are not evidence-ablation experiments and do not establish causation.

## Verify and inspect a frozen cohort offline

Use `FrozenCohort` from `obsidiandroid.assessment_batch.cohort` for shared
read-only inspection. The caller must supply an independently retained checksum
manifest SHA-256. The CLI defaults to verification and summary:

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.cli.assessment_cohort \
  --packet /path/to/frozen/cohort \
  --expect-checksums-sha256 EXPECTED_64_HEX_DIGEST
```

Add `--sha256 SAMPLE_SHA256` to retrieve a frozen assessment, its evidence
context and the cutoff's provenance. Add `--followups` instead to emit exact-hash
review items with baseline hashes and missing declared permission tokens. JSON
is written to stdout; use a new output location outside the sealed packet.

The inspector verifies every sealed file, immutable assessment IDs, revision
mappings, canonical evidence digests, cohort membership, and pinned pilot cutoff
mappings. It rejects corrupted inputs, duplicate identities, escaping paths and
symlinks. Verified input bytes are retained for consistent inspection.

Legacy pilot cutoff timestamps remain explicitly attributed to their original
frozen-snapshot capture upper bound. They are not presented as fields that were
stored in the old revision. New revisions retain their stored cutoff provenance.

The summary distinguishes verified local packet contents from external baseline
references and live database state, neither of which this command checks. A
successful result does not authorize mutation, acquisition or runtime execution.
Follow-ups are review inputs, not SQL repair plans. Incompatible static results
are not promoted to runtime candidates.

## Build environment

`./setup.sh` now installs the build requirements declared in `pyproject.toml`,
in addition to runtime requirements. CI uses the same helper. Existing virtual
environments can be repaired with:

```bash
.venv/bin/python scripts/dev/install_build_requirements.py
```

This is needed by the wheel contract test, which deliberately uses
`--no-build-isolation`. It does not change the runtime dependency declarations.

## Static declaration evidence

A pre-runtime batch may bind an immutable source-aware static declaration ledger
under `context.static_baseline.static_declaration_projection` with its reference,
file SHA-256 and occurrence/semantic summary. The stored batch context preserves
that reference. `assessment explain` displays the summary separately from legacy
provider observations; it does not rewrite the V1 engine evidence or promote
permission/family/type authority. Historical revisions retain their original
payloads and cutoffs. Reuse the same normalized context to avoid meaningless
revisions from a changed collection time alone.
