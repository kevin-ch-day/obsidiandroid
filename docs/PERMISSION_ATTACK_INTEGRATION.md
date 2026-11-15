# Permission evidence and ATT&CK Mobile relationships

ObsidianDroid owns analytical ATT&CK assessments. Android Permission Intelligence
(PI) owns source permission identities and occurrences; see
`docs/permission_intel_v1_shadow_pilot.md` and PI's `docs/CONSUMER_OWNERSHIP.md`.
This integration changes neither shared PI schema nor permission feature inputs.

## Versioned reference and migration

The existing mapping path and public loader/report builder remain active.
`config/taxonomy/mobile_attack_permission_mapping.yaml` now uses
`permission-attack-relationships-v2`; the exact old bootstrap is retained in
`config/taxonomy/mobile_attack_permission_mapping.bootstrap-v1.yaml` for audit,
not accepted as an active v2 configuration. Rules are source-checked development
assessments, not independent human review or production deployment approval.

The official MITRE Mobile ATT&CK v20.1 artifact is retained at
`config/taxonomy/mitre/mobile-attack-v20.1.json`, SHA-256
`632e2ec40848394f9873a7a3485fc32f92b861a4e7271f7e88e0cb02f11bb6af`,
commit `f59b03ecf828579d5f9e93683ce25b7e2e5fd9d7`.
The offline loader verifies bytes, active Android techniques, source-object
identity/version/modified timestamp, and exact supported tactics. It never
substitutes a newer release or downloads a missing artifact.

## Independent evidence dimensions

`PermissionObservation` binds exact sample ID/SHA-256 and raw case-sensitive
token to source kind/version, event/payload identity, source snapshot digest,
role, timestamps and timestamp meaning, extraction time and provenance.
Snapshot identity is not an observation timestamp or payload/event identity.
Provider-only exports retain UNKNOWN roles. Runtime grants are not API execution.
Identity is an independently established `PermissionIdentity`; a lowercased
legacy prevalence token never establishes a canonical identity.

A disposition is CAPABILITY_RELATED, CONTEXT_REQUIRED, NO_DIRECT_MAPPING,
UNRESOLVED, NOT_VALID_PERMISSION or PENDING_REVIEW. Missing dictionary membership
is unresolved; a known unreviewed identity is pending. NO_DIRECT_MAPPING requires
an explicit assessment (currently generic INTERNET); it is not absence of
malicious behavior. Conflicting declarations stay unresolved. Relationships are
many-to-many. T1453 uses Collection and Credential Access;
BIND_ACCESSIBILITY_SERVICE is a component guard, not a user-requested grant.

Interpretation distinguishes potential capability, supporting static indicator,
supporting runtime observation and insufficient evidence. Corroborated behavior
requires future independent evidence adjudication; this phase never emits an
observed technique. Every rule preserves unmet behavior prerequisites and API
minimum checks; minimum compatibility does not attest grants, target-SDK policy,
API maxima, hardware, service enablement or actual execution.

## Existing aggregate reports

The legacy family/type prevalence builder remains a descriptive report.
`confidence` remains a compatibility column with null values and an explicit
deprecation status. Pattern scores/levels/confidence describe upstream permission
prevalence only; they are not attack confidence. `pattern_basis` now explicitly
says PERMISSION_CAPABILITY_HYPOTHESIS rather than BEHAVIOR. `tactic` contains
semicolon-separated official tactics; `tactics` preserves the list. Group
prevalence does not establish same-sample co-occurrence, requested roles, or
runtime behavior. Outputs explicitly forbid family-model feature use.

## Offline development projection

Run with the project virtualenv and an independently retained producer SHA-256:

```bash
.venv/bin/python scripts/diagnostics/project_permission_attack.py \
  --catalog /absolute/path/to/owner-normalized.json \
  --catalog-sha256 ACTUAL_RETAINED_OWNER_ARTIFACT_SHA256 \
  --output /absolute/path/to/new-output-directory
```

An optional `--approved-export /absolute/path/to/export.json` uses the existing
root-approved PI V2 consumer validation and adds source-aware sample reporting.
It never creates a new approval or feature frame. Missing export membership is
unknown, not a verified negative. The output directory must not exist.

The command produces a complete CSV disposition for the supplied retained
catalog, a fresh local SQLite analytical overlay, a reconstruction receipt, and
optional sample relationship CSV. SQLite constrains references, disposition
values and behavioral assertions. Its schema is a development proposal only;
no MySQL connection, migration, deployment or training is performed. A retained
snapshot does not attest full current live PI/OEM/Google/app-defined coverage.

## Validation and limits

Run `make ci` plus explicitly selected slow permission-report tests and
`tests/test_mobile_attack_integration.py`. Offline tests use synthetic evidence
and retained official bytes. Test cases cover all original techniques,
role confusion, API minima, duplicates, contradictions, obsolete objects,
source tampering, frozen output semantics and deterministic SQLite regeneration.
No independent human review, production schema activation, model training,
family-label adjudication or challenge-cohort expansion follows from passing.

## Current-state reconciliation and bounded v3 review

Mapping `20261113-v3` adds seven source-checked rules and extends the existing
location rule from a predeclared 40-identity tranche. Nineteen reviewed generic
permissions receive explicit NO_DIRECT_MAPPING assessments; eight remain held
for further applicability/semantic evidence. A privileged declaration conflict
remains unresolved. No direct assessment is an absence-of-behavior observation.
Read-external-storage evidence at API 33+ requires target-SDK/storage-context
review; minimum API compatibility alone no longer implies useful access there.

The existing projection command now also writes `PI_CATALOG_RECONCILIATION.csv`.
Without an authorized current owner export, each retained identity is marked
CURRENT_EVIDENCE_UNAVAILABLE: current membership, authority changes, lifecycle,
roles and time are unknown. It does not compare against a fabricated empty
catalog or call every identity retained-only.

Optional `--current-owner-export PATH --current-owner-sha256 SHA256` accepts a
`pi-owner-reference-catalog-export-v1` document. This is a reference-only,
owner-attested artifact with exact UTF-8 bytes, snapshot/schema/authorization
scope, authority, lifecycle, canonical alternatives, provenance and explicit
unknown role/time fields. The operator must verify the owner publication and
trusted manifest hash; the loader validates bytes and structure, not the owner's
identity or authorization authenticity. It cannot expand an occurrence-export
approval or feed current-only identities into sample reports. Comparison is
case-sensitive, keeps aliases unapplied and treats source absence as an observed
scope difference, not deletion or corruption. Missing lifecycle/canonical
information remains unknown rather than an invented change or conflict.

A source-bound provider observation may additionally carry
`source_asserted_role=PROVIDER_REPORTED_REQUIRED_PERMISSION`, an exact retained
provider field path, event/payload identity and
`role_interpretation_rule=pi-retained-provider-required-v1`. Its independent
manifest role remains UNKNOWN. A provider scan timestamp is not permission-use
or execution time. The original approved export cannot acquire this assertion
from a token name, matching sample, or unrelated payload. Source-audit supplements
outside that export remain separate; no cohort, approval or model feature changes
follow. Sample reports now include identity-source digest, API-release and
protection context separately from provider metadata.
