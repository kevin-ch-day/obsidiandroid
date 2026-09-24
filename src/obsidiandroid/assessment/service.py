"""Shared CLI/API application service over frozen, exact-hash source evidence."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from .composition import (
    ENGINE_VERSION,
    compose_assessment,
    digest,
    ordered,
    validate_sha256,
)
from typing import Protocol
from .revisions import compare_revisions


class AssessmentRepository(Protocol):
    """Storage boundary shared by the SQLite and MariaDB adapters."""

    def append(self, body: dict, *, assessed_at_utc: str) -> dict: ...
    def current(self, sha256: str) -> dict | None: ...
    def history(self, sha256: str) -> list[dict]: ...
    def by_id(self, assessment_id: str) -> dict | None: ...
    def history_page(
        self, sha256: str, *, limit: int = 50, after_revision: int = 0
    ) -> dict: ...


class FrozenEvidenceSource:
    """Validated source sidecar. Absence from its scope is not global nonexistence."""

    def __init__(self, bundle: dict):
        if (
            not isinstance(bundle, dict)
            or bundle.get("contract_version") != "obsidiandroid.assessment-evidence.v1"
        ):
            raise ValueError("Unsupported evidence bundle contract")
        if not isinstance(bundle.get("artifacts"), dict):
            raise ValueError("Evidence bundle requires an artifacts mapping")
        for sha, item in bundle["artifacts"].items():
            if (
                validate_sha256(sha) != sha
                or not isinstance(item, dict)
                or item.get("sha256") != sha
            ):
                raise ValueError(
                    "Evidence bundle contains an invalid artifact identity"
                )
        if digest(ordered(bundle["artifacts"])) != bundle.get("content_sha256"):
            raise ValueError("Evidence bundle content checksum mismatch")
        self._bundle = deepcopy(bundle)

    @classmethod
    def load(cls, path: Path | str):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def lookup(self, sha256: str) -> dict:
        sha = validate_sha256(sha256)
        if sha in self._bundle["artifacts"]:
            return deepcopy(self._bundle["artifacts"][sha])
        return {
            "sha256": sha,
            "catalog": [],
            "lookup_status": "not_in_snapshot",
            "source_snapshots": {
                "scope": "bounded_frozen_snapshot",
                "content_sha256": self._bundle["content_sha256"],
            },
        }


class AssessmentService:
    """Assess, retrieve current, and retrieve history using one result contract."""

    def __init__(
        self,
        source: FrozenEvidenceSource | None,
        store: AssessmentRepository,
        *,
        code_version=None,
        engine_version=ENGINE_VERSION,
    ):
        self.source = source
        self.store = store
        self.code_version = code_version
        self.engine_version = engine_version

    def assess(self, sha256: str, *, assessed_at_utc: str | None = None) -> dict:
        sha = validate_sha256(sha256)
        if self.source is None:
            raise ValueError("Assessment generation requires an evidence source")
        body = compose_assessment(
            sha,
            self.source.lookup(sha),
            code_version=self.code_version,
            engine_version=self.engine_version,
        )
        return self.store.append(
            body, assessed_at_utc=assessed_at_utc or datetime.now(UTC).isoformat()
        )

    def current(self, sha256: str) -> dict | None:
        return self.store.current(sha256)

    def history(self, sha256: str) -> list[dict]:
        return self.store.history(sha256)

    def by_id(self, assessment_id: str) -> dict | None:
        return self.store.by_id(assessment_id)

    def history_page(
        self, sha256: str, *, limit: int = 50, after_revision: int = 0
    ) -> dict:
        return self.store.history_page(
            sha256, limit=limit, after_revision=after_revision
        )

    def compare(self, before_id: str, after_id: str) -> dict:
        before = self.store.by_id(before_id)
        after = self.store.by_id(after_id)
        if before is None or after is None:
            raise ValueError("Both assessment revisions must exist")
        return compare_revisions(before, after)
