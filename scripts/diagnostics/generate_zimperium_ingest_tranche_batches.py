"""Generate batched ingest SQL tranches from large IOC files.

This wraps `generate_zimperium_ingest_tranche.py` behavior for large feeds by:
1. extracting hashes from source files,
2. classifying hash type first and filtering to hashes not present in queue,
   plus catalog dedupe for SHA-256 only,
3. chunking output SQL into deterministic tranche files.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.diagnostics.generate_zimperium_ingest_tranche import (
    build_sql,
    canonicalize_artifact_family,
    extract_unique_hashes,
    filter_new_hashes,
    summarize_hash_types,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", action="append", required=True, help="IOC file to scan for hashes")
    parser.add_argument("--artifact-family")
    parser.add_argument("--artifact-category")
    parser.add_argument("--artifact-subtype")
    parser.add_argument("--artifact-name")
    parser.add_argument("--artifact-source", required=True)
    parser.add_argument("--workload-lane", default="raw_hash_reservoir")
    parser.add_argument("--temp-prefix", required=True, help="prefix for temp table suffix, e.g. 20260528otp")
    parser.add_argument("--source-note", required=True)
    parser.add_argument("--output-prefix", required=True, help="file prefix path, e.g. database/sql/artifact_ingest_tranche_2026_05_28_v")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument(
        "--start-batch-index",
        type=int,
        default=1,
        help=(
            "Batch label start index for output naming only. "
            "Data selection always starts from the current unresolved-hash head."
        ),
    )
    parser.add_argument(
        "--start-new-offset",
        type=int,
        default=0,
        help="Optional row offset into current unresolved hashes (default 0).",
    )
    parser.add_argument(
        "--allow-unmapped-family",
        action="store_true",
        help="Allow artifact-family values that are not authority-backed by canonical family or accepted alias.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = [Path(p) for p in args.source_file]
    hashes = extract_unique_hashes(paths)
    hash_type_summary = summarize_hash_types(hashes)
    new_hashes = filter_new_hashes(hashes)
    canonical_family, authority_matched = canonicalize_artifact_family(args.artifact_family)
    if args.artifact_family and not authority_matched and not args.allow_unmapped_family:
        raise SystemExit(
            "error: artifact family is not authority-backed. "
            "Either curate the family/alias first or pass --allow-unmapped-family."
        )

    batch_size = max(1, int(args.batch_size))
    max_batches = max(1, int(args.max_batches))
    start_idx = max(1, int(args.start_batch_index))
    start_new_offset = max(0, int(args.start_new_offset))

    total_new = len(new_hashes)
    print(f"source_hashes={len(hashes)}")
    print(
        "source_hash_type_counts="
        f"md5:{hash_type_summary['md5']},"
        f"sha1:{hash_type_summary['sha1']},"
        f"sha256:{hash_type_summary['sha256']}"
    )
    print(f"new_hashes={total_new}")
    print(f"artifact_family_input={args.artifact_family}")
    print(f"artifact_family_canonical={canonical_family}")
    print(f"artifact_family_authority_matched={1 if authority_matched else 0}")
    print(f"batch_size={batch_size}")
    print(f"max_batches={max_batches}")
    print(f"start_batch_index={start_idx}")
    print(f"start_new_offset={start_new_offset}")

    written = 0
    for local_idx, batch_no in enumerate(range(start_idx, start_idx + max_batches)):
        offset = start_new_offset + (local_idx * batch_size)
        chunk = new_hashes[offset : offset + batch_size]
        if not chunk:
            break
        suffix = f"{args.temp_prefix}_{batch_no:03d}"
        out_path = Path(f"{args.output_prefix}_{batch_no:03d}.sql")
        out_path.write_text(
            build_sql(
                chunk,
                artifact_name=args.artifact_name,
                artifact_family=canonical_family,
                artifact_category=args.artifact_category,
                artifact_subtype=args.artifact_subtype,
                artifact_source=args.artifact_source,
                workload_lane=args.workload_lane,
                temp_suffix=suffix,
                source_note=f"{args.source_note} (batch {batch_no})",
            )
        )
        print(f"wrote={out_path} rows={len(chunk)}")
        written += 1

    print(f"batches_written={written}")


if __name__ == "__main__":
    main()
