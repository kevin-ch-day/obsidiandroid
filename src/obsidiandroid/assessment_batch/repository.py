"""Reviewed-head guard inside the existing V1 MariaDB append transaction."""

from obsidiandroid.assessment.mariadb_store import MariaDBAssessmentStore
from .service import BatchConflict


class ReviewedMariaDBRepository(MariaDBAssessmentStore):
    def append_reviewed(self, body, *, expected_id, assessed_at_utc):
        active = {}

        def connect():
            conn = self.connection_factory()
            active["connection"] = conn
            return conn

        def guard(stage):
            if stage == "after_artifact_lock":
                with active["connection"].cursor() as cur:
                    cur.execute(
                        "SELECT assessment_id FROM core_assessment_revision WHERE artifact_sha256=%s ORDER BY revision DESC LIMIT 1",
                        (body["artifact"]["sha256"],),
                    )
                    row = cur.fetchone()
                    if (row[0] if row else None) != expected_id:
                        raise BatchConflict(
                            "Reviewed assessment head changed inside transaction"
                        )

        writer = MariaDBAssessmentStore(
            connect,
            database=self.database,
            allow_production=self.database == "obsidiandroid_core_prod",
            max_retries=self.max_retries,
            failure_hook=guard,
        )
        return writer.append(body, assessed_at_utc=assessed_at_utc)
