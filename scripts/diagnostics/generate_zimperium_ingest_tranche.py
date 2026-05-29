"""Generate an audited ingest SQL tranche from one or more IOC files.

Hash handling policy:
1. detect hash type from token length first,
2. dedupe against the ingest queue for all supported hash types,
3. dedupe against the live sample catalog for SHA-256 tokens,
4. resolve MD5/SHA1 hint hashes through the artifact-hash registry and skip
   them when their mapped SHA-256 is already known.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from obsidiandroid.database.cohort_sql_fragments import (
    latest_artifact_hash_registry_subquery,
)
from obsidiandroid.database.db_engine import database_connection


HEX_RE = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")


def infer_hash_type(token: str) -> str:
    if len(token) == 32:
        return "md5"
    if len(token) == 40:
        return "sha1"
    if len(token) == 64:
        return "sha256"
    raise ValueError(f"Unsupported hash length for token: {token}")


def summarize_hash_types(hashes: list[str]) -> dict[str, int]:
    summary = {"md5": 0, "sha1": 0, "sha256": 0}
    for token in hashes:
        summary[infer_hash_type(token)] += 1
    return summary


def extract_unique_hashes(paths: list[Path]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        text = path.read_text(errors="ignore")
        for match in HEX_RE.finditer(text):
            token = match.group(0).lower()
            if token not in seen:
                seen.add(token)
                ordered.append(token)
    return ordered


def _lookup_registry_sha256_mappings(
    cursor,
    *,
    hashes: list[str],
    hash_column: str,
) -> dict[str, str]:
    if not hashes:
        return {}
    placeholders = ",".join(["%s"] * len(hashes))
    registry_sql = latest_artifact_hash_registry_subquery()
    cursor.execute(
        f"""
        SELECT
          LOWER(COALESCE(h.{hash_column}, '')) AS hash_value,
          LOWER(COALESCE(h.sha256, '')) AS mapped_sha256
        FROM {registry_sql} AS h
        WHERE LOWER(COALESCE(h.{hash_column}, '')) IN ({placeholders})
          AND COALESCE(h.{hash_column}, '') <> ''
          AND COALESCE(h.sha256, '') <> ''
        """,
        tuple(hashes),
    )
    return {
        str(row[0]): str(row[1])
        for row in cursor.fetchall()
        if str(row[0]).strip() and str(row[1]).strip()
    }


def filter_new_hashes(hashes: list[str]) -> list[str]:
    if not hashes:
        return []
    placeholders = ",".join(["%s"] * len(hashes))
    catalog_sha256_matches: set[str] = set()
    queue_matches: set[str] = set()
    registry_known_tokens: set[str] = set()
    with database_connection() as conn:
        cur = conn.cursor()
        sha256_hashes = [h for h in hashes if len(h) == 64]
        md5_hashes = [h for h in hashes if len(h) == 32]
        sha1_hashes = [h for h in hashes if len(h) == 40]
        if sha256_hashes:
            sha256_placeholders = ",".join(["%s"] * len(sha256_hashes))
            cur.execute(
                f"SELECT LOWER(sha256) FROM malware_sample_catalog WHERE LOWER(sha256) IN ({sha256_placeholders})",
                tuple(sha256_hashes),
            )
            catalog_sha256_matches = {str(row[0]) for row in cur.fetchall()}
        cur.execute(
            f"SELECT LOWER(artifact_hash_norm) FROM malware_artifact_ingest_queue WHERE LOWER(artifact_hash_norm) IN ({placeholders})",
            tuple(hashes),
        )
        queue_matches = {str(row[0]) for row in cur.fetchall()}

        registry_mapped_sha256: dict[str, str] = {}
        if md5_hashes:
            registry_mapped_sha256.update(
                _lookup_registry_sha256_mappings(
                    cur,
                    hashes=md5_hashes,
                    hash_column="md5",
                )
            )
        if sha1_hashes:
            registry_mapped_sha256.update(
                _lookup_registry_sha256_mappings(
                    cur,
                    hashes=sha1_hashes,
                    hash_column="sha1",
                )
            )
        if registry_mapped_sha256:
            mapped_sha256s = list(dict.fromkeys(registry_mapped_sha256.values()))
            mapped_placeholders = ",".join(["%s"] * len(mapped_sha256s))
            cur.execute(
                f"SELECT LOWER(sha256) FROM malware_sample_catalog WHERE LOWER(sha256) IN ({mapped_placeholders})",
                tuple(mapped_sha256s),
            )
            mapped_catalog_matches = {str(row[0]) for row in cur.fetchall()}
            cur.execute(
                f"SELECT LOWER(artifact_hash_norm) FROM malware_artifact_ingest_queue WHERE LOWER(artifact_hash_norm) IN ({mapped_placeholders})",
                tuple(mapped_sha256s),
            )
            mapped_queue_matches = {str(row[0]) for row in cur.fetchall()}
            known_mapped_sha256 = mapped_catalog_matches | mapped_queue_matches
            registry_known_tokens = {
                token
                for token, mapped_sha256 in registry_mapped_sha256.items()
                if mapped_sha256 in known_mapped_sha256
            }
        cur.close()
    return [
        h
        for h in hashes
        if h not in catalog_sha256_matches
        and h not in queue_matches
        and h not in registry_known_tokens
    ]


def canonicalize_artifact_family(artifact_family: str | None) -> tuple[str | None, bool]:
    """Map supplied family label to canonical family name.

    Returns:
        tuple[str | None, bool]:
            canonical family name (or normalized input/None) and whether the value
            was authority-backed by active family slug or accepted alias mapping.
    """
    if artifact_family is None:
        return None, False
    token = artifact_family.strip()
    if token == "":
        return None, False
    lookup = token.lower()
    with database_connection() as conn:
        cur = conn.cursor()
        # Direct slug match first.
        cur.execute(
            """
            SELECT family_name
            FROM android_malware_family
            WHERE is_active = 1
              AND LOWER(TRIM(family_slug)) = %s
            LIMIT 1
            """,
            (lookup,),
        )
        row = cur.fetchone()
        if row:
            cur.close()
            return str(row[0]), True

        # Then active alias match, but only from accepted synonym surfaces.
        cur.execute(
            """
            SELECT f.family_name
            FROM android_malware_family_alias AS a
            JOIN android_malware_family AS f
              ON f.family_id = a.family_id
            WHERE a.is_active = 1
              AND f.is_active = 1
              AND LOWER(TRIM(a.alias_name)) = %s
              AND a.review_status = 'accepted'
              AND a.alias_type IN (
                'canonical',
                'public_report_name',
                'vendor_label',
                'vendor_alias'
              )
            ORDER BY
              CASE WHEN a.is_preferred = 1 THEN 0 ELSE 1 END,
              a.alias_id
            LIMIT 1
            """,
            (lookup,),
        )
        row = cur.fetchone()
        cur.close()
        if row:
            return str(row[0]), True
    return token, False


def sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def build_values_rows(
    hashes: list[str],
    artifact_name: str | None,
    artifact_family: str | None,
    artifact_category: str | None,
    artifact_subtype: str | None,
    artifact_source: str,
    workload_lane: str,
) -> str:
    rows: list[str] = []
    for token in hashes:
        hash_type = infer_hash_type(token)
        md5 = token if hash_type == "md5" else None
        sha1 = token if hash_type == "sha1" else None
        sha256 = token if hash_type == "sha256" else None
        rows.append(
            "  ("
            + ", ".join(
                [
                    sql_literal(hash_type),
                    sql_literal(token),
                    sql_literal(token),
                    sql_literal(md5),
                    sql_literal(sha1),
                    sql_literal(sha256),
                    sql_literal(artifact_name),
                    sql_literal(artifact_family),
                    sql_literal(artifact_category),
                    sql_literal(artifact_subtype),
                    sql_literal(artifact_source),
                    sql_literal(workload_lane),
                ]
            )
            + ")"
        )
    return ",\n".join(rows)


def build_sql(
    hashes: list[str],
    artifact_name: str | None,
    artifact_family: str | None,
    artifact_category: str | None,
    artifact_subtype: str | None,
    artifact_source: str,
    workload_lane: str,
    temp_suffix: str,
    source_note: str,
) -> str:
    values_sql = build_values_rows(
        hashes,
        artifact_name=artifact_name,
        artifact_family=artifact_family,
        artifact_category=artifact_category,
        artifact_subtype=artifact_subtype,
        artifact_source=artifact_source,
        workload_lane=workload_lane,
    )
    return f"""-- Generated Zimperium ingest tranche.
