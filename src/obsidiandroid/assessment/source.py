"""Bounded SELECT-only extraction of assessment evidence on one MariaDB server.

The caller supplies an already server-enforced read-only snapshot connection.
No credentials, provider requests, repairs or production writers live here.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from datetime import date, datetime

from .composition import digest, ordered, validate_sha256

EREBUS = "erebus_threat_intel_prod"
PERMISSIONS = "android_permission_intel"
SCYTALE = "scytaledroid_core_prod"


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def retained_permission_tokens(value) -> list[str]:
    """Read only the retained permission fields, not source descriptions/labels."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    tokens = set()

    def visit(item):
        if isinstance(item, dict):
            tokens.update(
                k
                for k in item
                if isinstance(k, str) and "." in k and not any(c.isspace() for c in k)
            )
        elif isinstance(item, list):
            for child in item:
                if (
                    isinstance(child, str)
                    and "." in child
                    and not any(c.isspace() for c in child)
                ):
                    tokens.add(child)
                elif isinstance(child, (dict, list)):
                    visit(child)

    visit(value)
    return sorted(tokens)


class ReadOnlyEvidenceReader:
    """Collect a bounded source slice with a complete replayable query log."""

    def __init__(self, connection):
        self.connection = connection
        self.queries = []
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@tx_read_only AS read_only")
            if cursor.fetchone()["read_only"] != 1:
                raise ValueError(
                    "Assessment extraction requires server-enforced read-only transactions"
                )

    def read(self, name, sql, params=()):
        if (
            not sql.lstrip().upper().startswith("SELECT ")
            or ";" in sql
            or re.search(
                r"\b(INTO|FOR\s+UPDATE|LOCK|SLEEP|BENCHMARK|GET_LOCK)\b", sql, re.I
            )
        ):
            raise ValueError("Only single SELECT statements are allowed")
        with self.connection.cursor() as cursor:
            rendered = cursor.mogrify(sql, params)
            self.queries.append({"name": name, "sql": rendered})
            cursor.execute(sql, params)
            return json_value(list(cursor.fetchall()))

    def collect(self, sha256: str) -> dict:
        sha = validate_sha256(sha256)
        result = {
            "sha256": sha,
            "errors": [],
            "source_snapshots": {
                "erebus": {"catalog": EREBUS, "snapshot_kind": "frozen_row_projection"},
                "permission_intel": {"catalog": PERMISSIONS},
                "scytale": {"catalog": SCYTALE, "join": "exact_sha256_only"},
                "query_contract": "operational-read-v1",
            },
        }

        def get(name, sql, params=()):
            try:
                return self.read(sha + ":" + name, sql, params)
            except Exception as exc:
                result["errors"].append(name + ":" + type(exc).__name__)
                return []

        result["catalog"] = get(
            "catalog",
            f"SELECT sample_id,sha256,platform,artifact_type,android_package_name,classification_primary,classification_subtype,family_label,android_permission_count,vt_first_submission_at_utc,vt_first_seen_itw_date,record_created_at_utc,record_updated_at_utc,source_batch_label FROM {EREBUS}.malware_sample_catalog WHERE sha256=%s",
            (sha,),
        )
        result["lookup_status"] = "found" if result["catalog"] else "not_found"
        if len(result["catalog"]) != 1:
            return result
        sid = result["catalog"][0]["sample_id"]
        result["taxonomy"] = get(
            "taxonomy",
            f"SELECT type_id,type_name,type_slug,parent_type_id,is_active,updated_at_utc FROM {EREBUS}.android_malware_type ORDER BY type_id",
        )
        mappings = get(
            "mappings",
            f"SELECT mapping_id,sample_id,family_id,matched_alias_id,observed_value,observed_source_kind,mapping_method,confidence,trust_tier,review_status,updated_at_utc FROM {EREBUS}.malware_sample_family_mapping WHERE sample_id=%s ORDER BY mapping_id",
            (sid,),
        )
        result["authority"] = get(
            "authority",
            f"SELECT authority_id,sample_id,governed_family_id,governed_family_slug,governed_family_name,governed_type_id,governed_type_slug,authority_source_system,authority_source_table,authority_resolution_method,authority_version,review_status,is_active,resolved_at_utc,updated_at_utc FROM {EREBUS}.malware_family_authority_fact WHERE sample_id=%s AND is_active=1 ORDER BY authority_id",
            (sid,),
        )
        family_ids = sorted(
            {m["family_id"] for m in mappings}
            | {
                a["governed_family_id"]
                for a in result["authority"]
                if a["governed_family_id"] is not None
            }
        )
        families = {}
        result["family_conflicts"] = []
        result["aliases"] = []
        for fid in family_ids:
            rows = get(
                "family",
                f"SELECT family_id,family_slug,family_name,primary_type_id,family_status,is_active,ecosystem_class,normalization_target_family_id,updated_at_utc FROM {EREBUS}.android_malware_family WHERE family_id=%s",
                (fid,),
            )
            if rows:
                families[fid] = rows[0]
                result["aliases"].extend(
                    get(
                        "aliases",
                        f"SELECT alias_id,alias_token,canonical_family_slug,alias_kind,source_system,source_reference,confidence_score,is_active,updated_at_utc FROM {EREBUS}.malware_family_alias_fact WHERE canonical_family_slug=%s AND is_active=1 ORDER BY alias_id",
                        (rows[0]["family_slug"],),
                    )
                )
            result["family_conflicts"].extend(
                get(
                    "family_conflicts",
                    f"SELECT c.conflict_case_id,c.family_entity_id,e.legacy_family_id,c.conflict_kind,c.conflict_state,c.opened_at_utc,c.resolved_at_utc FROM {EREBUS}.android_family_conflict_case_v2 c JOIN {EREBUS}.android_family_entity_v2 e ON e.family_entity_id=c.family_entity_id WHERE e.legacy_family_id=%s ORDER BY c.conflict_case_id",
                    (fid,),
                )
            )
        result["mappings"] = [
            {**m, "family": families.get(m["family_id"], {})} for m in mappings
        ]
        result["families"] = list(families.values())
        result["av_scan"] = get(
            "av_scan",
            f"SELECT sample_id,sha256,vt_last_analysis_date,vt_malicious_count,vt_suspicious_count,vt_undetected_count,vt_harmless_count,vt_suggested_threat_label,updated_at FROM {EREBUS}.virustotal_sample_scan_summary WHERE sample_id=%s AND sha256=%s",
            (sid, sha),
        )
        result["av_verdict"] = get(
            "av_verdict",
            f"SELECT sample_id,sha256,vt_last_analysis_date,vt_malicious_count,vt_suspicious_count,vt_harmless_count,vt_undetected_count,vt_total_engines,raw_detection_ratio,confidence_score,confidence_bucket,recommended_action,score_version,record_updated_at_utc FROM {EREBUS}.vt_sample_verdict_confidence_current WHERE sample_id=%s AND sha256=%s",
            (sid, sha),
        )
        result["av_review"] = get(
            "av_review",
            f"SELECT sample_id,sha256,confidence_bucket,recommended_action,review_reason FROM {EREBUS}.v_vt_false_positive_review_candidates_effective WHERE sample_id=%s AND sha256=%s",
            (sid, sha),
        )
        result["av_labels"] = get(
            "av_labels",
            f"SELECT evidence_id,sample_id,vendor_key,raw_vendor_label,parsed_family_token,parsed_type_token,parser_name,parser_version,source_report_date_utc,is_active FROM {EREBUS}.malware_family_label_evidence WHERE sample_id=%s AND is_active=1 ORDER BY evidence_id",
            (sid,),
        )
        before_pi = len(result["errors"])
        obs = get(
            "permission_observations",
            f"SELECT obs_id,sample_id,permission_string,source,classification,observed_at_utc,run_id FROM {PERMISSIONS}.android_permission_obs_sample WHERE sample_id=%s ORDER BY obs_id",
            (sid,),
        )
        releases = get(
            "permission_release",
            f"SELECT catalog_release_id,semantic_catalog_digest,source_set_digest,release_status,is_current_accepted,exhaustive_scope,scope_completeness_statement,platform_release_coverage,accepted_at_utc FROM {PERMISSIONS}.api_catalog_content_release WHERE is_current_accepted=1 ORDER BY catalog_release_id",
        )
        semantics = []
        for token in sorted({o["permission_string"] for o in obs}):
            semantics.extend(
                get(
                    "permission_semantics",
                    f"""SELECT r.catalog_release_id,i.permission_id,i.canonical_permission,i.authority_class,i.identity_status,
                d.declaration_revision_id,d.source_snapshot_id,d.feature_dependency,d.lifecycle,d.platform_release_id,
                s.acceptance_status,s.source_status,s.raw_sha256 AS source_sha256,
                p.compatibility_protection_expression,
                (SELECT COUNT(*) FROM {PERMISSIONS}.api_permission_declaration_conflict c WHERE c.permission_id=i.permission_id AND c.resolution_status<>'RESOLVED') AS unresolved_conflict_count
                FROM {PERMISSIONS}.api_permission_identity i
                JOIN {PERMISSIONS}.api_catalog_release_permission r ON r.permission_id=i.permission_id
                JOIN {PERMISSIONS}.api_catalog_content_release cr ON cr.catalog_release_id=r.catalog_release_id AND cr.is_current_accepted=1
                LEFT JOIN {PERMISSIONS}.api_permission_declaration_revision d ON d.declaration_revision_id=r.selected_declaration_revision_id
                LEFT JOIN {PERMISSIONS}.api_upstream_source_snapshot s ON s.source_snapshot_id=d.source_snapshot_id
                LEFT JOIN {PERMISSIONS}.android_permission_v1_current_protection p ON p.catalog_release_id=r.catalog_release_id AND p.declaration_revision_id=d.declaration_revision_id
                WHERE BINARY i.canonical_permission=BINARY %s ORDER BY i.permission_id,d.declaration_revision_id""",
                    (token,),
                )
            )
        retained = get(
            "retained_permissions",
            f"""SELECT b.bounded_result_id,b.sample_id,b.sha256,b.event_id,b.payload_hash,b.required_persistence_state,
                JSON_UNQUOTE(JSON_EXTRACT(p.payload_json,'$.data.id')) AS report_sha256,
                JSON_EXTRACT(p.payload_json,'$.data.attributes.androguard.permission_details','$.data.attributes.androguard.PermissionDetails','$.data.attributes.androguard.permissions','$.data.attributes.androguard.Permissions') AS permission_fields_json,
                p.first_seen_at_utc,p.last_seen_at_utc
                FROM {EREBUS}.virustotal_bounded_result_evidence b
                JOIN {EREBUS}.virustotal_file_report_payload_store p ON p.payload_hash=b.payload_hash
                WHERE b.sample_id=%s AND b.sha256=%s AND b.http_status=200 ORDER BY b.bounded_result_id""",
            (sid, sha),
        )
        for row in retained:
            row["tokens"] = retained_permission_tokens(
                row.pop("permission_fields_json")
            )
        result["permissions"] = {
            "observations": obs,
            "releases": releases,
            "semantics": semantics,
            "retained": retained,
            "availability": "error"
            if len(result["errors"]) > before_pi
            else "available"
            if obs
            else "unavailable",
        }
        before_scytale = len(result["errors"])
        result["scytale"] = {
            "registry": get(
                "scytale_registry",
                f"SELECT apk_id,sha256,package_name,version_code,version_name,is_split_member,harvested_at FROM {SCYTALE}.android_apk_repository WHERE sha256=%s ORDER BY apk_id",
                (sha,),
            ),
            "static": get(
                "scytale_static",
                f"SELECT id,base_apk_sha256,artifact_set_hash,artifact_set_hash_version,status,identity_valid,run_class FROM {SCYTALE}.static_analysis_runs WHERE base_apk_sha256=%s ORDER BY id",
                (sha,),
            ),
            "dynamic": get(
                "scytale_dynamic",
                f"SELECT dynamic_run_id,package_name,base_apk_sha256,artifact_set_hash,artifact_set_hash_version,status,started_at_utc FROM {SCYTALE}.dynamic_sessions WHERE base_apk_sha256=%s ORDER BY dynamic_run_id",
                (sha,),
            ),
        }
        result["scytale"]["availability"] = (
            "error"
            if len(result["errors"]) > before_scytale
            else "available"
            if any(result["scytale"].values())
            else "unavailable"
        )
        result["source_snapshots"]["erebus"]["row_projection_sha256"] = digest(
            ordered(
                {
                    k: result[k]
                    for k in (
                        "catalog",
                        "mappings",
                        "authority",
                        "av_scan",
                        "av_verdict",
                    )
                }
            )
        )
        result["source_snapshots"]["permission_intel"]["row_projection_sha256"] = (
            digest(ordered(result["permissions"]))
        )
        result["source_snapshots"]["scytale"]["row_projection_sha256"] = digest(
            ordered(result["scytale"])
        )
        return ordered(result)
