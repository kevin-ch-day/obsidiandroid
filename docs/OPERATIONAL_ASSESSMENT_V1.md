# Operational artifact assessment V1

V1 derives an exact-SHA assessment from existing source evidence. It supports bounded frozen-evidence assessment with SQLite and an explicitly
selected MariaDB adapter. It is not a model prediction or HTTP service. The canonical code is `obsidiandroid.assessment`; presentation lives in
`obsidiandroid.cli.assessment`. Migration 0006 is registered and validated in a disposable database; production activation has not occurred.

## Result contract

`contract_version = obsidiandroid.artifact-assessment.v1`. The full result contains:

| Member | Meaning |
| --- | --- |
| `assessment_id` | SHA-256 of artifact identity, canonical body digest, revision and predecessor |
| `revision`, `previous_assessment_id` | Per-artifact append-only chain, beginning at 1 |
| `assessed_at_utc` | First persistence time; unchanged on identical replay |
| `artifact` | Exact lowercase SHA-256 and independently supported platform, format, package and version |
| `assessment` | Separate artifact_label, type, family and variant fields |
| `evidence` | Erebus, Permission Intel and Scytale availability and source evidence references |
| `confidence` | Field support plus unmodified upstream AV policy quantities; no model probability |
| `provenance` | Engine, rule and code versions, source projection digests and keyed reference registry |
| `processing` | Status, reasons and unresolved assessment fields |

Each conclusion has `state`, `value`, `candidates`, `method`, `support`,
`evidence_refs`, and `reason`. Supported values require references. Unresolved and
conflicting fields have null values; conflict candidates remain visible. A
reference identifies source/table/key plus a digest of the frozen row projection.
The evidence snapshot retains those projections, not a new authoritative copy.
The local store validates this boundary before appending a revision.

Statuses: `complete`, `complete_with_unresolved_fields`,
`complete_with_conflict`, `insufficient_evidence`, `unsupported_artifact`, `error`.
They describe processing, not detection quality. `error` preserves source errors
and is not equivalent to absent evidence. `current` means latest attempt, even if
that attempt is an error; it does not mean latest successful or most certain.

## Evidence and rule policy

- **Identity:** a unique exact-SHA Erebus catalog row; Android/APK is the V1
  supported artifact scope. Package metadata is a source assertion, not an APK
  measurement. Exact Scytale registry version metadata can be included separately.
- **Artifact label:** Android identity supports `ANDROID_APPLICATION`, which is
  neutral about benignness. `ANDROID_MALWARE` additionally requires Erebus
  `vt_confidence_v1`, `high`, `promote`, positive malicious detections, and exact
  agreement with the current scan's date and detection counts. Coexisting effective
  false-positive review evidence retains a conflict. This is a source-policy rule,
  not independent maliciousness verification or a calibrated probability.
- **Family:** accepted mappings must have active canonical families. Active reviewed
  authority facts also require an active canonical dimension with consistent name
  and slug. Automated authority rows are retained but not promoted to reviewed
  assignments. Multiple canonical candidates or open family governance conflicts
  block selection. An accepted mapping alone is not ground truth.
- **Type:** existing active Erebus taxonomy only. Family taxonomy, reviewed type
  authority and exact catalog type assertions remain separately supported. Multiple
  distinct type IDs remain a conflict, including broader/narrower type pairs; V1
  does not adjudicate taxonomy hierarchy or silently choose a more specific type.
- **Variant:** unresolved; there is no governed sample-bound variant source in V1.
  Therefore even otherwise supported records have unresolved fields.
- **Permissions:** existing observations only; no downstream materialization.
  Exact token spelling, one accepted current release, accepted identity/source,
  available source, selected declaration and absence of unresolved declaration
  conflicts are required for semantic resolution. Reuses the existing
  `permission_current_interpretation` interpreter. Resolved count means current
  catalog interpretation, not complete historical/runtime applicability. Feature
  conditions and historical lifecycle remain visible. No observations means null
  counts, not measured zero permissions. Retained-report tokens missing downstream
  are a separate evidence-gap list and never become synthetic observations.
- **Scytale:** exact SHA only, preserving versioned install-set hashes where
  present. Run/registry availability does not certify run completion, static
  readiness, or measured runtime behavior. No package-name or family fuzzy joins.

## Application service and CLI