--
-- Source note:
--   * {source_note}

USE erebus_threat_intel_prod;

SET NAMES utf8mb4;

START TRANSACTION;

DROP TEMPORARY TABLE IF EXISTS tmp_external_ioc_ingest_{temp_suffix};

CREATE TEMPORARY TABLE tmp_external_ioc_ingest_{temp_suffix} (
  artifact_hash_type VARCHAR(16) NOT NULL,
  artifact_hash_raw VARCHAR(255) NOT NULL,
  artifact_hash_norm VARCHAR(64) NOT NULL PRIMARY KEY,
  artifact_hash_md5 CHAR(32) NULL,
  artifact_hash_sha1 CHAR(40) NULL,
  artifact_hash_sha256 CHAR(64) NULL,
  artifact_name VARCHAR(255) NULL,
  artifact_family VARCHAR(100) NULL,
  artifact_category VARCHAR(100) NULL,
  artifact_subtype VARCHAR(100) NULL,
  artifact_source VARCHAR(255) NOT NULL,
  workload_lane VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO tmp_external_ioc_ingest_{temp_suffix} (
  artifact_hash_type,
  artifact_hash_raw,
  artifact_hash_norm,
  artifact_hash_md5,
  artifact_hash_sha1,
  artifact_hash_sha256,
  artifact_name,
  artifact_family,
  artifact_category,
  artifact_subtype,
  artifact_source,
  workload_lane
) VALUES
{values_sql};

INSERT INTO malware_artifact_ingest_queue (
  artifact_hash_md5,
  artifact_hash_sha1,
  artifact_hash_sha256,
  artifact_name,
  artifact_family,
  artifact_category,
  artifact_subtype,
  artifact_source,
  workload_lane,
  artifact_hash_raw,
  artifact_hash_norm,
  artifact_hash_type,
  queue_status
)
SELECT
  t.artifact_hash_md5,
  t.artifact_hash_sha1,
  t.artifact_hash_sha256,
  t.artifact_name,
  t.artifact_family,
  t.artifact_category,
  t.artifact_subtype,
  t.artifact_source,
  t.workload_lane,
  t.artifact_hash_raw,
  t.artifact_hash_norm,
  t.artifact_hash_type,
  'PENDING'
FROM tmp_external_ioc_ingest_{temp_suffix} AS t
WHERE NOT EXISTS (
  SELECT 1
  FROM malware_artifact_ingest_queue AS existing
  WHERE LOWER(COALESCE(existing.artifact_hash_norm, '')) = t.artifact_hash_norm
)
AND NOT EXISTS (
  SELECT 1
  FROM malware_sample_catalog AS msc
  WHERE LOWER(COALESCE(msc.sha256, '')) = t.artifact_hash_norm
);

DROP TEMPORARY TABLE IF EXISTS tmp_external_ioc_ingest_{temp_suffix};

COMMIT;
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", action="append", required=True, help="IOC file to scan for hashes")
    parser.add_argument("--artifact-family")
    parser.add_argument("--artifact-category")
    parser.add_argument("--artifact-subtype")
    parser.add_argument("--artifact-name")
    parser.add_argument("--artifact-source", required=True)
    parser.add_argument("--workload-lane", default="raw_hash_reservoir")
    parser.add_argument("--temp-suffix", required=True)
    parser.add_argument("--source-note", required=True)
    parser.add_argument("--output", required=True)
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
    output_path = Path(args.output)
    output_path.write_text(
        build_sql(
            new_hashes,
            artifact_name=args.artifact_name,
            artifact_family=canonical_family,
            artifact_category=args.artifact_category,
            artifact_subtype=args.artifact_subtype,
            artifact_source=args.artifact_source,
            workload_lane=args.workload_lane,
            temp_suffix=args.temp_suffix,
            source_note=args.source_note,
        )
    )
    print(f"source_hashes={len(hashes)}")
    print(
        "source_hash_type_counts="
        f"md5:{hash_type_summary['md5']},"
        f"sha1:{hash_type_summary['sha1']},"
        f"sha256:{hash_type_summary['sha256']}"
    )
    print(f"new_hashes={len(new_hashes)}")
    print(f"artifact_family_input={args.artifact_family}")
    print(f"artifact_family_canonical={canonical_family}")
    print(f"artifact_family_authority_matched={1 if authority_matched else 0}")
    print(f"wrote={output_path}")


if __name__ == "__main__":
    main()
