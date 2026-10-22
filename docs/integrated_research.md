# Integrated Android research

The read-only explorer includes **Integrated research — retained evidence**.
Choose an explicitly generated research packet directory, or set
`OBSIDIANDROID_RESEARCH_PACKET` in the launching environment. The browser never
opens a database connection or activates a model. Its snapshot is separate from
the live catalog explorer.

For complete machine-readable results from the same views:

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /absolute/path/to/integrated-packet overview
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /absolute/path/to/integrated-packet sample 123
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /absolute/path/to/integrated-packet family 'Dark Herring'
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /absolute/path/to/integrated-packet type banker
```

Packets contain checksum-bound `SAMPLES.csv`, `PERMISSIONS.csv` and a
`RESEARCH_MANIFEST.json` with format `obsidiandroid-integrated-research-v1`.
The manifest indexes original, checksum-verified retained vendor shards: keep
those paths available for sample-level raw claims. No pickle/model is loaded.
Checksums detect byte drift; they do not independently establish source authority.
The current builder recipe is retained in the generated audit packet; a generic
live refresh/export command has not yet been added to the application.

The separate `obsidiandroid.governance.permission_consumer_conformance` module
tests a proposed evidence consumer offline. Its audit-harness binding pins packet,
sample identities, immutable history, dictionary/classifier versions and reader
code. It verifies retained report bytes and exact token correspondence, preserving
governed concepts separately from accepted catalog identity. Missing source bytes,
projection-only correspondence, unknown protection and unresolved evidence produce
explicit abstentions; corrupt or contradictory evidence fails validation.

This prototype accepts only `OFFLINE_CONFORMANCE_ONLY` fixtures and descriptive
operation names. Its binding is not the installed consumer approval anchor. It
does not activate access, provide training features, query a database, or load a
model. Ordinary retained analysis uses local packet validation without this fixture
admission layer. Even a byte-verified latest report is not proof of an
original historical event, APK manifest declaration, granted access or behavior.

The overview, sample, family and type views also show a permission coverage
matrix. Old packets report upstream dimensions as `NOT_INSPECTED`, with unknown
counts. An explicitly built packet can include checksum-bound `PI_COVERAGE.csv`
and `permission_coverage_audit` metadata (format
`obsidiandroid-pi-coverage-audit-v1`, purpose
`AUDIT_ONLY_NOT_CONSUMER_AUTHORITY`). The CSV must cover exactly the packet's
sample ID/SHA-256 population. Each dimension records its source, snapshot time
and access state. `INACCESSIBLE` and `NOT_INSPECTED` require blank counts;
`OBSERVED` requires nonnegative integer counts. Zero then means no rows in that
inspected surface, never proof that the APK uses no permissions.

This optional audit distinguishes retained observations, exact accepted catalog
identity, current operational classification, stored recovery stamps, exact V2
source members and observations labeled `apk_manifest`. A source label alone
does not verify a manifest. Audit counts do not supply permission tokens,
change approved-export membership, authorize training, or unlock database reads.
Source snapshots may differ in time and are shown separately.

Optional classification audit dimensions distinguish explicit protection bases,
scoped permission authority, source-asserted, pattern-only, provisional, unresolved,
and governed non-permission interpretations. Separate counters identify governed
concepts omitted by the coarse classifier and stored-versus-token-only replay
differences. A replay difference is not a correction: recovery may have transferred
authority from exact raw evidence under a separately recorded projection policy.
Each supplied dimension requires its own provenance and bounded observation count.
Older packets retain unknown counts for dimensions they did not inspect.

Every view also explains consumer availability: frozen export members, excluded
identities with upstream observations, and excluded identities with no rows in the
inspected surface. The browser does not recheck current approval. Canonical identity,
classification coverage, and audit access cannot authorize an expanded consumer;
that requires a separately approved identity-bound descriptive contract. Training
requires separate authorization. These diagnostics never add permission features
to the approved export.

Sample views retain original vendor strings and parser interpretations separately
from recorded/governed family fields. The type is a primary family-taxonomy mapping,
not a behavioral inference. Family/type views keep unknown labels visible, report
sources and authority, and give covered permission denominators explicitly.

Permission descriptive access is verified through the existing PI V2 interface
when the packet is built. The frozen result does not establish current approval or
training authority. Raw and projected tokens remain separate. Missing PI coverage
is `UNAVAILABLE`, not absence. Category/capability fields remain unavailable because
the current unresolved export carries no governed definitions; names alone must
not become Android protection levels or observed behavior.

Temporal reports use retained VirusTotal `first_submission_date`, with no fallback
to effective/first-seen/ingestion dates. Missing/invalid timestamps and first-submission
after last-analysis anomalies are excluded from temporal denominators but remain
visible in the sample population. The proxy describes submitted cohorts, not malware
creation, emergence, population prevalence or demonstrated family evolution.

Console tables use navigable 20-row pages. Use the CLI or exported
CSVs for complete machine-readable results. Human timestamp display uses the existing America/Chicago
CST/CDT plus UTC formatter; JSON/CSV retains exact UTC timestamps.

### Retained descriptive Permission Intelligence tables

`obsidiandroid.reporting.permission_descriptive_research.describe_permissions`
accepts previously validated, hash-verified offline consumer rows and exact
sample ID/SHA/family metadata. It reports family coverage, sample-based canonical
identity prevalence and calendar-year first-submission cells. Source-unverified
observations are excluded from canonical comparisons; repeated observations do
not inflate sample prevalence. Missing or invalid temporal evidence cannot be
silently counted as a dated observation. Capability labels remain candidates,
and source protection assertions do not establish runtime behavior.

The descriptive function does not activate a database reader or authorize model
training. Its caller must verify frozen artifact hashes; it is not a replacement
for the evidence consumer's admission checks.

### Family-signature sensitivity and retained PI views

An explicitly selected packet containing `PI_VIEW_MANIFEST.json` can now be
opened through the existing Integrated research menu or its research CLI. The
local view checks file hashes, sample/source identities, frozen versions and
exact denominators. It shows accepted sample frequencies, authority/protection,
unresolved observations, vendor-family relationships and temporal distributions.
Lineage summaries average inferred components and retain sample counts; bootstrap
ranges are exploratory sensitivity, not population confidence intervals. Missing
source batches remain unknown. Permission presence does not establish behavior.

### Permission lookup, pooled comparisons and exact AV companions

For a retained PI view, the existing console now offers **Permission identity
across families** and **AV and permission evidence comparison**. Tables have
20-row pages: `n` advances, `p` goes back, and Enter continues to the next section.
Sample evidence includes exact tokens, source/history bindings, frozen versions,
protection assertions and abstentions. Candidate capability labels are explicitly
unapproved; they are never promoted into governed definitions or model features.

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /absolute/path/to/research-view permission android.permission.READ_SMS
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /absolute/path/to/research-view comparison
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /absolute/path/to/research-view \
  --av-packet /absolute/path/to/integrated-packet sample 3
```

