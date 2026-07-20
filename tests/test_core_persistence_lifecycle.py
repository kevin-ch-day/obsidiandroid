"""Synthetic tests for Phase 1 Core persistence failure handling.

No test in this module opens a database connection or creates database objects.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from obsidiandroid.governance.core_persistence_lifecycle import finalize_artifacts_then_attempt_core


def _artifact_preserver(path: Path):
    def preserve() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"frozen synthetic evidence\n")
    return preserve


def test_failed_core_persistence_preserves_artifact_and_records_safe_failure(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "run" / "evidence.json"
    outcomes: list[dict[str, object]] = []
    before_after_calls: list[str] = []
    preserve = _artifact_preserver(artifact)

    def forbidden_primary_write(*args, **kwargs):  # pragma: no cover - must never execute
        raise AssertionError("source database helper must not be used as a Core fallback")

    monkeypatch.setattr("obsidiandroid.database.db_engine.execute_query", forbidden_primary_write)

    def fail_core() -> None:
        before_after_calls.append("core")
        raise RuntimeError("password=do-not-record")

    outcome = finalize_artifacts_then_attempt_core(
        preserve_artifacts=preserve,
        persist_to_core=fail_core,
        record_outcome=outcomes.append,
        core_persistence_enabled=True,
    )

    assert artifact.read_bytes() == b"frozen synthetic evidence\n"
    assert hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert before_after_calls == ["core"]
    assert outcome.core_persistence_status == "failed"
    assert outcome.core_persistence_succeeded is False
    assert outcome.migration_applied is False
    assert outcome.run_imported is False
    assert outcomes == [{
        "artifact_status": "preserved", "core_persistence_status": "failed", "core_persistence_succeeded": False,
        "migration_applied": False, "run_imported": False, "failure_code": "core_persistence_failed", "exception_type": "RuntimeError",
    }]
    assert "password" not in repr(outcomes)


def test_disabled_core_is_distinct_and_does_not_attempt_persistence(tmp_path: Path) -> None:
    artifact = tmp_path / "run" / "evidence.json"
    outcomes: list[dict[str, object]] = []

    def unexpected_core_attempt() -> None:
        raise AssertionError("disabled Core persistence must not be attempted")

    outcome = finalize_artifacts_then_attempt_core(
        preserve_artifacts=_artifact_preserver(artifact),
        persist_to_core=unexpected_core_attempt,
        record_outcome=outcomes.append,
        core_persistence_enabled=False,
    )

    assert artifact.exists()
    assert outcome.core_persistence_status == "disabled"
    assert outcome.failure_code == "feature_flag_disabled"
    assert outcomes[0]["core_persistence_succeeded"] is False


def test_retry_does_not_duplicate_artifact_and_never_claims_import(tmp_path: Path) -> None:
    artifact = tmp_path / "run" / "evidence.json"
    outcomes: list[dict[str, object]] = []
    preserve_calls = 0

    def preserve() -> None:
        nonlocal preserve_calls
        preserve_calls += 1
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if not artifact.exists():
            artifact.write_text("one immutable artifact\n", encoding="utf-8")

    def fail_core() -> None:
        raise ConnectionError("synthetic Core unavailable")

    for _ in range(2):
        outcome = finalize_artifacts_then_attempt_core(
            preserve_artifacts=preserve,
            persist_to_core=fail_core,
            record_outcome=outcomes.append,
            core_persistence_enabled=True,
        )
        assert outcome.run_imported is False
        assert outcome.migration_applied is False

    assert preserve_calls == 2
    assert list(artifact.parent.iterdir()) == [artifact]
    assert artifact.read_text(encoding="utf-8") == "one immutable artifact\n"
    assert [entry["core_persistence_status"] for entry in outcomes] == ["failed", "failed"]
