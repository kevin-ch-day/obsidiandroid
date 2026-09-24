# Read-only operational assessment API

The WSGI adapter uses `AssessmentService(None, store)`, the same current/history
service and unchanged V1 JSON contract as the CLI. It never invokes assessment
composition, provider clients, migrations or inserts. MariaDB retrieval uses the
existing server-enforced read-only store transactions and exact catalog check.

- `GET /artifact/{sha256}` returns the current V1 record, including identity,
  all assessment fields, conflict/unresolved state, evidence and provenance.
- `GET /artifact/{sha256}/history?limit=50&after_revision=0` returns existing
  revisions in ascending order. Limit is 1–200; use `next_after_revision` to page.
  An exhausted page is 200 with empty records; an unassessed SHA is 404.

No pre-existing HTTP authentication framework was present in this repository.
This small adapter requires an explicit bearer token (at least 32 ASCII
characters), uses constant-time comparison, and provides no anonymous endpoint,
write route, CORS grant, or cached response. Keep secrets in the process
configuration, never in URLs. Reuse private MySQL option files; choose an account
with SELECT on the assessment tables. Production grants were not changed.

For local development, set `OBSIDIANDROID_ASSESSMENT_API_TOKEN` to a fresh secret
in your private environment, then run:

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.assessment.http_api \
  --database obsidiandroid_core_prod \
  --db-option-file /private/assessment-reader.cnf --allow-production
```

This binds **127.0.0.1:8765 only** using the standard-library development server.
It is not a public deployment recipe. A separately reviewed deployment should
host `create_app(...)` in a production WSGI server behind TLS/authenticated ingress,
with request/rate limits and a read-only DB role. No server was deployed by this
sprint. External proxy configuration and multi-user authorization are follow-up.

Send `Authorization: Bearer <secret>` as a header. Success returns the exact
persisted V1 JSON; HTTP adds no independent classification logic. Errors are
401 unauthorized, 400 invalid identity/pagination, 404 unavailable artifact/route,
405 unsupported method, and 503 sanitized retrieval failure. Database exception
text and credentials are never included in responses. `--help` is side-effect free.
