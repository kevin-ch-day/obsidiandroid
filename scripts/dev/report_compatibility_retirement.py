#!/usr/bin/env python3
"""Print the current legacy-tree retirement matrix for canonical-relocation work."""

from __future__ import annotations

from pathlib import Path

from scripts.dev.compatibility_retirement_audit import (
    canonical_target_exists,
    collect_bucket_callers,
    collect_legacy_subtree_python_files,
    collect_ready_now_bucket_callers,
)
from scripts.dev.compatibility_retirement_manifest import (
    LEGACY_SUBTREE_RETIREMENT_BUCKETS,
    LEGACY_TREE_RETIREMENT_MATRIX,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    print("Compatibility Retirement Matrix")
    print("------------------------------")
    print("Canonical application imports use obsidiandroid.*; no repo-root Python compatibility tree remains.")
    print()
    if not LEGACY_TREE_RETIREMENT_MATRIX:
        print("No repo-root Python compatibility trees remain.")
        print()
    for entry in LEGACY_TREE_RETIREMENT_MATRIX:
        print(f"Root: {entry.root}")
        print(f"  Files: {entry.file_count}")
        print(f"  Status: {entry.implementation_status}")
        print(f"  Role: {entry.compatibility_role}")
        print("  Blockers:")
        for blocker in entry.blockers:
            print(f"    - {blocker}")
        print(f"  Next step: {entry.next_step}")
        print()
    print("Subtree Buckets")
    print("---------------")
    if not LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        print("No active compatibility subtree buckets.")
        print()
    for bucket in LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        print(f"Tree: {bucket.tree}")
        print(f"  Canonical target: {bucket.canonical_target}")
        print(f"  Bucket: {bucket.bucket}")
        print(f"  Files: {bucket.file_count}")
        print(f"  Readiness: {bucket.readiness}")
        print(f"  Why: {bucket.rationale}")
        print(f"  Next step: {bucket.next_step}")
        print(f"  Target exists: {'yes' if canonical_target_exists(repo_root, bucket.canonical_target) else 'no'}")
        print()
    print("Ready-Now Caller Audit")
    print("----------------------")
    for tree, hits in collect_ready_now_bucket_callers(repo_root).items():
        print(f"{tree}: {len(hits)} external legacy import caller(s)")
        for hit in hits[:5]:
            print(f"  - {hit}")
        if len(hits) > 5:
            print(f"  - ... {len(hits) - 5} more")
        print()
    print("Ready-Now File Batches")
    print("----------------------")
    for bucket in LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        if bucket.readiness != "ready to deprecate now":
            continue
        print(f"{bucket.tree} -> {bucket.canonical_target}")
        files = collect_legacy_subtree_python_files(repo_root, bucket.tree)
        for path in files:
            print(f"  - {path.relative_to(repo_root)}")
        print()
    print("Remaining Bucket Caller Audit")
    print("-----------------------------")
    all_hits = collect_bucket_callers(repo_root)
    for bucket in LEGACY_SUBTREE_RETIREMENT_BUCKETS:
        if not bucket.import_prefixes:
            continue
        hits = all_hits.get(bucket.tree, [])
        print(f"{bucket.tree}: {len(hits)} external legacy import caller(s)")
        if hits:
            for hit in hits[:5]:
                print(f"  - {hit}")
            if len(hits) > 5:
                print(f"  - ... {len(hits) - 5} more")
        else:
            print("  - none outside parity/tooling allowlists")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
