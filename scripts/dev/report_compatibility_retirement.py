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
    DATABASE_COMPAT_CANDIDATE_DELETE_TREES,
    DATABASE_COMPAT_DEFER_TREES,
    DATABASE_COMPAT_KEEP_TREES,
    LEGACY_SUBTREE_RETIREMENT_BUCKETS,
    LEGACY_TREE_RETIREMENT_MATRIX,
)
from obsidiandroid.database.facade_manifest import (
    REPO_ROOT_DATABASE_CANDIDATE_DELETE_FILES,
    REPO_ROOT_DATABASE_DEFER_FILES,
    REPO_ROOT_DATABASE_KEEP_FILES,
    REPO_ROOT_DATABASE_RETIRED_FILES,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    print("Compatibility Retirement Matrix")
    print("------------------------------")
    print("Tip: set OBSIDIANDROID_WARN_LEGACY_SHIMS=1 to surface opt-in warnings for ready-now shim batches.")
    print("Tip: ordinary shim-only legacy leaves are now expected to use shared helpers from obsidiandroid.legacy_shim_lazy.")
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
    print("Repo-Root Database Shim Split")
    print("-----------------------------")
    print("Keep trees:")
    for item in DATABASE_COMPAT_KEEP_TREES:
        print(f"  - {item}")
    print("Candidate-delete trees:")
    if DATABASE_COMPAT_CANDIDATE_DELETE_TREES:
        for item in DATABASE_COMPAT_CANDIDATE_DELETE_TREES:
            print(f"  - {item}")
    else:
        print("  - none")
    if DATABASE_COMPAT_DEFER_TREES:
        print("Defer trees:")
        for item in DATABASE_COMPAT_DEFER_TREES:
            print(f"  - {item}")
    else:
        print("Defer trees:")
        print("  - none")
    print("Keep files:")
    for item in REPO_ROOT_DATABASE_KEEP_FILES:
        print(f"  - database/{item}")
    print("Candidate-delete files:")
    if REPO_ROOT_DATABASE_CANDIDATE_DELETE_FILES:
        for item in REPO_ROOT_DATABASE_CANDIDATE_DELETE_FILES:
            print(f"  - database/{item}")
    else:
        print("  - none")
    if REPO_ROOT_DATABASE_DEFER_FILES:
        print("Deferred files:")
        for item in REPO_ROOT_DATABASE_DEFER_FILES:
            print(f"  - database/{item}")
    else:
        print("Deferred files:")
        print("  - none")
    if REPO_ROOT_DATABASE_RETIRED_FILES:
        print("Retired files:")
        for item in REPO_ROOT_DATABASE_RETIRED_FILES:
            print(f"  - database/{item}")
    else:
        print("Retired files:")
        print("  - none")
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
