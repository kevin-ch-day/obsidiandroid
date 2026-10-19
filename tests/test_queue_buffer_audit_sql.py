"""Exercise read-only queue audit SQL against disposable relational fixtures."""

from pathlib import Path
import re
import sqlite3


def test_queue_audit_counts_materialized_rows_once_across_hash_types() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "database/sql/malware_artifact_ingest_queue_buffer_audit.sql"
    sql = re.sub(r"(?m)^\s*--.*$", "", sql_path.read_text())
    queries = [part.strip() for part in sql.split(";") if part.strip()]
    with sqlite3.connect(":memory:") as conn:
        conn.executescript("""
            CREATE TABLE malware_sample_catalog (sha256 TEXT COLLATE NOCASE PRIMARY KEY);
            CREATE TABLE malware_artifact_hash_registry (
                sha256 TEXT COLLATE NOCASE PRIMARY KEY,
                md5 TEXT COLLATE NOCASE, sha1 TEXT COLLATE NOCASE
            );
            CREATE TABLE malware_artifact_ingest_queue (
                ingest_id INTEGER PRIMARY KEY, workload_lane TEXT, artifact_hash_type TEXT,
                artifact_hash_sha256 TEXT COLLATE NOCASE,
                artifact_hash_md5 TEXT COLLATE NOCASE, artifact_hash_sha1 TEXT COLLATE NOCASE,
                queue_status TEXT, result_code TEXT
            );
        """)
        conn.executemany("INSERT INTO malware_sample_catalog VALUES (?)", [("A",), ("B",), ("C",), ("D",)])
        conn.executemany(
            "INSERT INTO malware_artifact_hash_registry VALUES (?,?,?)",
            [("B", "MD5B", "SHA1B"), ("C", "MD5C", "SHA1C"),
             ("D", "MD5B", "SHA1D"), ("ORPHAN", "MD5O", "SHA1O")],
        )
        conn.executemany(
            "INSERT INTO malware_artifact_ingest_queue VALUES (?,?,?,?,?,?,?,?)",
            [
                (1, "android", "sha256", "a", None, None, "DONE", "OK"),
                (2, "android", "md5", None, "md5b", None, "DONE", "OK"),
                (3, "android", "sha1", None, None, "sha1c", "DONE", "OK"),
                (4, "android", "sha256", "B", "MD5B", "SHA1B", "DONE", "OK"),
                (5, "android", "md5", None, "MD5O", None, "DONE", "OK"),
                (6, "android", "sha256", "", "", None, "DONE", "OK"),
                (7, "android", "sha256", "A", None, None, "FAILED", "OK"),
                (8, "android", "sha256", "A", None, None, "PROCESSING", "OK"),
                (9, "android", "sha256", "A", None, None, "DONE", "ERROR"),
                (10, None, "md5", None, "MD5B", None, "DONE", "OK"),
            ],
        )
        # SET NAMES is the only non-SELECT statement; it is MySQL session setup.
        assert queries.pop(0) == "SET NAMES utf8mb4"
        shape, total, groups = [conn.execute(query).fetchall() for query in queries]
        assert sum(row[-1] for row in shape) == 10
        assert total == [(5, 1)]  # COUNT(DISTINCT lane) excludes NULL, as before.
        assert set(groups) == {
            ("android", "sha256", 2), ("android", "md5", 1),
            ("android", "sha1", 1), ("<null>", "md5", 1),
        }


def test_vendor_audit_exposes_missing_parsed_family_evidence() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "database/sql/label_authority_audit.sql"
    sql = re.sub(r"(?m)^\s*--.*$", "", sql_path.read_text())
    query = next(part.strip() for part in sql.split(";") if "AS evidence_rows" in part)
    with sqlite3.connect(":memory:") as conn:
        conn.execute(
            "CREATE TABLE malware_family_label_evidence "
            "(vendor_key TEXT, parsed_family_token TEXT, generic_token_flag INTEGER, is_active INTEGER)"
        )
        conn.executemany(
            "INSERT INTO malware_family_label_evidence VALUES (?,?,?,?)",
            [("vendor", None, 0, 1), ("vendor", "", 0, 1), ("vendor", "  ", 0, 1),
             ("vendor", "family", 0, 1), ("vendor", "ignored", 1, 0)],
        )
        cur = conn.execute(query)
        row = dict(zip([column[0] for column in cur.description], cur.fetchone()))
        assert row["evidence_rows"] == 4
        assert row["parsed_family_rows"] == 1
        assert row["missing_parsed_family_rows"] == 3
        assert row["generic_rows"] == 0
