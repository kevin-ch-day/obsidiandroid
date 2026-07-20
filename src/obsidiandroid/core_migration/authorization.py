"""Explicit, plan-bound authorization record for a future Phase 2C import.

This is an execution guard, not a substitute for the separately required human
approval.  It prevents a caller from treating a bare boolean as authority to
write the production Core schema.  The application pipeline does not create or
load this record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mapping import CoreImportError


PRODUCTION_CORE_SCHEMA = "obsidiandroid_core_prod"


@dataclass(frozen=True)
class Phase2CImportAuthorization:
    """A human-reviewed authorization bound to one deterministic import plan.

    A future operator must preserve the corresponding approval document and
    construct this record outside normal application execution.  No default,
    environment variable, or feature flag can manufacture production-import
    authority.
    """

    authorization_id: str
    approved_by: str
    target_database: str
    source_run_id: str
    plan_sha256: str

    def validate_for(self, *, target_database: str, plan: dict[str, Any]) -> None:
        """Fail closed unless this record names the exact production plan."""
        if not self.authorization_id.strip() or not self.approved_by.strip():
            raise CoreImportError("Phase 2C authorization requires nonempty approval identity fields")
        if self.target_database != PRODUCTION_CORE_SCHEMA or target_database != PRODUCTION_CORE_SCHEMA:
            raise CoreImportError("Phase 2C authorization is valid only for the production Core schema")
        if self.source_run_id != str(plan.get("source_run_id") or ""):
            raise CoreImportError("Phase 2C authorization run identity does not match the import plan")
        if self.plan_sha256 != str(plan.get("plan_sha256") or ""):
            raise CoreImportError("Phase 2C authorization hash does not match the import plan")
