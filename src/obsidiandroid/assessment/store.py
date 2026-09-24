"""Local-only immutable assessment revisions with transactional append semantics.

This SQLite sidecar is not an Obsidian production database adapter.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .composition import canonical_json, digest, validate_sha256
from .contract import validate_body
from .revisions import validate_page, history_page

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS assessment_revision (
    assessment_id TEXT PRIMARY KEY CHECK(length(assessment_id)=64),
    artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256)=64 AND artifact_sha256 NOT GLOB '*[^0-9a-f]*'),
    revision INTEGER NOT NULL CHECK(revision>0),
    previous_assessment_id TEXT,
    input_digest TEXT NOT NULL CHECK(length(input_digest)=64),
    assessed_at_utc TEXT NOT NULL,
    result_json TEXT NOT NULL CHECK(json_valid(result_json)),
    UNIQUE(artifact_sha256, revision),
    UNIQUE(artifact_sha256, assessment_id),
    UNIQUE(previous_assessment_id),
    FOREIGN KEY(artifact_sha256, previous_assessment_id)
        REFERENCES assessment_revision(artifact_sha256, assessment_id),
    CHECK((revision=1 AND previous_assessment_id IS NULL) OR (revision>1 AND previous_assessment_id IS NOT NULL)),
    CHECK(json_extract(result_json,'$.assessment_id') IS NOT NULL AND json_extract(result_json,'$.assessment_id')=assessment_id),
    CHECK(json_extract(result_json,'$.artifact.sha256') IS NOT NULL AND json_extract(result_json,'$.artifact.sha256')=artifact_sha256),
    CHECK(json_extract(result_json,'$.revision') IS NOT NULL AND json_extract(result_json,'$.revision')=revision),
    CHECK(json_extract(result_json,'$.previous_assessment_id') IS previous_assessment_id),
    CHECK(json_extract(result_json,'$.assessed_at_utc') IS NOT NULL AND json_extract(result_json,'$.assessed_at_utc')=assessed_at_utc)
);
CREATE INDEX IF NOT EXISTS assessment_sha_latest ON assessment_revision(artifact_sha256, revision DESC);
CREATE TRIGGER IF NOT EXISTS assessment_no_update BEFORE UPDATE ON assessment_revision
BEGIN SELECT RAISE(ABORT, 'assessment revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS assessment_no_delete BEFORE DELETE ON assessment_revision
BEGIN SELECT RAISE(ABORT, 'assessment revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS assessment_append_only BEFORE INSERT ON assessment_revision
WHEN NEW.revision != COALESCE((SELECT MAX(revision)+1 FROM assessment_revision WHERE artifact_sha256=NEW.artifact_sha256),1)
 OR (NEW.revision>1 AND NEW.previous_assessment_id IS NOT (SELECT assessment_id FROM assessment_revision WHERE artifact_sha256=NEW.artifact_sha256 ORDER BY revision DESC LIMIT 1))
BEGIN SELECT RAISE(ABORT, 'revision must extend the current assessment'); END;
"""


class AssessmentStore:
    """Canonical retrievable V1 revisions in an explicitly selected local file."""

    def __init__(self, path: Path | str, *, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as conn:
                conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(
            self.path.resolve().as_uri() + "?mode=ro" if self.read_only else self.path,
            timeout=30,
            uri=self.read_only,
        )
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def history(self, sha256: str) -> list[dict]:
        sha = validate_sha256(sha256)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT result_json FROM assessment_revision WHERE artifact_sha256=? ORDER BY revision",
                (sha,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def current(self, sha256: str) -> dict | None:
        sha = validate_sha256(sha256)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM assessment_revision WHERE artifact_sha256=? ORDER BY revision DESC LIMIT 1",
                (sha,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def by_id(self, assessment_id: str) -> dict | None:
        key = validate_sha256(assessment_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM assessment_revision WHERE assessment_id=?",
                (key,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def history_page(
        self, sha256: str, *, limit: int = 50, after_revision: int = 0
    ) -> dict:
        sha = validate_sha256(sha256)
        validate_page(limit, after_revision)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT result_json FROM assessment_revision WHERE artifact_sha256=? AND revision>? ORDER BY revision LIMIT ?",
                (sha, after_revision, limit + 1),
            ).fetchall()
        return history_page(sha, [json.loads(row[0]) for row in rows], limit)

    def append(self, body: dict, *, assessed_at_utc: str) -> dict:
        """Reuse unchanged current input or append one revision under a write lock."""
        if self.read_only:
            raise ValueError("Read-only assessment store cannot append")
        validate_body(body, assessed_at_utc)
        sha = validate_sha256(body["artifact"]["sha256"])
        key = digest(body)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            last = conn.execute(
                "SELECT assessment_id,revision,input_digest,result_json FROM assessment_revision WHERE artifact_sha256=? ORDER BY revision DESC LIMIT 1",
                (sha,),
            ).fetchone()
            if last and last[2] == key:
                return json.loads(last[3])
            revision = last[1] + 1 if last else 1
            previous = last[0] if last else None
            assessment_id = digest(
                {
                    "artifact_sha256": sha,
                    "input_digest": key,
                    "revision": revision,
                    "previous_assessment_id": previous,
                }
            )
            result = {
                **body,
                "assessment_id": assessment_id,
                "revision": revision,
                "previous_assessment_id": previous,
                "assessed_at_utc": assessed_at_utc,
            }
            conn.execute(
                "INSERT INTO assessment_revision VALUES (?,?,?,?,?,?,?)",
                (
                    assessment_id,
                    sha,
                    revision,
                    previous,
                    key,
                    assessed_at_utc,
                    canonical_json(result),
                ),
            )
        return result