```python
from obsidiandroid.assessment import AssessmentService, AssessmentStore, FrozenEvidenceSource

service = AssessmentService(
    FrozenEvidenceSource.load("pilot_evidence.json"),
    AssessmentStore("assessments.sqlite"),
)
record = service.assess(sha256)
assert service.current(sha256) == record
history = service.history(sha256)
```

`python -m obsidiandroid.cli.assessment --help` describes the CLI. An updated
editable install provides `obsidiandroid-assess`. `--json` serializes exactly the
service result. Current/history do not need a source snapshot. Exit codes: 0 means
record(s) returned (inspect `processing.status` for assessment outcome), 2 means
invalid/unavailable input or sidecar error, 3 means no stored assessment. `--help`
requires neither snapshot, credentials, nor database access.

The frozen bundle contract is `obsidiandroid.assessment-evidence.v1`, with an
`artifacts` object keyed by lowercase SHA and `content_sha256` over canonicalized
artifact slices. Snapshot absence is `not_in_snapshot`; a completed source lookup
with no row is `not_found`. Checksums detect accidental change; they do not
authenticate an untrusted bundle. The caller must trust the extraction provenance.

`ReadOnlyEvidenceReader` accepts an existing read-only DictCursor connection and
requires `@@tx_read_only=1`. Its fixed SELECT queries target the current same-server
Erebus, Permission Intel and Scytale deployment; connection setup is intentionally
not part of the CLI. The audit collector starts a server-enforced read-only
consistent snapshot, applies a statement timeout and always rolls back/closes.
Multi-server extraction and general deployment configuration are future work.
No database or network call occurs in composition or local retrieval.

## Revision model

Identical current canonical bodies return the same ID, timestamp and JSON.
Evidence changes, rule versions or code fingerprints append a new revision.
Returning to an older evidence state creates a new revision rather than reviving
an earlier current pointer. Source row ordering does not affect canonical hashes.
By default the code fingerprint includes assessment modules and the reused
permission interpreter; explicit reviewed fingerprints can be supplied.

The local SQLite schema in `assessment/store.py` enforces unique IDs, unique
(artifact, revision), same-artifact predecessor foreign keys, one successor per
predecessor, contiguous chain extension, JSON identity agreement, and immutable
rows. `BEGIN IMMEDIATE` serializes concurrent local appends. The current record is
maximum revision using `(artifact_sha256, revision DESC)`; superseded status is
derived, never an update to historical payloads. Timestamps do not participate in
idempotency. Independent stores can record different first-persistence times;
byte-for-byte replay is guaranteed within a store, not across unrelated stores.

## MariaDB persistence

Migration `0006_operational_assessment_v1.sql` adds only:

- `core_assessment_artifact`: one exact-SHA row used to serialize writers.
- `core_assessment_revision`: immutable revisions, complete V1 JSON including
  fields/provenance, generated family/type/status query projections.
- `v_core_assessment_current`: latest revision per artifact, including errors.

The three triggers enforce immutable revisions and contiguous extension. Local
foreign keys enforce same-SHA predecessors and artifact ownership. There are no
cross-catalog foreign keys or experiment-table dependencies. JSON identity checks
bind ID/SHA/revision/predecessor/time to columns. The application validates the
full V1 field/provenance contract before writing; the database is not a duplicate
implementation of the evidence interpreter. Restricted application credentials
must not be exposed directly to untrusted clients.

The adapter opens a dedicated connection per operation, verifies `DATABASE()`,
uses READ COMMITTED, and acquires the artifact lock with a no-op upsert followed
by SELECT FOR UPDATE. Under that lock it compares the complete canonical body
hash with the latest revision, either reusing it or inserting the next revision.
All field results and provenance are in the same INSERT; there is no separately
committed field/provenance stage. Current is derived, so no mutable pointer can
lag a commit. Failed operations roll back artifact creation and revision insertion.
Known deadlock/lock-timeout errors (1213/1205) retry the whole transaction, at most
three retries by default. Other errors, including unknown commit outcomes, are
surfaced; inspect current/history before replaying. Historical payloads never change.

The runtime account needs SELECT/INSERT on both tables, UPDATE on only the
artifact SHA column for the no-op lock upsert, and SELECT on the current view.
It receives no revision UPDATE/DELETE, DDL, or upstream grants. Migration uses a
separate explicitly selected connection. Defaults reject production; the explicit
`--allow-production` flag is for separately authorized activation only.

