# Future taxonomy-repair workflow

Use this workflow for each candidate, including HippoSMS:

```text
candidate investigation
→ independent evidence review
→ proposed receipt and reviewable SQL
→ explicit approval
→ approved database application
→ post-change validation
→ finalized, hashed receipt
```

Create a dated package only after the proposed action is narrow and approved:

```text
governance/taxonomy_repairs/YYYY-MM-DD_<repair-slug>/
```

The package must include the required files listed in [README.md](README.md).

Rules:

1. Use exact IDs and restrictive `WHERE` clauses; do not perform bulk cleanup.
2. Capture before-state evidence before application whenever possible. If this
   is impossible, record a reconstructed capture mode and its limitation.
3. Preserve historical families, mappings, and evidence unless their removal is
   separately approved.
4. Require at least independent external evidence plus database-specific review
   before creating or reactivating current authority.
5. Record a rollback that reverses only the approved fields.
6. Validate affected rows and global taxonomy invariants after application.
7. Never commit credentials, package names, raw sample IDs, APK hashes, or raw
   evidence extracts.
