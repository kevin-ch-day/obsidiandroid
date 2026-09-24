"""Transactional native analysis service. No upstream or assessment writes."""

from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, UTC
import json
from pathlib import Path
import re
import uuid
from .contract import (
    VERSION,
    canonical,
    digest,
    validate_spec,
    reject_secrets,
    validate_result,
    artifact,
)

TABLES = (
    "core_run_sample",
    "split_ledger",
    "feature_contract",
    "model_execution",
    "model_metric",
    "prediction",
    "label_contract",
    "confusion_cell",
    "core_artifact",
)


class AnalysisStore:
    def __init__(self, connection_factory, *, database, allow_production=False):
        if not re.fullmatch(
            r"obsidiandroid_core_persistence_test_\d{8}(?:_[a-z0-9]+)?", database
        ) and not (database == "obsidiandroid_core_prod" and allow_production):
            raise ValueError("Explicit analytical database target required")
        self.factory = connection_factory
        self.database = database

    @contextmanager
    def transaction(self, read_only=False):
        c = self.factory()
        c.autocommit = False
        try:
            with c.cursor() as q:
                q.execute("SELECT DATABASE()")
                assert q.fetchone()[0] == self.database
                q.execute("SET time_zone='+00:00'")
                if read_only:
                    q.execute("SET SESSION TRANSACTION READ ONLY")
            yield c
            if not read_only:
                c.commit()
        finally:
            c.rollback()
            c.close()

    def begin_run(self, spec, *, run_id=None):
        validate_spec(spec)
        rid = run_id or str(uuid.uuid4())
        profile = digest({"profile": spec["profile"]})
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.transaction() as c, c.cursor() as q:
            q.execute(
                "SELECT profile_id FROM core_profile WHERE profile_id=%s", (profile,)
            )
            if not q.fetchone():
                q.execute(
                    "INSERT INTO core_profile(profile_id,profile_name,profile_hash,profile_contract_json,created_at_utc) VALUES(%s,%s,%s,%s,%s)",
                    (
                        profile,
                        spec["profile"],
                        profile,
                        canonical({"profile": spec["profile"]}),
                        now,
                    ),
                )
            q.execute(
                "INSERT INTO core_source_snapshot(source_catalogs_json,source_query_contract_hash,cohort_checksum,extracted_at_utc,snapshot_status,notes) VALUES(%s,%s,%s,%s,%s,%s)",
                (
                    canonical(list(spec["source_digests"])),
                    digest(spec["source_digests"]),
                    spec.get("cohort_digest"),
                    datetime.fromisoformat(
                        spec["evidence_cutoff"].replace("Z", "+00:00")
                    ).replace(tzinfo=None),
                    "observed",
                    canonical(spec["source_digests"]),
                ),
            )
            snapshot = q.lastrowid
            q.execute(
                "SELECT migration_version,migration_checksum FROM core_schema_migration ORDER BY migration_version"
            )
            schema_receipts = q.fetchall()
            q.execute(
                "INSERT INTO core_run(run_id,profile_id,source_snapshot_id,run_kind,application_commit,configuration_hash,run_started_at_utc,run_status,scope_kind,publication_applicability,evidence_completeness_status,metadata_json,imported_at_utc,analysis_contract_version) VALUES(%s,%s,%s,'snapshot_backed',%s,%s,%s,'running','analytical','exploratory','incomplete',%s,%s,%s)",
                (
                    rid,
                    profile,
                    snapshot,
                    spec["code"]["git_commit"],
                    digest(spec),
                    now,
                    canonical({"spec": spec, "schema_receipts": schema_receipts}),
                    now,
                    VERSION,
                ),
            )
        return rid

    def fail_run(
        self,
        run_id,
        *,
        stage,
        error_type="AnalysisFailure",
        cancelled=False,
        context=None,
    ):
        # Only codes, never exception messages or traceback/local variables.
        if not re.fullmatch(r"[A-Za-z0-9_]{1,100}", error_type) or not re.fullmatch(
            r"[A-Za-z0-9_]{1,64}", stage
        ):
            raise ValueError("Sanitized failure identifiers required")
        if context is not None:
            reject_secrets(context)
            canonical(context)
        with self.transaction() as c, c.cursor() as q:
            q.execute(
                "SELECT run_status,metadata_json FROM core_run WHERE run_id=%s AND analysis_contract_version=%s FOR UPDATE",
                (run_id, VERSION),
            )
            row = q.fetchone()
            if not row or row[0] != "running":
                raise ValueError("Run is not running")
            meta = json.loads(row[1])
            meta["failure"] = {"stage": stage, "error_type": error_type}
            if context is not None:
                meta["partial_evidence"] = context
            q.execute(
                "UPDATE core_run SET run_status=%s,run_completed_at_utc=UTC_TIMESTAMP(6),metadata_json=%s WHERE run_id=%s",
                ("cancelled" if cancelled else "failed", canonical(meta), run_id),
            )

    def finalize_run(self, run_id, result, *, artifact_root):
        with self.transaction() as c, c.cursor(dictionary=True) as q:
            q.execute(
                "SELECT * FROM core_run WHERE run_id=%s AND analysis_contract_version=%s FOR UPDATE",
                (run_id, VERSION),
            )
            run = q.fetchone()
            if not run:
                raise ValueError("Unknown analytical run")
            spec = json.loads(run["metadata_json"])["spec"]
            if "resolved_spec" in result:
                resolved = result["resolved_spec"]
                if any(
                    resolved[k] != spec[k]
                    for k in (
                        "profile",
                        "mode",
                        "code",
                        "evidence_cutoff",
                        "label_authority",
                        "cohort_id",
                    )
                ):
                    raise ValueError("Planned run identity changed")
                spec = resolved
            fingerprint = validate_result(spec, result)
            result_digest = digest(result)
            if run["run_status"] == "completed":
                if (
                    json.loads(run["metadata_json"]).get("result_digest")
                    != result_digest
                ):
                    raise ValueError("Completed result differs")
                return {
                    "run_id": run_id,
                    "status": "EXACT_REPLAY",
                    "fingerprint": fingerprint,
                }
            if run["run_status"] != "running":
                raise ValueError("Terminal run cannot be finalized")
            refs = result["artifacts"]
            kinds = [r["kind"] for r in refs]
            if len(set(kinds)) != len(kinds):
                raise ValueError("Duplicate artifact kind")
            for r in refs:
                if (
                    artifact(
                        artifact_root, r["path"], kind=r["kind"], required=r["required"]
                    )
                    != r
                ):
                    raise ValueError("Artifact changed")
            for member in result["members"]:
                role = member["role"]
                included = "excluded" if role == "excluded" else "aligned"
                split = (
                    role
                    if role in {"train", "test", "validation", "excluded"}
                    else "not_assigned"
                )
                q.execute(
                    "INSERT INTO core_run_sample(run_id,sample_key,sha256,source_sample_id,source_sample_namespace,observed_family,observed_type,inclusion_role,supervised_status,split_status,label_authority_state,evidence_state,record_checksum,source_record_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        run_id,
                        member["sha256"],
                        member["sha256"],
                        member.get(
                            "source_sample_id",
                            member.get("artifact_id")
                            if isinstance(member.get("artifact_id"), int)
                            else None,
                        ),
                        "erebus_sample_id",
                        None,
                        None,
                        included,
                        "eligible" if role != "excluded" else "ineligible",
                        split,
                        "unknown",
                        "snapshot_backed",
                        digest(member),
                        digest(member),
                    ),
                )
            splits_written = set()
            features_written = set()
            for model in result["models"]:
                feature_id = digest(
                    {"run": run_id, "features": model["feature_schema"]}
                )
                if feature_id not in features_written:
                    q.execute(
                        "INSERT INTO feature_contract(feature_contract_id,run_id,contract_name,modality,ordered_column_hash,column_count,leakage_assessment,contract_json,created_at_utc) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                        (
                            feature_id,
                            run_id,
                            "features_" + digest(model["feature_schema"])[:24],
                            "static",
                            digest(model["feature_schema"]),
                            len(model["feature_schema"]),
                            "not_assessed",
                            canonical(
                                {
                                    "columns": model["feature_schema"],
                                    "source_digests": spec["source_digests"],
                                }
                            ),
                        ),
                    )
                    features_written.add(feature_id)
                mid = digest({"run": run_id, "model": model["key"]})
                split = model["split_contract"]
                split_hash = digest(split)
                if split_hash not in splits_written:
                    for sha, role in split["members"].items():
                        q.execute(
                            "INSERT INTO split_ledger(run_id,split_contract_hash,sample_key,split_name,label_value,fold_number) VALUES(%s,%s,%s,%s,%s,%s)",
                            (
                                run_id,
                                split_hash,
                                sha,
                                role,
                                split.get("labels", {}).get(sha),
                                split.get("fold", 0),
                            ),
                        )
                    splits_written.add(split_hash)
                modelmeta = {
                    k: v
                    for k, v in model.items()
                    if k not in {"predictions", "metrics", "confusion"}
                }
                q.execute(
                    "INSERT INTO model_execution(model_execution_id,run_id,model_name,evaluation_scope,feature_contract_id,split_contract_hash,estimator_config_hash,model_artifact_role,promoted_flag,execution_status,created_at_utc,execution_metadata_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,0,%s,UTC_TIMESTAMP(6),%s)",
                    (
                        mid,
                        run_id,
                        model["key"],
                        model["dimension"],
                        feature_id,
                        split_hash,
                        digest(model["parameters"]),
                        model.get("artifact"),
                        "completed",
                        canonical(modelmeta),
                    ),
                )
                labels = sorted(
                    {
                        p["actual"]
                        for p in model["predictions"]
                        if p.get("actual") is not None
                    }
                    | {
                        p["predicted"]
                        for p in model["predictions"]
                        if p.get("predicted") is not None
                    }
                )
                lid = digest({"run": run_id, "model": model["key"], "labels": labels})
                q.execute(
                    "INSERT INTO label_contract(label_contract_id,run_id,label_target,label_universe_hash,class_count,authority_state,created_at_utc) VALUES(%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                    (lid, run_id, model["key"], digest(labels), len(labels), "unknown"),
                )
                for p in model["predictions"]:
                    q.execute(
                        "INSERT INTO prediction(model_execution_id,sample_key,split_name,true_label,predicted_label,confidence,prediction_rank,prediction_status,prediction_details_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            mid,
                            p["sha256"],
                            split["members"][p["sha256"]],
                            p.get("actual"),
                            p.get("predicted"),
                            p.get("score"),
                            p.get("rank", 1),
                            p["status"],
                            canonical(p),
                        ),
                    )
                for name, value in model["metrics"].items():
                    numeric = value if isinstance(value, (int, float)) else None
                    q.execute(
                        "INSERT INTO model_metric(model_execution_id,metric_name,metric_value,metric_universe_hash,metric_details_json) VALUES(%s,%s,%s,%s,%s)",
                        (mid, name, numeric, split_hash, canonical(value)),
                    )
                for cell in model["confusion"]:
                    q.execute(
                        "INSERT INTO confusion_cell(model_execution_id,label_contract_id,split_name,true_label,predicted_label,sample_count) VALUES(%s,%s,%s,%s,%s,%s)",
                        (
                            mid,
                            lid,
                            "test",
                            cell["true"],
                            cell["predicted"],
                            cell["count"],
                        ),
                    )
            for r in refs:
                q.execute(
                    "INSERT INTO core_artifact(run_id,artifact_role,immutable_relative_path,sha256,expected_sha256,observed_sha256,byte_size,availability_status,hash_validation_status,retention_status,created_at_utc,imported_at_utc,required_flag) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),%s)",
                    (
                        run_id,
                        r["kind"],
                        r["path"],
                        r["sha256"],
                        r["sha256"],
                        r["sha256"],
                        r["byte_size"],
                        "present",
                        "validated",
                        "retained",
                        int(r["required"]),
                    ),
                )
            q.execute(
                "SELECT run_id FROM core_run WHERE analysis_fingerprint=%s AND run_status='completed' ORDER BY run_completed_at_utc,run_id LIMIT 1",
                (fingerprint,),
            )
            prior = q.fetchone()
            metadata = {
                "schema_receipts": json.loads(run["metadata_json"]).get(
                    "schema_receipts", []
                ),
                "spec": spec,
                "result_digest": result_digest,
                "members": result["members"],
                "artifact_root": str(Path(artifact_root).absolute()),
                "sample_count": len(result["members"]),
                "model_count": len(result["models"]),
                "counts_by_role": {
                    role: sum(r["role"] == role for r in result["members"])
                    for role in (
                        "train",
                        "test",
                        "validation",
                        "inference_only",
                        "excluded",
                    )
                },
            }
            snapshot_id = run["source_snapshot_id"]
            if "resolved_spec" in result:
                q.execute(
                    "INSERT INTO core_source_snapshot(source_catalogs_json,source_query_contract_hash,cohort_checksum,extracted_at_utc,snapshot_status,notes) VALUES(%s,%s,%s,%s,'observed',%s)",
                    (
                        canonical(list(spec["source_digests"])),
                        digest(spec["source_digests"]),
                        spec.get("cohort_digest"),
                        datetime.fromisoformat(
                            spec["evidence_cutoff"].replace("Z", "+00:00")
                        ).replace(tzinfo=None),
                        canonical(spec["source_digests"]),
                    ),
                )
                snapshot_id = q.lastrowid
            q.execute(
                "UPDATE core_run SET source_snapshot_id=%s,configuration_hash=%s,run_status='completed',run_completed_at_utc=UTC_TIMESTAMP(6),analysis_fingerprint=%s,replay_of_run_id=%s,evidence_completeness_status='snapshot_backed',artifact_count=%s,metadata_json=%s WHERE run_id=%s",
                (
                    snapshot_id,
                    digest(spec),
                    fingerprint,
                    prior["run_id"] if prior else None,
                    len(refs),
                    canonical(metadata),
                    run_id,
                ),
            )
        return {"run_id": run_id, "status": "SUCCEEDED", "fingerprint": fingerprint}

    def history(self, limit=20):
        if not 1 <= limit <= 200:
            raise ValueError("History limit1..200")
        with self.transaction(True) as c, c.cursor(dictionary=True) as q:
            q.execute(
                "SELECT run_id,run_status,run_started_at_utc,run_completed_at_utc,analysis_fingerprint,replay_of_run_id,metadata_json FROM core_run WHERE analysis_contract_version=%s ORDER BY run_started_at_utc DESC,run_id LIMIT %s",
                (VERSION, limit),
            )
            return q.fetchall()

    def show(self, run_id):
        with self.transaction(True) as c, c.cursor(dictionary=True) as q:
            q.execute(
                "SELECT * FROM core_run WHERE run_id=%s AND analysis_contract_version=%s",
                (run_id, VERSION),
            )
            run = q.fetchone()
            if not run:
                raise ValueError("Unknown analytical run")
            result = {"run": run}
            for table in TABLES:
                if table in {"prediction", "model_metric", "confusion_cell"}:
                    sql = f"SELECT c.* FROM {table} c JOIN model_execution m ON m.model_execution_id=c.model_execution_id WHERE m.run_id=%s"
                else:
                    sql = f"SELECT * FROM {table} WHERE run_id=%s"
                q.execute(sql, (run_id,))
                result[table] = q.fetchall()
            return result