```bash
PYTHONPATH=src python -m obsidiandroid.cli.assessment current SHA256 \
  --database obsidiandroid_core_persistence_test_20260919 \
  --db-option-file /private/service.cnf --json
# Use history or assess; assess additionally requires --snapshot frozen.json.
PYTHONPATH=src python -m obsidiandroid.assessment.migration \
  --database obsidiandroid_core_persistence_test_20260919 \
  --option-file /private/migrator.cnf --receipt /new/receipt.json
# Migration defaults to dry-run; --apply is explicit.
```

The migration wrapper verifies foundation ledger checksums 0001–0003, applies
only 0006 through the existing Core executor, and verifies the reviewed structural schema contract.
It does not implicitly apply the unrelated 0004/0005 experiment migrations.
Existing migrations remain unchanged. Reruns verify the ledger checksum and
the full assessment schema structure. MariaDB DDL can commit partially: a failed migration
requires schema inspection and reconciliation, not blind retry or a claim of
transactional DDL rollback. There is no destructive down migration: disable the
writer and retain history when rolling back application activation.

The service accepts either storage adapter. `MariaDBAssessmentStore.by_id()` also
supports direct immutable-ID retrieval. Family/type/status indexes support
revision searches; SHA/revision and ID keys support current/history/detail reads.
Current-family searches can use the view, but historical revisions matching a
family must not be confused with current family counts.

The disposable acceptance packet is
`/home/systemadmin/Documents/ObsidianDroid_Audits/OBSIDIAN_ASSESSMENT_PERSISTENCE_V1_20260919/`.
Live tests require explicit `OBSIDIAN_ASSESSMENT_TEST_OPTION_FILE` and optionally
`OBSIDIAN_ASSESSMENT_TEST_ADMIN_OPTION_FILE`; they never default to production.
Synthetic rows and the database are retained for inspection. The 28 frozen pilot
conclusions match V1. Independent stores have different revision metadata; the
expanded source fingerprint also changes code provenance without changing rules.

## Pilot evidence

The September 19 pilot and all 16 requested audit documents are preserved under
`/home/systemadmin/Documents/ObsidianDroid_Audits/OBSIDIAN_OPERATIONAL_ASSESSMENT_V1_20260919/`.
The 28 samples cover seven each of unique accepted mapping, no accepted mapping,
multiple accepted mappings and retained permission materialization gaps. It is an
operational contract exercise, not a representative accuracy benchmark.

## Review and read-only health checks

Both storage adapters now expose `by_id(assessment_id)` and
`history_page(sha256, limit=50, after_revision=0)`. Pages contain unchanged V1
`records`, `artifact_sha256` and `next_after_revision`. Limits are 1–200 and use
revision cursors, avoiding increasingly expensive SQL offsets. New commits can
appear on later pages; a page sequence is not a frozen export. Existing `history`
without `--limit` retains its full-list response for compatibility.

```bash
PYTHONPATH=src python -m obsidiandroid.cli.assessment history SHA256 \
  --store assessments.sqlite --limit 25 --after-revision 0 --json
PYTHONPATH=src python -m obsidiandroid.cli.assessment by-id ASSESSMENT_ID \
  --store assessments.sqlite --json
PYTHONPATH=src python -m obsidiandroid.cli.assessment compare BEFORE_ID \
  --against AFTER_ID --store assessments.sqlite --json
```

The MariaDB backend uses the same commands with `--database`/`--db-option-file`.
Comparison is restricted to one exact artifact and uses JSON Pointer paths.
`conclusions_changed` tracks field states, values and candidates; evidence,
field support, processing, confidence, code/rules and persistence metadata remain
separate change categories. Missing values are distinguished from explicit null.
Comparison explains differences; it does not infer which revision is more correct.
SQLite retrieval uses URI read-only mode, without creating files or schema.
MariaDB retrieval explicitly enables a read-only session. Invalid identities/page
bounds are rejected before opening a database connection.

The read-only doctor is available as `obsidiandroid-assess-doctor` after installing
this source, or directly:

```bash
PYTHONPATH=src python -m obsidiandroid.assessment.doctor \
  --database obsidiandroid_core_persistence_test_20260920 \
  --option-file /private/auditor.cnf --sha256 SHA256 --max-revisions 100 --json
```

