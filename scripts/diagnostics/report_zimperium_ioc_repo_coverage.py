"""Inventory Zimperium IOC repository coverage against local catalog and ingest queue."""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from obsidiandroid.database.cohort_sql_fragments import (
    latest_artifact_hash_registry_subquery,
)
from obsidiandroid.database.db_engine import database_connection


HEX_RE = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")
REPO_ROOT = Path("research/external_iocs/Zimperium-IOC")
OUTPUT_DIR = Path("output/diagnostics")
SUMMARY_CSV = OUTPUT_DIR / "zimperium_ioc_repo_coverage_summary_latest.csv"
NEW_HASHES_CSV = OUTPUT_DIR / "zimperium_ioc_repo_new_hashes_latest.csv"


@dataclass(frozen=True)
class CatalogRecord:
    family_label: str
    classification_primary: str
    android_package_name: str


def infer_hash_type(token: str) -> str:
    if len(token) == 32:
        return "md5"
    if len(token) == 40:
        return "sha1"
    if len(token) == 64:
        return "sha256"
    return "unknown"


def infer_source_label(rel_path: Path) -> str:
    stem = rel_path.stem.lower().replace("_", "-")
    parent = rel_path.parent.name.lower().replace("_", "-")
    return f"external_ioc_zimperium_{parent}_{stem}"


def extract_hashes(path: Path) -> list[str]:
    text = path.read_text(errors="ignore")
    return [match.group(0).lower() for match in HEX_RE.finditer(text)]