Permission comparisons include zero-positive families against the full selected
cohort denominator; projection-only observations never count as accepted positives.
Pooled type frequencies count distinct samples, not averages of family percentages.
Common permissions, represented families and inferred-component support remain
selected-cohort descriptions, not universal signatures or independent replication.
Missing source, lineage, AV state and temporal coverage are visible separately.

An optional `OBSIDIANDROID_RESEARCH_AV_PACKET` selects the console's AV companion.
All PI cohort identities must match the companion by sample ID, SHA-256, retained
report event and payload hash. A mismatch rejects the attachment. Vendor shards
are checksum-verified on demand. Both snapshot paths and manifest hashes are shown;
family labels, permission membership and classifications are not merged or replaced.
Without a companion, retained AV summary evidence remains available and no raw
vendor claims are invented. Catalog overview continues to use its explicit catalog
packet, separately from the 1,212-sample PI research view.

The comparison view reports evidence availability, not training eligibility.
A future AV-only / PI-only / fused comparison needs a separately authorized,
ID/SHA-bound common cohort with accepted source-exact PI, independently justified
labels, acquisition-source and lineage isolation, and a genuinely untouched final
evaluation population. Existing inspected folds are development evidence only.
Freeze target, taxonomy, label universe, dictionary/classifier and split identities
before fitting; build vocabularies and select features inside training partitions
only. Use the same partitions for all modalities, report fixed-label macro-F1 and
per-family independent-group support, and disclose vendor-label circularity and
first-submission proxy limitations. No PI-enabled fit is exposed by these views.

### Separate disposable process-provider tests

This SQLite test harness is not required to export or browse a local research
packet. Its fixture authentication, expiry and revocation exercise a possible
persistent transport; they impose no signing or custodian requirement on offline
descriptive work.

`governance.disposable_consumer` implements a separate provider process reached
through an inherited JSON pipe. `provision(new_tmp_directory, validated_view)`
creates a private, disposable SQLite source and control store. It cannot target
an existing directory or a path outside `/tmp`; it creates no production accounts
or grants. Owner provisioning pins the exact retained cohort, fields, row hashes,
versions and query template in an HMAC-authenticated fixture contract. Requests
cannot supply SQL, source paths, resource policy or a production mode.

