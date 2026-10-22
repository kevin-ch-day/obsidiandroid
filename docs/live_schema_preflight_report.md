# Live schema preflight guide

Keep deployment-specific observations and decisions in local notes outside the
repository, loaded through gitignored `CLAUDE.local.md`. This tracked guide is a
procedure, not a live inspection receipt or authorization status.

Before a source-dependent analysis, use the authorized read-only account to record:

1. Source identity, server version, UTC timestamp and transaction/isolation scope.
2. Exact sample identity constraints and duplicate/conflicting identity coverage.
3. Report/extraction identity and immutability, distinct from mutable update times.
4. Engine/label/taxonomy authority and the temporal scope of each metadata fact.
5. Exact permission strings, source provenance, declaration completeness and
   dictionary/version coverage; missing extraction is not an empty permission set.
6. Whether all consumed sources share a coherent snapshot. If they do not, preserve
   separately hashed extracts and report the limitation.

Save counts, SQL, credentials-free connection receipts, findings and the operator's
scope-specific decision in a new local evidence directory. Do not copy passwords,
authentication material, machine paths or current readiness decisions into Git.
A read-only inspection does not authorize cohort locking, writes, provider requests,
training or evaluation. Preserve fail-closed runtime behavior and its existing
contracts until a separately reviewed change is authorized.

Historical environment-specific preflight records are retained in local operator
notes. Their conclusions must not be presented as current evidence without a fresh
inspection under the appropriate authorization.