def load_local_indexes() -> tuple[
    dict[str, CatalogRecord],
    set[str],
    set[str],
    set[str],
    dict[str, str],
    dict[str, str],
]:
    catalog_sha256: dict[str, CatalogRecord] = {}
    queue_md5: set[str] = set()
    queue_sha1: set[str] = set()
    queue_sha256: set[str] = set()
    registry_md5_to_sha256: dict[str, str] = {}
    registry_sha1_to_sha256: dict[str, str] = {}
    with database_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT LOWER(sha256), COALESCE(family_label, ''), COALESCE(classification_primary, ''),
                   COALESCE(android_package_name, '')
            FROM malware_sample_catalog
            WHERE COALESCE(sha256, '') <> ''
            """
        )
        for sha256, family_label, primary, package_name in cur.fetchall():
            catalog_sha256[str(sha256)] = CatalogRecord(
                family_label=str(family_label),
                classification_primary=str(primary),
                android_package_name=str(package_name),
            )

        cur.execute(
            """
            SELECT LOWER(COALESCE(artifact_hash_norm, '')), LOWER(COALESCE(artifact_hash_type, ''))
            FROM malware_artifact_ingest_queue
            WHERE COALESCE(artifact_hash_norm, '') <> ''
            """
        )
        for token, hash_type in cur.fetchall():
            token = str(token)
            hash_type = str(hash_type)
            if hash_type == "md5":
                queue_md5.add(token)
            elif hash_type == "sha1":
                queue_sha1.add(token)
            elif hash_type == "sha256":
                queue_sha256.add(token)

        registry_sql = latest_artifact_hash_registry_subquery()
        cur.execute(
            f"""
            SELECT
              LOWER(COALESCE(md5, '')) AS md5_value,
              LOWER(COALESCE(sha1, '')) AS sha1_value,
              LOWER(COALESCE(sha256, '')) AS sha256_value
            FROM {registry_sql} AS h
            WHERE COALESCE(sha256, '') <> ''
            """
        )
        for md5_value, sha1_value, sha256_value in cur.fetchall():
            md5_value = str(md5_value)
            sha1_value = str(sha1_value)
            sha256_value = str(sha256_value)
            if md5_value:
                registry_md5_to_sha256[md5_value] = sha256_value
            if sha1_value:
                registry_sha1_to_sha256[sha1_value] = sha256_value
        cur.close()
    return (
        catalog_sha256,
        queue_md5,
        queue_sha1,
        queue_sha256,
        registry_md5_to_sha256,
        registry_sha1_to_sha256,
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (
        catalog_sha256,
        queue_md5,
        queue_sha1,
        queue_sha256,
        registry_md5_to_sha256,
        registry_sha1_to_sha256,
    ) = load_local_indexes()

    summary_rows: list[dict[str, object]] = []
    new_hash_rows: list[dict[str, object]] = []

    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or ".git/" in str(path):
            continue

        hashes = extract_hashes(path)
        if not hashes:
            continue

        rel_path = path.relative_to(REPO_ROOT)
        unique_hashes = list(dict.fromkeys(hashes))
        hash_types = Counter(infer_hash_type(h) for h in unique_hashes)
        catalog_matches = 0
        queue_matches = 0
        new_hashes = 0
        matched_families: Counter[str] = Counter()
        matched_primary: Counter[str] = Counter()

        for token in unique_hashes:
            hash_type = infer_hash_type(token)
            in_catalog = False
            in_queue = False
            if hash_type == "sha256":
                record = catalog_sha256.get(token)
                if record is not None:
                    in_catalog = True
                    matched_families[record.family_label or "<blank>"] += 1
                    matched_primary[record.classification_primary or "<blank>"] += 1
                if token in queue_sha256:
                    in_queue = True
            elif hash_type == "sha1":
                if token in queue_sha1:
                    in_queue = True
                else:
                    mapped_sha256 = registry_sha1_to_sha256.get(token, "")
                    if mapped_sha256:
                        record = catalog_sha256.get(mapped_sha256)
                        if record is not None:
                            in_catalog = True
                            matched_families[record.family_label or "<blank>"] += 1
                            matched_primary[record.classification_primary or "<blank>"] += 1
                        elif mapped_sha256 in queue_sha256:
                            in_queue = True
            elif hash_type == "md5":
                if token in queue_md5:
                    in_queue = True
                else:
                    mapped_sha256 = registry_md5_to_sha256.get(token, "")
                    if mapped_sha256:
                        record = catalog_sha256.get(mapped_sha256)
                        if record is not None:
                            in_catalog = True
                            matched_families[record.family_label or "<blank>"] += 1
                            matched_primary[record.classification_primary or "<blank>"] += 1
                        elif mapped_sha256 in queue_sha256:
                            in_queue = True

            if in_catalog:
                catalog_matches += 1
            elif in_queue:
                queue_matches += 1
            else:
                new_hashes += 1
                new_hash_rows.append(
                    {
                        "repo_file": str(rel_path),
                        "source_label": infer_source_label(rel_path),
                        "hash_type": hash_type,
                        "hash_value": token,
                    }
                )

        dominant_family = matched_families.most_common(1)[0][0] if matched_families else ""
        dominant_primary = matched_primary.most_common(1)[0][0] if matched_primary else ""
        summary_rows.append(
            {
                "repo_file": str(rel_path),
                "source_label": infer_source_label(rel_path),
                "unique_hashes": len(unique_hashes),
                "md5_hashes": hash_types.get("md5", 0),
                "sha1_hashes": hash_types.get("sha1", 0),
                "sha256_hashes": hash_types.get("sha256", 0),
                "catalog_matches": catalog_matches,
                "queue_matches": queue_matches,
                "new_hashes": new_hashes,
                "dominant_catalog_family": dominant_family,
                "dominant_catalog_primary": dominant_primary,
            }
        )

    summary_rows.sort(key=lambda row: (-int(row["new_hashes"]), str(row["repo_file"])))
    new_hash_rows.sort(key=lambda row: (str(row["repo_file"]), str(row["hash_value"])))

    with SUMMARY_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        if summary_rows:
            writer.writeheader()
            writer.writerows(summary_rows)

    with NEW_HASHES_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["repo_file", "source_label", "hash_type", "hash_value"])
        writer.writeheader()
        writer.writerows(new_hash_rows)

    print(f"Wrote {SUMMARY_CSV}")
    print(f"Wrote {NEW_HASHES_CSV}")
    print(f"Summary rows: {len(summary_rows)}")
    print(f"New hashes: {len(new_hash_rows)}")


if __name__ == "__main__":
    main()
