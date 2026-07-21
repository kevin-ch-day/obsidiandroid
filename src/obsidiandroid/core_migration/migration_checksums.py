"""Immutable Core migration checksums and Phase 2D table contracts."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


MIGRATION_CHECKSUMS = {
    "0001": "fd65d0106b50484da3ca802f8a2b98649f9bac06993989c5602f09d30c0badae",
    "0002": "076fefdc613e9f359f03c2156027009f0950df33b4e049cd501c523dcb4c9b21",
    "0003": "ffb09f7fe5c8b476384dac4587f1c69a7f24ca1807d4cbb5bba2a809c11707f2",
    "0004": "39d8ebfa55f9a4113ac2469b184504ff750cb7548f3a735df04d4f029e381942",
    "0005": "de649016c32e0bc52fc02557e3d871be914d950cfc62f5bb7afc46ed7e2527c1",
}

CORE_FOUNDATION_TABLES = (
    "core_schema_migration",
    "core_profile",
    "core_source_snapshot",
    "core_run",
    "core_run_sample",
    "core_artifact",
    "core_quality_finding",
)

CORE_RESULT_TABLES_FINAL = (
    "run_stage",
    "feature_contract",
    "split_ledger",
    "model_execution",
    "model_metric",
    "prediction",
    "experiment",
    "experiment_metric",
    "permission_measure",
    "label_contract",
    "label_assignment",
    "confusion_cell",
)

CORE_RESULT_TABLES_TEMPORARY = (
    "core_run_stage",
    "core_feature_contract",
    "core_split_ledger",
    "core_model_execution",
    "core_model_metric",
    "core_prediction",
    "core_experiment",
    "core_experiment_metric",
    "core_permission_measure",
    "core_label_contract",
    "core_label_assignment",
    "core_confusion_cell",
)

PARTIAL_0004_TABLES = (
    "core_label_contract",
    "core_label_assignment",
    "core_confusion_cell",
)

PHASE2C_FIXTURE_RUN_ID = "20260718T032717Z__a8cf01"
PHASE2C_FIXTURE_COUNTS = {
    "core_profile": 1,
    "core_source_snapshot": 1,
    "core_run": 1,
    "core_run_sample": 9716,
    "core_artifact": 57,
    "core_quality_finding": 0,
}

FAILED_PRODUCTION_RECEIPT_ID = "39b809e3ba7604f527a7f70e4ce988a63a93ed1ff69916b29e202f1727fb2ab5"
PRE_MIGRATION_BACKUP_SHA256 = "6fe86e7c08f63a7250e7224dcabbb417b92a45f019348d06186840b5df01f6e5"
REMEDIATION_EXECUTOR_ID = "obsidiandroid-core-results-ledger-remediator"
PRODUCTION_CORE = "obsidiandroid_core_prod"


def verify_repository_migration_checksums(migrations_dir: Path, versions: tuple[str, ...] | None = None) -> dict[str, str]:
    """Return file checksums after confirming they match the immutable contract."""
    selected = versions or tuple(sorted(MIGRATION_CHECKSUMS))
    observed: dict[str, str] = {}
    for version in selected:
        matches = sorted(migrations_dir.glob(f"{version}_*.sql"))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one migration file for {version}, found {len(matches)}")
        digest = sha256(matches[0].read_bytes()).hexdigest()
        expected = MIGRATION_CHECKSUMS[version]
        if digest != expected:
            raise ValueError(f"Migration {version} checksum mismatch: file={digest} expected={expected}")
        observed[version] = digest
    return observed
