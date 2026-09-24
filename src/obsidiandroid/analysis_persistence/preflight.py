"""Read-only persistence planning: validate profile, schema and actor privileges."""

from pathlib import Path
import hashlib
from .contract import digest


def build_plan(profile_ref, store, *, persist=True):
    from obsidiandroid.cli.profile_manager import load_profile
    from obsidiandroid.core_migration.migration_checksums import MIGRATION_CHECKSUMS

    profile = load_profile(profile_ref)
    path = Path(profile["__profile_path"])
    with store.transaction(True) as c, c.cursor() as q:
        q.execute("SELECT CURRENT_USER()")
        actor = q.fetchone()[0]
        q.execute("SHOW COLUMNS FROM core_schema_migration")
        columns = [row[0] for row in q.fetchall()]
        q.execute("SELECT * FROM core_schema_migration")
        receipts = [dict(zip(columns, row)) for row in q.fetchall()]
        q.execute("SHOW GRANTS")
        grants = [row[0].split(" IDENTIFIED")[0] for row in q.fetchall()]
        # Read selected contract columns, no mutation or source-model work.
        for statement in (
            "SELECT analysis_contract_version,analysis_fingerprint FROM core_run LIMIT 0",
            "SELECT prediction_status,prediction_details_json FROM prediction LIMIT 0",
            "SELECT execution_metadata_json FROM model_execution LIMIT 0",
            "SELECT fold_number FROM split_ledger LIMIT 0",
            "SELECT required_flag FROM core_artifact LIMIT 0",
        ):
            q.execute(statement)
            q.fetchall()
    migration = next(
        (
            r
            for r in receipts
            if str(r.get("migration_version", r.get("version"))) == "0007"
        ),
        None,
    )
    if (
        migration is None
        or migration.get("migration_checksum") != MIGRATION_CHECKSUMS["0007"]
    ):
        raise ValueError("Analytical migration receipt absent")
    profile_contract = {k: v for k, v in profile.items() if not k.startswith("__")}
    return {
        "profile": profile_ref,
        "profile_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "resolved_profile_digest": digest(profile_contract),
        "models": profile["model_list"],
        "database": store.database,
        "actor": actor,
        "migration_receipt": migration,
        "schema_columns_checked": True,
        "grants_observed": grants,
        "mode": "persisted" if persist else "read_only",
        "execution_started": False,
        "assessment_writes": False,
        "provider_requests": False,
        "status": "PLAN_VALIDATED_RUNTIME_INPUTS_PENDING",
        "remaining_runtime_gates": [
            "source connectivity and exact SHA cohort",
            "actual feature schemas and split labels",
            "all requested models captured",
            "required model artifact hashes",
            "atomic finalization",
        ],
        "membership_boundary": "Rows returned by the profile SQL loader, including subsequent Python exclusions",
    }