The provider opens the source with SQLite `mode=ro` and `query_only`, establishes
a read transaction before pagination, and uses a fixed indexed primary-key query.
Actual EXPLAIN output must show the expected primary-key search. An SQLite VM
progress handler interrupts execution on the provider's statement deadline;
SQLite lock waits are also bounded. This verifies SQLite mechanics, not MariaDB
query plans, distributed cancellation or kernel-level I/O termination.

Authenticated, sequential keyset cursors bind job, snapshot and continuation
position. Pages are staged: the adapter exposes nothing until the entire ordered
snapshot matches, publication is audited, and current authority is checked.
Row/encoded-row-byte budgets and the single active-job lease are transactionally
shared across independent processes through the control database. Budgets are
cumulative and are not refunded on uncertain interruption. JSON framing and
process RSS are not included in the encoded-row-byte budget.

Audit verification refuses ledgers at 10,000 records; terminal pagination cannot
be polled repeatedly. Audit records use a durable SQLite transaction (`synchronous=FULL`), sequence,
previous-record hash and a service-held HMAC key. Budget updates and page/publication
audit records commit atomically. Forged records, missing/truncated chains and audit
unavailability fail closed. Same-UID filesystem access is trusted in this fixture:
this fixture does not establish an independent public signature or operational
production boundary.

`reporting.disposable_research.DisposableResearchAdapter` consumes the provider's
complete response, checks the view snapshot and reuses `PermissionResearchView`.
Pass it explicitly to `launch_integrated_research(consumer=adapter)` for a disposable
integration demonstration. Results are labeled `DISPOSABLE_INTEGRATION_ONLY` and
never production-authorized. Normal console startup continues to use retained
packets. There is no environment switch to activate a production provider.

Authority generation changes/revocation invalidate active jobs and publications.
Expiration and job deadlines are checked before pages, publication and subsequent
view access. `adapter.rollback()` invalidates publication while preserving source
and audit history. A killed worker leaves a conservative lease; owner `recover()`
expires only elapsed active jobs and records recovery without refunding use.
Previously copied bytes cannot be recalled. These controls belong to the disposable
provider tests, not to local retained-packet analysis.

| Failure | Disposition |
| --- | --- |
| Unknown/malformed identity, extra field, SQL or mode override | Deny admission; no publication; durable DENIED receipt if audit is available. |
| Source/hash/version/interpretation/classification mismatch | Abort job, preserve source; no result. |
| Frozen unknown historical classifier or original event | Preserve explicit null/abstention; do not manufacture a version or original-event authority. Mutating that history fails the row pin. |
| Projection-only evidence | Preserve abstention; never promote into accepted source-exact evidence. |
| Expiry, revocation or generation change | Reject page/publication/access; invalidate dependent publications on owner transition. |
| Tampered/replayed cursor | Abort; no cursor fallback or offset pagination. |
| Nonindexed query plan or SQLite execution timeout | Abort transaction; no weaker query or timeout retry. |
| Row/byte budget or active-job exhaustion | Deny; do not return zero evidence or silently shrink the population. |
| Missing/forged/truncated/unavailable audit | No page or valid result released by that request; recovery needs trusted audit service restoration or a new fixture. |
| Process interruption | Explicit transport-unavailable error; partial rows remain unpublished; expire orphan lease conservatively. |
| Incomplete publication or rollback | Reject/invalidate derived output; original evidence stays immutable. |

### Capability source-version review

`governance.capability_review.review_definition` checks pinned manifest bytes,
commit, release, URL, exact permission identity, complete XML attributes and the
retained definition receipt. A release mismatch yields
`ABSTAIN_VERSION_MISMATCH`; even a match yields review-only, never activation.
The retained Android 15 READ_SMS and USE_FULL_SCREEN_INTENT examples validate
against their actual XML and both abstain against the frozen Android 17 catalog.
No mapping or platform-behavior claims are inferred from token names.

To reconcile them, the source owner must supply an authenticated mapping from the
exact dictionary release/digest to its immutable platform source commit/build;
the matching defining manifest entries, protection modifiers/flags and referenced
descriptions; API, grant/AppOps and target-SDK applicability sources for the proposed
capability wording; conflict resolution and owner review identity; and sample
applicability evidence where claimed. SDK public-surface definitions alone may not
supply runtime grant/applicability rules. Existing Android 15 evidence remains
historical, rather than being relabeled Android 17. OEM/custom definitions require
the corresponding defining package/firmware provenance.

### Malware Classification and Permission Intelligence Research Atlas

