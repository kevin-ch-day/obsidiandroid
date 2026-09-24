"""Regenerate scientific exports from normalized database records."""

import csv
import hashlib
import json
from pathlib import Path
from .contract import artifact


def verify_artifacts(data):
    """Check registered bytes without exporting files or loading model objects."""
    meta = json.loads(data["run"]["metadata_json"])
    root = meta.get("artifact_root")
    checks = []
    for row in data["core_artifact"]:
        status = "root_unavailable"
        if isinstance(root, str) and root and Path(root).is_absolute():
            try:
                observed = artifact(
                    root, row["immutable_relative_path"],
                    kind=row["artifact_role"], required=bool(row["required_flag"]),
                )
                status = (
                    "verified"
                    if observed["sha256"] == row["sha256"]
                    and observed["byte_size"] == row["byte_size"]
                    else "changed"
                )
            except (OSError, ValueError, TypeError):
                status = "missing_or_unsafe"
        checks.append({
            "kind": row["artifact_role"],
            "path": row["immutable_relative_path"],
            "status": status,
            "required": bool(row["required_flag"]),
        })
    return {
        "run_id": data["run"]["run_id"],
        "status": (
            "no_registered_artifacts" if not checks
            else "verified" if all(c["status"] == "verified" for c in checks)
            else "unverified_artifacts"
        ),
        "artifact_checks": checks,
    }


def export_run(store, run_id, destination):
    data = store.show(run_id)
    target = Path(destination)
    if target.exists():
        raise ValueError("Export destination must be new")
    target.mkdir(parents=True)
    (target / "run.json").write_text(
        json.dumps(data["run"], sort_keys=True, indent=2, default=str) + "\n"
    )
    for table, rows in data.items():
        if table == "run":
            continue
        with (target / (table + ".tsv")).open("w") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)
    verification = verify_artifacts(data)
    checks = verification["artifact_checks"]
    (target / "artifact_verification.json").write_text(
        json.dumps(checks, indent=2) + "\n"
    )
    (target / "checksums.sha256").write_text(
        "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
            for p in sorted(target.iterdir())
            if p.is_file()
        )
    )
    return {
        "run_id": run_id,
        "export": str(target),
        "artifact_checks": checks,
        "artifact_verification_status": verification["status"],
        "database_export_complete": True,
    }