The doctor checks the assessment schema and 0006 ledger, then optionally validates
up to 200 revisions for one artifact: column/JSON identity, input and assessment
hashes, field provenance contract, chain continuity, artifact ownership and current
selection. A bounded prefix is explicitly `partial`, never a full integrity claim.
Exit codes: 0=ready for the stated scope; 2=failed/unavailable; 3=partial check.
Without SHA it is schema-only, not an all-artifact scan. Unknown SHA is explicitly
`not_assessed`. It uses a server-enforced read-only consistent snapshot and a
five-second statement timeout. Use an auditor/migrator connection with metadata
visibility and SELECT on the ledger; the minimal runtime writer intentionally
cannot see all these objects. Missing visibility does not prove missing schema.
It does not certify upstream truth, governance readiness, or detection accuracy.

Structural validation compares table/view kinds, engines, columns, generated
expressions, index columns/uniqueness, FK targets/rules, CHECK expressions, trigger
bodies/timing and view definitions/security. `schema_contract_v1.json` is a
reviewed package asset bound to the unchanged SQL 0006 checksum; never regenerate
it automatically from a possibly drifted deployment. Own-schema qualification
and the status column's intentionally inherited default collation are normalized.
SHA/JSON collations and case-sensitive table identities remain exact. Metadata
representation is validated on MariaDB 11.8.8; another server version can require
reviewed normalization changes rather than weakening the checks. This pass also
rehearsed production's `utf8mb4_uca1400_ai_ci` default in a separate disposable
schema; production itself was not migrated.

Migration preflight now checks repository checksums before connecting and refuses
to overwrite a receipt even through the Python API. Post-DDL validation failure
sets receipt status `validation_failed` while retaining applied-version facts.
Connector errors at command boundaries omit credential details. Rollback/close
errors no longer hide the original error or make an acknowledged commit appear
failed; sanitized cleanup warnings remain visible.

Disposable test names may have an alphanumeric run suffix, such as
`obsidiandroid_core_persistence_test_20260920_collation`. Live test fixtures validate
the target before any connection, including privileged schema-drift exercises.
Production remains a separately authorized activation. See the preserved hardening
packet under `ObsidianDroid_Audits/OBSIDIAN_HIGH_ROI_HARDENING_20260919/`.

### Schema doctor account and visibility

Use the existing metadata-capable auditor with the doctor's server-enforced
read-only transaction. Keep the runtime writer and migration/trigger-definer
roles separate. A partial result (exit 3) means inspection was incomplete, not
that missing metadata proves a physical schema defect. Confirmed differences
remain failures (exit 2); complete verification returns ready (exit 0).

On MariaDB 11.8.8, schema-level SELECT exposes CHECK_CONSTRAINTS, while a
restricted table-level SELECT grant does not. REFERENTIAL_CONSTRAINTS also needs
a non-SELECT table privilege, and trigger metadata requires TRIGGER. Consequently
a data-read-only account with SELECT alone cannot inspect the complete contract.
Do not grant schema modification rights to the runtime account for this purpose.
The doctor checks SHOW CREATE evidence to distinguish hidden CHECK/FK metadata
from demonstrably missing or altered definitions; strict migration validation
still requires complete metadata and never accepts a partial inspection.


## Read-only assessment explanations

`explain` retrieves the current immutable assessment and projects evidence gaps;
it does not compose, append, refresh sources, contact providers, or alter labels.

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.cli.assessment explain SHA256 \
  --database obsidiandroid_core_prod --allow-production \
  --db-option-file "$HOME/.config/obsidiandroid/assessment-writer.cnf" --json
```

The JSON envelope identifies the exact assessment ID/revision, processing status,
and separate catalog, family/type/variant, retained-permission projection, and
permission-semantic gaps. Scope is the stored assessment: it does not establish
current upstream state or independently validate APKs. `unsupported_artifact`
can reflect platform/format catalog evidence that does not meet V1's Android/APK
requirements; it is not itself proof of invalid bytes. Existing `current` JSON
and assessment V1 bodies remain unchanged. Plain-text unsupported results now
show the catalog platform/format and point to `explain`.

Expected input/storage failures return exit2. With `--json`, stderr contains
`status`, `error_type`, and numeric `errno` when available. Arbitrary exception
messages, including option-file lines or credential values, are not echoed.
Exit3 still means no stored assessment. No connection occurs for `--help`.
