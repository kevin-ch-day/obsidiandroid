"""Synthetic-safe lifecycle boundary for future Core persistence.

This module deliberately does not implement a Core database writer.  It makes
the required ordering and failure representation testable before Phase 2:
filesystem evidence is finalized first, then an injected Core persistence
callback may be attempted.  No source-database helper is imported or used.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CorePersistenceOutcome:
    """Credential-safe result for an optional future Core persistence attempt."""

    artifact_status: str
    core_persistence_status: str
    core_persistence_succeeded: bool
    migration_applied: bool
    run_imported: bool
    failure_code: str | None = None
    exception_type: str | None = None

    def as_evidence(self) -> dict[str, Any]:
        return asdict(self)


def finalize_artifacts_then_attempt_core(
    *,
    preserve_artifacts: Callable[[], None],
    persist_to_core: Callable[[], None],
    record_outcome: Callable[[dict[str, Any]], None],
    core_persistence_enabled: bool,
) -> CorePersistenceOutcome:
    """Preserve artifacts once and represent disabled/failed Core persistence.

    ``persist_to_core`` is dependency-injected exclusively so the Phase 1
    tests can prove failure behavior without opening any database connection.
    A future Phase 2 writer must be separately reviewed before it can be passed
    here by production code.
    """
    preserve_artifacts()
    if not core_persistence_enabled:
        outcome = CorePersistenceOutcome(
            artifact_status="preserved",
            core_persistence_status="disabled",
            core_persistence_succeeded=False,
            migration_applied=False,
            run_imported=False,
            failure_code="feature_flag_disabled",
        )
        record_outcome(outcome.as_evidence())
        return outcome
    try:
        persist_to_core()
    except Exception as exc:  # The outcome records type only; never secret-bearing messages.
        outcome = CorePersistenceOutcome(
            artifact_status="preserved",
            core_persistence_status="failed",
            core_persistence_succeeded=False,
            migration_applied=False,
            run_imported=False,
            failure_code="core_persistence_failed",
            exception_type=type(exc).__name__,
        )
        record_outcome(outcome.as_evidence())
        return outcome
    outcome = CorePersistenceOutcome(
        artifact_status="preserved",
        core_persistence_status="succeeded",
        core_persistence_succeeded=True,
        migration_applied=False,
        run_imported=False,
    )
    record_outcome(outcome.as_evidence())
    return outcome
