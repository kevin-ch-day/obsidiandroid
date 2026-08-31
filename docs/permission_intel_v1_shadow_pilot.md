# Permission Intel v1 Read-Only Shadow Pilot

## Authority and scope

This pilot is pinned to shared commit
`54b23b581939184e8dd8668e38837ca1cd15013d`, migration-set digest
`1bec1edabf99fbebffc9737e8b5d14076d3566b963c4878c9b3361bbe269ed5c`,
catalog digest
`075accc8aa2042d0d9454ba12e8625b87e76fe54366532c6bca21d56066fc334`,
and catalog-plan digest
`aae4c1b48f043e58293884183235f344d8ab0e7e18cfd2362b99725227234cca`.

The source set is `android-17-r1-audit-2026-08-30-source-identity-correction-1`.
It supersedes the prior release only to correct the Health manifest's exact
tagged Gitiles path; the frozen file bytes and all parsed permission facts are
unchanged.

ObsidianDroid was selected because its normal Permission Intel role is
read-oriented and its primary checkout was clean at the audited commit. Android
17 r1 is accepted only as an explicitly incomplete shadow-test candidate. It is
not exhaustive Android authority and does not include canonical OEM or
operational observations.

## Architecture

Legacy queries remain authoritative. The new adapter issues parameterized
`SELECT` statements only against `android_permission_v1_*` views. Runtime code
does not import the shared Python package. The shared package is a test-harness
dependency only during disposable MariaDB integration.

Shadow mode is controlled by
`OBSIDIANDROID_PERMISSION_INTEL_V1_SHADOW_MODE`:

- unset or `LEGACY_ONLY`: no gate or v1 query runs;
- `LEGACY_WITH_V1_SHADOW`: the gate and selected v1 lookup run, but the exact
  legacy value remains the returned authority;
- `V1_UNAVAILABLE_LEGACY_ACTIVE`: diagnostic-only and cannot be configured.

There is intentionally no `V1_AUTHORITATIVE` mode. Gate failure produces a
structured, credential-free diagnostic and never activates an analytical
fallback as platform authority.

## Minimum-version gate

The gate reads `android_permission_v1_catalog_release`, requires one compatible
accepted/imported catalog row, keeps full API versions as strings, and reports
explicit compatibility states. The pinned catalog returns
`COMPATIBLE_INCOMPLETE_SCOPE` because `exhaustive_scope` is false. Candidate or
missing catalogs are unavailable; compatible but different accepted content is
reported as stale rather than silently accepted as the pinned candidate.

## Protection and authority

The adapter uses the complete pinned base, modifier, and permission-flag
vocabularies. Compatibility text is serialized as base first followed by every
modifier in stable view order with `|` delimiters. `internal` is a protection
base. Unknown tokens remain explicit.

Authority is typed as AOSP public, hidden, internal, or module; Google/GMS;
OEM/vendor; application-defined; provisional; or unknown. Application-defined
does not imply manufacturer authority. Namespace and signer evidence do not
prove ownership. Obsidian risk, ATT&CK, capability, abuse, and analytical
taxonomy remain local analytical data.

## Parity evidence

The comparison model distinguishes equivalent facts, v1 metadata additions,
legacy-only/v1-only rows, protection, authority, lifecycle and provenance
differences, legacy non-expressiveness, unsupported queries, and errors. JSON is
canonical and stably sorted; its SHA-256 excludes wall-clock time. Markdown is
derived from the same payload. Disposable output is labeled
`disposable_integration_evidence`, never production parity.

The 23-signal/54-mapping fallback remains unchanged. It is analytical taxonomy,
does not satisfy the platform catalog gate, and cannot make a failed shadow look
like current Android reference truth.

## Disposable integration

Tests use a rootless, network-disabled MariaDB 11.8 container, generated
temporary credentials, the pinned shared migrations and catalog plan, and
container-local SQL execution. Production names, host sockets, absent explicit
ephemeral consent, and digest drift are rejected. The real adapter SELECT text
is executed, write statements are refused, artifacts go under `/tmp`, and
container teardown is mandatory.

The v1 views expose a permission's `sdk_extension_release_id` separately from
its platform release. They do not expose SDK-extension detail rows through a
versioned view, and the pinned selected declarations currently carry no
non-null SDK-extension ID. The pilot preserves that separation and records the
detail-view limitation instead of querying an unversioned table.

## Live verification status, not cutover approval

A bounded read-only query-contract verification now passes against the accepted
`android_permission_intel` catalog: the gate reports
`COMPATIBLE_INCOMPLETE_SCOPE`, the exact `android.permission.INTERNET` anchor is
`AOSP_PUBLIC`, the lowercase variant does not match, and the source-evidence
query is executable. No SQL was deployed and no database row was changed by
that verification. Overall routine readiness remains blocked when the connector
does not use `obsidiandroid_pipeline_reader@localhost`.

The checkout still has no private repo-local database configuration. Routine
operation therefore requires an approved least-privilege reader option file or
repo-local ignored `.env`/`.env.local` settings. Run the redacted probe after
installing that configuration:

```bash
python -m obsidiandroid.database.permission_intel_v1 --json
```

This verification does not authorize v1 analytical cutover or production
writes. The legacy analytical path remains authoritative and v1 remains a
read-only shadow.

The eventual sequence is:

1. Disposable query validation.
2. Read-only production schema attestation.
3. Separately authorized additive production deployment. **Completed for API-0001 through API-0007.**
4. Live Obsidian shadow reads. **Bounded verification completed.**
5. Install a durable least-privilege Obsidian reader configuration.
6. Reviewed parity period.
7. Explicit read cutover.
8. Retained switchback.