The same research console and JSON CLI accept a directory containing
`ATLAS_MANIFEST.json` (`obsidiandroid-research-atlas-v1`). It references and pins
an existing catalog `RESEARCH_MANIFEST.json` and a separate authorized
`PI_VIEW_MANIFEST.json`; optional raw-source and historical coverage-audit
companions are independently hash-bound. It does not copy evidence or open a
live database. The PI companion must match every sample ID, SHA, selected report
event and payload hash in the catalog companion.

Use the existing Integrated research menu with the atlas packet path. Engine,
family, type, sample, permission, comparison, overlap and separate prior-export
views retain distinct denominators. JSON queries use the existing CLI, for example
`python -m obsidiandroid.reporting.integrated_research --packet <atlas> engine Kaspersky`.
The first AV query verifies all vendor shards and builds an in-memory index;
subsequent navigation reuses those validated bytes. Unknown engines/families return
explicit zero eligible coverage, while absent PI remains unavailable. Sample views
can verify raw source payloads and expose engine versions/update dates when present.
Catalog aggregates use the frozen parser projection, not newly reparsed labels.

Engine names remain raw. A lowercase/hyphen compatibility key aids lookup but does
not merge vendor aliases or assert engine independence. Every `(sample, raw engine)`
occurs once in the selected-report snapshot; repeated keys are rejected. Engine
missingness, undetected, timeout, failure and unsupported categories stay distinct.
The global engine universe is not a required scanner panel. Nonempty unrecognized
labels include generic labels and specific claims the parser cannot resolve.
Neither parser quality nor taxonomy agreement establishes detection accuracy.

PI comparisons preserve zero-positive families and distinguish pooled sample
frequencies from equal-family mean frequencies. In family and type views, each
family's PI numerator and denominator use only members of the selected view;
type lookups also apply the same case-insensitive scope to source-context counts.
Inferred lineage components and
VT first-submission periods remain descriptive dependence/time proxies. The
prior 1813-sample export remains an unresolved-evidence contract, separate from
the governed 1212-sample view. Historical upstream coverage counts never authorize
access or classify every excluded sample as an authorization failure. Candidate
capabilities and machine-learning training remain disabled.

### Atlas v1.1 vendor interpretation intelligence

An atlas manifest may additionally pin `vendor_interpretation` to the maintained
`vendors.interpretation_quality.source_identity()` contract. A mismatched policy
or source hash fails closed. Historical Atlas v1 manifests continue showing frozen
interpretations. The new view retains those columns and adds a separate explanation
layer; it never overwrites raw labels, catalog taxonomy or historical artifacts.

Engine, family, type and sample views now expose distinct label counts, before/after
recognition, newly conflicting samples, conservative generic outcomes, unresolved
specific-looking labels, ambiguity and taxonomy-review cases. The 100 most frequent
labels per scope include exact sample/SHA/event/payload exemplars, old/new claims
and rule reasons. Missing engine observations remain distinct from undetected.

The bounded Kaspersky correction admits an exact Android family-name slot through
the existing supported taxonomy when the parser's local allowlist omitted it.
Suffixes, substrings, other platforms and unapproved aliases are not promoted.
Kaspersky's published naming convention supplies the slot semantics; recognition
still describes a vendor claim, not independent sample attribution. BankBot remains
BankBot; KungFu is not mapped to DroidKungFu and Arsink is not mapped to ArsinkRAT.

Generic recognition is deliberately conservative. The remaining nonempty labels
are not all specific family claims or defects. Outcome C means specificity is
unverified; F means an unaccepted literal catalog-name token requires review.
Existing recognized claims retain their historical authority, including ambiguous
vendor nomenclature. Any comparison to canonical family requires separate review.

### Permission associations within AV groups

Version-pinned research atlases expose **Permission associations within AV groups**
through the existing research console, or the research CLI `association` operation
with an exact accepted canonical permission identity. The view partitions the
approved PI cohort into conflicting recognized claims, one recognized family,
detected without recognition, and no detected verdict. It compares observed
positive frequencies pooled, within families, within family/source batches and
within family/first-submission months. Both sides receive equal weight for each
shared stratum; included and excluded sample counts accompany every contrast.
Missing source/time cannot establish common support; an empty comparison is
`UNAVAILABLE`, not zero. Small strata remain visible and are not independent
replication. Exact identity/report references support existing sample drill-down.
Seven retained projection abstentions remain abstentions. Nonpositive observations
are not proof of permission absence, and declarations are not runtime behavior.
This exploratory view provides neither causal estimates nor training authority.
Each contrast also reports the smallest contributing cell and a `min5` sensitivity
result retaining only strata with at least five samples on each side. This is an
explicit exploratory screen, not a statistical sufficiency or independence rule.

