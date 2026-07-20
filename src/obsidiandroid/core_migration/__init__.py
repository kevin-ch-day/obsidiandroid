"""Fail-closed tools for the separately reviewed ObsidianDroid Core ledger.

These helpers are not wired into the analysis pipeline.  They require an
explicit target and injected Core-only connection factory so they cannot fall
back to the Erebus or Permission Intel application helpers.
"""

from .executor import CoreMigrationError, apply_migrations, discover_migrations
from .importer import execute_import_plan, validate_import_plan
from .mapping import CoreImportError, build_import_plan, source_mapping_rows
from .authorization import Phase2CImportAuthorization

__all__ = (
    "CoreImportError",
    "CoreMigrationError",
    "Phase2CImportAuthorization",
    "apply_migrations",
    "build_import_plan",
    "discover_migrations",
    "execute_import_plan",
    "validate_import_plan",
    "source_mapping_rows",
)
