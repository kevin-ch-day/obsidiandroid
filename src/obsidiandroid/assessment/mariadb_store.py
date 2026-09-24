"""Transactional MariaDB adapter for the unchanged operational V1 contract.

Connections are dedicated, non-pooled, selected explicitly, and closed per call.
No schema creation or upstream queries occur here. Default target policy accepts
only disposable persistence schemas; production requires separate explicit opt-in.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import logging
import re
import time
from typing import Callable

import mysql.connector

from .composition import canonical_json, digest, validate_sha256
from .contract import validate_body
from .revisions import validate_page, history_page

logger = logging.getLogger(__name__)


class AssessmentPersistenceError(RuntimeError):
    """Credential-free storage boundary error; original exception is chained."""


class MariaDBAssessmentStore:
    """Serialize appends per SHA; retain complete, immutable canonical JSON."""

    def __init__(
        self,
        connection_factory: Callable,
        *,
        database: str,
        allow_production: bool = False,
        max_retries: int = 3,
        failure_hook: Callable[[str], None] | None = None,
    ):
        if not re.fullmatch(r"obsidiandroid_core_persistence_test_\d{8}(?:_[a-z0-9]+)?", database):
            if database != "obsidiandroid_core_prod" or not allow_production:
                raise ValueError(
                    "An explicitly approved assessment database is required"
                )
        if not 0 <= max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        self.connection_factory = connection_factory
        self.database = database
        self.max_retries = max_retries
        self.failure_hook = failure_hook

    @contextmanager
    def connect(self, *, read_only=False):
        conn = None
        try:
            conn = self.connection_factory()
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("SELECT DATABASE()")
                if cur.fetchone()[0] != self.database:
                    raise ValueError(
                        "Assessment connection selected an unexpected database"
                    )
                cur.execute("SET time_zone = '+00:00'")
                cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                if read_only:
                    cur.execute("SET SESSION TRANSACTION READ ONLY")
            yield conn
        finally:
            if conn is not None:
                # Cleanup must not replace the primary transaction error, or turn
                # an acknowledged COMMIT into an apparent failed append.
                for cleanup in (conn.rollback, conn.close):
                    try:
                        cleanup()
                    except Exception as exc:
                        logger.warning(
                            "Assessment connection cleanup failed: %s errno=%s",
                            type(exc).__name__,
                            getattr(exc, "errno", None),
                        )

    def _hook(self, stage: str):
        if self.failure_hook:
            self.failure_hook(stage)

    def append(self, body: dict, *, assessed_at_utc: str) -> dict:
        """Atomically append or reuse latest input; retry only known rollback errors.

        Lost connections/unknown commit outcomes are surfaced, never blindly retried.
        A caller can retrieve current and replay the same input to reconcile.
        """
        body = deepcopy(body)
        validate_body(body, assessed_at_utc)
        sha, key = validate_sha256(body["artifact"]["sha256"]), digest(body)
        for attempt in range(self.max_retries + 1):
            try:
                with self.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO core_assessment_artifact (artifact_sha256) VALUES (%s) ON DUPLICATE KEY UPDATE artifact_sha256=VALUES(artifact_sha256)",
                            (sha,),
                        )
                        cur.execute(
                            "SELECT artifact_sha256 FROM core_assessment_artifact WHERE artifact_sha256=%s FOR UPDATE",
                            (sha,),
                        )
                        cur.fetchone()
                        self._hook("after_artifact_lock")
                        cur.execute(
                            "SELECT assessment_id,revision,input_digest,result_json FROM core_assessment_revision WHERE artifact_sha256=%s ORDER BY revision DESC LIMIT 1",
                            (sha,),
                        )
                        last = cur.fetchone()
                        if last and last[2] == key:
                            conn.commit()
                            return json.loads(last[3])
                        revision, previous = (
                            (last[1] + 1, last[0]) if last else (1, None)
                        )
                        assessment_id = digest(
                            dict(
                                artifact_sha256=sha,
                                input_digest=key,
                                revision=revision,
                                previous_assessment_id=previous,
                            )
                        )
                        result = dict(
                            body,
                            assessment_id=assessment_id,
                            revision=revision,
                            previous_assessment_id=previous,
                            assessed_at_utc=assessed_at_utc,
                        )
                        # Fields and provenance share one JSON document/INSERT, never
                        # independent partially committed rows.
                        encoded = canonical_json(result)
                        self._hook("after_fields_and_provenance_serialized")
                        cur.execute(
                            "INSERT INTO core_assessment_revision (assessment_id,artifact_sha256,revision,previous_assessment_id,input_digest,assessed_at_utc,result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (
                                assessment_id,
                                sha,
                                revision,
                                previous,
                                key,
                                assessed_at_utc,
                                encoded,
                            ),
                        )
                        self._hook("after_revision_insert")
                        self._hook("before_commit")
                    conn.commit()
                    return result
            except mysql.connector.Error as exc:
                if exc.errno in (1205, 1213) and attempt < self.max_retries:
                    time.sleep(0.01 * (attempt + 1))
                    continue
                raise AssessmentPersistenceError(
                    f"Assessment transaction failed (errno={exc.errno}); inspect current before replay"
                ) from exc
        raise AssertionError("Unreachable retry state")

    def _read(self, sql: str, key: str, *, many: bool = False, extra: tuple = ()):
        key = validate_sha256(key)
        try:
            with self.connect(read_only=True) as conn, conn.cursor() as cur:
                cur.execute(sql, (key, *extra))
                rows = cur.fetchall()
                values = [json.loads(row[0]) for row in rows]
                return values if many else (values[0] if values else None)
        except mysql.connector.Error as exc:
            raise AssessmentPersistenceError(
                f"Assessment retrieval failed (errno={exc.errno})"
            ) from exc

    def current(self, sha256: str) -> dict | None:
        return self._read(
            "SELECT result_json FROM core_assessment_revision WHERE artifact_sha256=%s ORDER BY revision DESC LIMIT 1",
            sha256,
        )

    def history(self, sha256: str) -> list[dict]:
        return self._read(
            "SELECT result_json FROM core_assessment_revision WHERE artifact_sha256=%s ORDER BY revision",
            sha256,
            many=True,
        )

    def by_id(self, assessment_id: str) -> dict | None:
        return self._read(
            "SELECT result_json FROM core_assessment_revision WHERE assessment_id=%s",
            assessment_id,
        )

    def history_page(
        self, sha256: str, *, limit: int = 50, after_revision: int = 0
    ) -> dict:
        sha = validate_sha256(sha256)
        validate_page(limit, after_revision)
        rows = self._read(
            "SELECT result_json FROM core_assessment_revision WHERE artifact_sha256=%s AND revision>%s ORDER BY revision LIMIT %s",
            sha,
            many=True,
            extra=(after_revision, limit + 1),
        )
        return history_page(sha, rows, limit)