### Family permission structure and temporal sensitivity

The existing atlas console and research CLI `structure` operation describe the
approved PI cohort over its full accepted canonical vocabulary. Base-2
Jensen–Shannon distance is the square root of divergence, ranges from zero to
one, and compares **normalized positive observation mass**, not permission
prevalence directly. Frequencies and exact denominators remain available beside
that normalization. Duplicate observations cannot multiply sample support;
projection-only evidence remains excluded from accepted positives.

The view compares sample weighting with equal inferred-component weighting,
reports leave-one-component distance ranges and known-batch omission results,
and exports annual frequencies plus adjacent observed-year distances. Missing
lineage is excluded from component-weighted profiles and counted explicitly.
Zero positive mass yields unavailable distance, including removal of a family's
only known source batch. Missing batch identifiers are never independent sources.
Annual records use eligible VirusTotal first-submission years, not malware
emergence dates; sparse years, gaps and cross-year shared components are visible.
The five-sample screen is descriptive, not a statistical sufficiency rule.

These are current-cohort exploratory results, not a reproduction of the papers'
figures or evidence of runtime behavior, lineage, convergence or causal change.
The operation fits no models and grants no access. It accepts at most 3,000
members, 100,000 observations, 2,048 accepted identities and 50 families, after
the existing manifest, source identity and classification-version validation.

### Local descriptive cohorts

Ordinary local descriptive work uses permitted source evidence, a bounded export,
exact sample/SHA/report validation and a retained packet. It does not require an
independent signer, approval-store service, custodian, arbitrary 24-hour expiry,
30-day retention rule or production deployment. Earlier audit-packet proposals
record historical designs; they do not govern this workflow. Existing database
privileges, external data-use obligations and the separate historical 1,813-sample
V2 contract remain unchanged. No source read is authorized by supplying a manifest.

`PermissionResearchView.export_subset(new_directory, identities)` converts a
validated retained view into a new exact-allowlist packet. Missing identities,
changed SHA/event/payload, duplicate members and existing destinations fail. Rows,
history, versions and unresolved evidence are preserved. Precomputed lineage
summaries are omitted for a subset; use the structure view to calculate them.
This exporter cannot manufacture evidence absent from its input.

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /path/to/retained-pi-view --identities /path/to/identities.csv \
  --write-subset /path/to/new-subset overview
```

An atlas may add `pi_cohorts` entries keyed by research cohort name. Each entry
contains `path` and `sha256` for its PI view manifest, plus `identities` containing
`path` and `sha256` for the complete sample/SHA/event/payload CSV. The existing `pi`
entry stays the `original` cohort. All views must bind exactly to the AV companion.
The console exposes cohort selection only when additional retained cohorts exist.

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /path/to/atlas --pi-cohort pilot_b comparison
PYTHONPATH=src .venv/bin/python -m obsidiandroid.reporting.integrated_research \
  --packet /path/to/atlas --pi-cohort combined structure
```

Combination rejects overlapping identities, duplicate observations and incompatible
classification/dictionary/interpretation versions. Source-index hashes may differ;
each cohort's exact versions and original row provenance remain visible. There is
no implicit combination or automatic evidence access. Descriptive tables permit
at most 1,312 members (the original 1,212 plus the requested 100); the existing
100,000-observation bound stays unchanged. Cohorts with incompatible interpretation
releases remain separately viewable until scientific compatibility is resolved.

Pilot B has no members in either the retained 1,212 view or the older
1,813 export. The earlier SQL audit does contain 1,857 grouped observations for
all 100 identities, but lacks observation IDs, historical rule/run/version and
per-observation interpretation bindings; these are partial audit evidence, not
a complete consumer packet. Erebus's governance snapshot exporter supplies dictionary rows, not
sample/report evidence; its exact-V2 exporter is fixed to the older cohort.
Preparing Pilot B therefore still needs a 100-identity, sample-bound projection
through the normal Erebus source reader, preserving raw-member
proof and original classification context. Do not enable the blocked ObsidianDroid
reader or substitute the dictionary snapshot for those observations. Missing new
tokens remain unresolved, without a recovery operation or provider request.

A metadata-only check on October 19, 2026 verified that the normal Erebus
`erebus_app@127.0.0.1` account has SELECT on both source schemas. The ObsidianDroid
reader remains restricted. No Pilot B source export was executed; the existing
Erebus path needs the bounded sample-evidence projection, not additional grants.
