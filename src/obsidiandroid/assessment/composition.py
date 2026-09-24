"""Deterministic, field-level synthesis of frozen upstream evidence.

No classifier is trained or invoked. Source policy support is not ground truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from collections import defaultdict
from typing import Any

ENGINE_VERSION = "operational-evidence-v1.0"
CONTRACT_VERSION = "obsidiandroid.artifact-assessment.v1"


def validate_sha256(value: str) -> str:
    """Validate an exact artifact hash; never accept a path or partial hash."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("SHA-256 must contain exactly 64 hexadecimal characters")
    return value.lower()


def source_code_version() -> str:
    """Fingerprint the actual composer and reused permission interpretation code."""
    paths = sorted(Path(__file__).parent.glob("*.py"))
    paths.append(
        Path(__file__).parents[1] / "database" / "permission_current_interpretation.py"
    )
    return "source-sha256:" + digest(
        {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    )


def canonical_json(value: Any) -> str:
    """Serialize canonical JSON without non-finite or implementation-only values."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def ordered(value: Any) -> Any:
    """Canonicalize unordered source result sets for stable evidence fingerprints."""
    if isinstance(value, dict):
        return {k: ordered(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return sorted((ordered(v) for v in value), key=canonical_json)
    return value


def field(
    value=None,
    *,
    state="unresolved",
    refs=(),
    candidates=(),
    method="governed_evidence",
    support="insufficient_evidence",
    reason=None,
):
    return {
        "state": state,
        "value": value,
        "candidates": list(candidates),
        "method": method,
        "support": support,
        "evidence_refs": sorted(set(refs)),
        "reason": reason,
    }


def compose_assessment(
    sha256: str, evidence: dict, *, engine_version=ENGINE_VERSION, code_version=None
) -> dict:
    """Compose a revision-free assessment body from one exact-hash evidence slice.

    AssessmentService assigns immutable revision metadata and timestamps separately.
    """
    sha = validate_sha256(sha256)
    evidence = ordered(evidence)
    if evidence.get("sha256") != sha:
        raise ValueError("Evidence slice is not bound to the requested SHA-256")
    refs: dict[str, dict] = {}

    def ref(source, table, key, row):
        rid = f"{source}:{table}:{canonical_json(key)}"
        item = {"source": source, "table": table, "key": key, "row_sha256": digest(row)}
        if rid in refs and refs[rid] != item:
            raise ValueError("Conflicting source rows share an evidence identity")
        refs[rid] = item
        return rid

    errors = list(evidence.get("errors") or [])
    catalog = evidence.get("catalog") or []
    if len(catalog) == 1:
        sample_id = catalog[0]["sample_id"]
        for group in (
            "mappings",
            "authority",
            "av_scan",
            "av_verdict",
            "av_labels",
            "av_review",
        ):
            for row in evidence.get(group, []):
                if row.get("sample_id") != sample_id or (
                    row.get("sha256") is not None and row["sha256"] != sha
                ):
                    raise ValueError("Source evidence is bound to a different sample")
        for row in (evidence.get("permissions") or {}).get("observations", []):
            if row.get("sample_id") != sample_id or row.get("source") != "virustotal":
                raise ValueError(
                    "Permission observation source/sample binding is unsupported"
                )
    elif any(
        evidence.get(k)
        for k in (
            "mappings",
            "authority",
            "av_scan",
            "av_verdict",
            "av_labels",
            "av_review",
        )
    ) or (evidence.get("permissions") or {}).get("observations"):
        raise ValueError("Sample-bound evidence requires a unique catalog identity")
    artifact = {
        "sha256": sha,
        "platform": field(),
        "format": field(),
        "package_name": field(),
        "version": field(
            reason="No exact-build version evidence in this source contract"
        ),
    }
    conclusions = {k: field() for k in ("artifact_label", "type", "family", "variant")}
    reasons = []
    catalog_refs = []
    for row in catalog:
        if validate_sha256(row.get("sha256", "")) != sha:
            raise ValueError("Catalog row SHA does not match assessment target")
        catalog_refs.append(
            ref(
                "erebus", "malware_sample_catalog", {"sample_id": row["sample_id"]}, row
            )
        )
    identity_conflict = len(catalog) > 1
    sample = catalog[0] if len(catalog) == 1 else {}
    if not sample:
        reasons.append(
            "multiple_catalog_identities"
            if identity_conflict
            else evidence.get("lookup_status", "not_found")
        )
    for dest, key in (
        ("platform", "platform"),
        ("format", "artifact_type"),
        ("package_name", "android_package_name"),
    ):
        if sample.get(key):
            artifact[dest] = field(
                sample[key],
                state="supported",
                refs=catalog_refs,
                support="source_metadata",
            )

    # Preserve each accepted mapping, even when a dimension is inactive or under review.
    family_groups = defaultdict(lambda: {"refs": [], "rows": [], "eligible": True})
    type_groups = defaultdict(lambda: {"refs": [], "value": None, "support": set()})
    family_aliases = evidence.get("aliases") or []

    def add_type(type_id, row, reference, support):
        if type_id is None:
            return
        types = [
            t
            for t in evidence.get("taxonomy", [])
            if t.get("type_id") == type_id and t.get("is_active") == 1
        ]
        if len(types) != 1:
            return
        t = types[0]
        tref = ref("erebus", "android_malware_type", {"type_id": type_id}, t)
        group = type_groups[str(type_id)]
        group["value"] = {"id": type_id, "slug": t["type_slug"], "name": t["type_name"]}
        group["refs"].extend([reference, tref])
        group["support"].add(support)

    for m in evidence.get("mappings", []):
        if m.get("review_status") != "accepted":
            continue
        mr = ref(
            "erebus",
            "malware_sample_family_mapping",
            {"mapping_id": m["mapping_id"]},
            m,
        )
        fam = m.get("family") or {}
        if fam and fam.get("family_id") != m["family_id"]:
            raise ValueError("Family dimension does not match its mapping identity")
        fr = ref("erebus", "android_malware_family", {"family_id": m["family_id"]}, fam)
        group = family_groups[str(m["family_id"])]
        group["refs"].extend([mr, fr])
        group["rows"].append(fam)
        group["eligible"] &= bool(
            fam.get("is_active") == 1 and fam.get("family_status") == "active"
        )
        if group["eligible"]:
            add_type(fam.get("primary_type_id"), fam, fr, "governed_family_taxonomy")
    authority_refs = []
    for a in evidence.get("authority", []):
        ar = ref(
            "erebus",
            "malware_family_authority_fact",
            {"authority_id": a["authority_id"]},
            a,
        )
        authority_refs.append(ar)
        if a.get("is_active") == 1 and a.get("review_status") == "reviewed":
            fid = a.get("governed_family_id")
            if fid is not None:
                group = family_groups[str(fid)]
                group["refs"].append(ar)
                dimensions = [
                    f for f in evidence.get("families", []) if f.get("family_id") == fid
                ]
                group["eligible"] &= bool(
                    len(dimensions) == 1
                    and dimensions[0].get("is_active") == 1
                    and dimensions[0].get("family_status") == "active"
                )
                for dimension in dimensions:
                    group["refs"].append(
                        ref(
                            "erebus",
                            "android_malware_family",
                            {"family_id": fid},
                            dimension,
                        )
                    )
                    group["rows"].append(dimension)
                group["rows"].append(
                    {
                        "family_id": fid,
                        "family_slug": a.get("governed_family_slug"),
                        "family_name": a.get("governed_family_name"),
                    }
                )
            add_type(a.get("governed_type_id"), a, ar, "reviewed_authority")
    conflicts = evidence.get("family_conflicts") or []
    open_conflict_refs = []
    for c in conflicts:
        if c.get("conflict_state") != "resolved":
            open_conflict_refs.append(
                ref(
                    "erebus",
                    "android_family_conflict_case_v2",
                    {"conflict_case_id": c["conflict_case_id"]},
                    c,
                )
            )
    candidates = []
    for fid, group in sorted(family_groups.items()):
        values = {(r.get("family_slug"), r.get("family_name")) for r in group["rows"]}
        if len(values) != 1 or any(not slug or not name for slug, name in values):
            group["eligible"] = False
        slug, name = sorted(values, key=str)[0]
        aliases = []
        for alias in family_aliases:
            if (
                alias.get("is_active") == 1
                and alias.get("canonical_family_slug") == slug
            ):
                aliases.append(alias["alias_token"])
                group["refs"].append(
                    ref(
                        "erebus",
                        "malware_family_alias_fact",
                        {"alias_id": alias["alias_id"]},
                        alias,
                    )
                )
        candidates.append(
            {
                "id": int(fid),
                "slug": slug,
                "name": name,
                "aliases": sorted(set(aliases)),
                "eligible": group["eligible"],
                "evidence_refs": sorted(set(group["refs"])),
            }
        )
    famrefs = [r for c in candidates for r in c["evidence_refs"]] + open_conflict_refs
    if len(candidates) > 1 or open_conflict_refs:
        conclusions["family"] = field(
            state="conflict",
            candidates=candidates,
            refs=famrefs,
            support="conflicting_governed_evidence",
            reason="No explicit sample-level resolution of competing evidence",
        )
    elif candidates and candidates[0]["eligible"]:
        c = candidates[0]
        conclusions["family"] = field(
            {k: c[k] for k in ("id", "slug", "name", "aliases")},
            state="supported",
            refs=famrefs,
            support="governed_source_assignment",
        )
    else:
        conclusions["family"] = field(
            candidates=candidates,
            refs=famrefs,
            reason="No usable governed family assignment",
        )

    # Raw catalog type is a source assertion, never a new taxonomy or independent model label.
    raw_type = str(sample.get("classification_primary") or "").strip().casefold()
    if raw_type:
        for t in evidence.get("taxonomy", []):
            if raw_type in {
                str(t.get("type_slug", "")).casefold(),
                str(t.get("type_name", "")).casefold(),
            }:
                add_type(
                    t["type_id"], sample, catalog_refs[0], "catalog_type_assertion"
                )
    type_candidates = [
        {
            "value": g["value"],
            "evidence_refs": sorted(set(g["refs"])),
            "support": sorted(g["support"]),
        }
        for _, g in sorted(type_groups.items())
    ]
    typerefs = [r for t in type_candidates for r in t["evidence_refs"]]
    if len(type_candidates) == 1:
        t = type_candidates[0]
        conclusions["type"] = field(
            t["value"],
            state="supported",
            refs=typerefs,
            method="rule_derived",
            support="+".join(t["support"]),
        )
    elif type_candidates:
        conclusions["type"] = field(
            state="conflict",
            refs=typerefs,
            candidates=type_candidates,
            support="conflicting_source_types",
        )

    av_refs = []
    scan_rows = evidence.get("av_scan") or []
    for row in scan_rows:
        av_refs.append(
            ref(
                "erebus",
                "virustotal_sample_scan_summary",
                {"sample_id": row["sample_id"]},
                row,
            )
        )
    verdicts = evidence.get("av_verdict") or []
    high = False
    for v in verdicts:
        vr = ref(
            "erebus",
            "vt_sample_verdict_confidence_current",
            {"sample_id": v["sample_id"]},
            v,
        )
        av_refs.append(vr)
        # Exact existing source policy/version and contemporaneous scan counts only.
        agrees = bool(v.get("vt_last_analysis_date")) and any(
            all(
                s.get(k) == v.get(k)
                for k in (
                    "vt_last_analysis_date",
                    "vt_malicious_count",
                    "vt_suspicious_count",
                    "vt_harmless_count",
                    "vt_undetected_count",
                )
            )
            for s in scan_rows
        )
        high |= bool(
            agrees
            and v.get("score_version") == "vt_confidence_v1"
            and v.get("recommended_action") == "promote"
            and v.get("confidence_bucket") == "high"
            and (v.get("vt_malicious_count") or 0) > 0
        )
    android = (
        sample.get("platform") == "android" and sample.get("artifact_type") == "apk"
    )
    if android:
        conclusions["artifact_label"] = field(
            "ANDROID_MALWARE" if high else "ANDROID_APPLICATION",
            state="supported",
            refs=catalog_refs + (av_refs if high else []),
            method="rule_derived",
            support="erebus_high_av_policy" if high else "android_identity_only",
            reason="Source-supported assessment, not independently verified maliciousness; absence of AV support does not establish benignness",
        )
        reviews = evidence.get("av_review") or []
        if reviews:
            review_refs = [
                ref(
                    "erebus",
                    "v_vt_false_positive_review_candidates_effective",
                    {"sample_id": r["sample_id"]},
                    r,
                )
                for r in reviews
            ]
            av_refs.extend(review_refs)
            if high:
                conclusions["artifact_label"] = field(
                    state="conflict",
                    refs=catalog_refs + av_refs,
                    candidates=[
                        {"name": "ANDROID_MALWARE"},
                        {"name": "UPSTREAM_REVIEW_REQUIRED"},
                    ],
                    support="upstream_review_conflict",
                    reason="High AV policy coexists with an upstream false-positive review requirement",
                )
    elif sample:
        conclusions["artifact_label"] = field(
            "UNKNOWN",
            state="unsupported",
            refs=catalog_refs,
            reason="V1 supports Android APK catalog identities",
        )
    conclusions["variant"] = field(
        reason="No sample-bound governed variant source in V1; never inferred from family aliases or AV label suffixes"
    )

    permissions = evidence.get("permissions") or {}
    observations = permissions.get("observations") or []
    releases = permissions.get("releases") or []
    accepted = [
        r
        for r in releases
        if r.get("release_status") == "ACCEPTED" and r.get("is_current_accepted") == 1
    ]
    release = accepted[0] if len(accepted) == 1 else None
    release_ref = (
        ref(
            "permission_intel",
            "api_catalog_content_release",
            {"catalog_release_id": release["catalog_release_id"]},
            release,
        )
        if release
        else None
    )
    by_token = defaultdict(list)
    for row in permissions.get("semantics", []):
        by_token[row.get("canonical_permission")].append(row)
    tokens = []
    for o in observations:
        ore = ref(
            "permission_intel",
            "android_permission_obs_sample",
            {"obs_id": o["obs_id"]},
            o,
        )
        token = o["permission_string"]
        rows = by_token.get(token, [])  # exact case and whitespace: no alias promotion
        eligible = [
            r
            for r in rows
            if release
            and r.get("catalog_release_id") == release["catalog_release_id"]
            and r.get("identity_status") == "ACCEPTED"
            and r.get("acceptance_status") == "ACCEPTED"
            and r.get("source_status") == "AVAILABLE"
            and r.get("declaration_revision_id")
            and not r.get("unresolved_conflict_count")
        ]
        if len(eligible) == 1:
            s = eligible[0]
            from obsidiandroid.database.permission_current_interpretation import (
                interpret_permission_evidence,
            )

            interpretation = interpret_permission_evidence(token=token, identity=s)
            sr = ref(
                "permission_intel",
                "api_permission_declaration_revision",
                {"declaration_revision_id": s["declaration_revision_id"]},
                s,
            )
            tokens.append(
                {
                    "token": token,
                    "state": "resolved",
                    "authority_class": s.get("authority_class"),
                    "protection": interpretation.protection_result,
                    "feature_dependency": interpretation.feature_dependency,
                    "interpretation": asdict(interpretation),
                    "evidence_refs": [ore, sr, release_ref],
                }
            )
        else:
            tokens.append(
                {
                    "token": token,
                    "state": "unresolved",
                    "authority_class": None,
                    "protection": None,
                    "feature_dependency": None,
                    "evidence_refs": [ore],
                }
            )
    retained = permissions.get("retained") or []
    retained_refs = [
        ref(
            "erebus",
            "virustotal_bounded_result_evidence",
            {"bounded_result_id": r["bounded_result_id"]},
            r,
        )
        for r in retained
    ]
    raw_tokens = set()
    for r in retained:
        if (
            r.get("sha256") != sha
            or r.get("report_sha256") != sha
            or r.get("sample_id") != sample.get("sample_id")
        ):
            raise ValueError(
                "Retained report is not bound to the requested sample and SHA"
            )
        if r.get("sha256") == sha and r.get("report_sha256") == sha:
            raw_tokens.update(r.get("tokens") or [])
    missing_tokens = sorted(raw_tokens - {o["permission_string"] for o in observations})
    permission_result = {
        "availability": permissions.get("availability", "unavailable"),
        "semantic_release": release,
        "release_ref": release_ref,
        "observed_token_count": len(tokens) if observations else None,
        "resolved_count": sum(t["state"] == "resolved" for t in tokens)
        if observations
        else None,
        "unresolved_count": sum(t["state"] == "unresolved" for t in tokens)
        if observations
        else None,
        "tokens": tokens,
        "retained_tokens_missing_downstream": missing_tokens,
        "retained_evidence_refs": retained_refs,
        "completeness": "not_established",
        "interpretation_scope": "current accepted release; not historical API reconstruction or runtime behavior",
    }
    scytale = dict(evidence.get("scytale") or {"availability": "unavailable"})
    scytale_refs = []
    tables = {
        "static": ("static_analysis_runs", "id"),
        "dynamic": ("dynamic_sessions", "dynamic_run_id"),
        "registry": ("android_apk_repository", "apk_id"),
    }
    for kind in ("static", "dynamic", "registry"):
        for row in scytale.get(kind, []):
            if row.get("sha256", row.get("base_apk_sha256")) != sha:
                raise ValueError("Scytale evidence is not an exact hash match")
            table, key = tables[kind]
            scytale_refs.append(ref("scytale", table, {key: row[key]}, row))
    scytale["evidence_refs"] = sorted(set(scytale_refs))
    registry = scytale.get("registry") or []
    versions = {
        (r.get("version_code"), r.get("version_name"))
        for r in registry
        if r.get("version_code") is not None or r.get("version_name") is not None
    }
    version_refs = [
        r for r in scytale_refs if refs[r]["table"] == "android_apk_repository"
    ]
    if len(versions) == 1:
        code, name = next(iter(versions))
        artifact["version"] = field(
            {"code": code, "name": name},
            state="supported",
            refs=version_refs,
            support="exact_hash_registry_metadata",
        )
    elif versions:
        artifact["version"] = field(
            state="conflict",
            refs=version_refs,
            candidates=[
                {"code": code, "name": name} for code, name in sorted(versions, key=str)
            ],
            reason="Exact hash registry versions disagree",
        )
    if errors:
        status = "error"
        reasons.extend(errors)
    elif identity_conflict:
        status = "complete_with_conflict"
    elif not sample:
        status = "insufficient_evidence"
    elif not android:
        status = "unsupported_artifact"
    elif any(
        v["state"] == "conflict"
        for v in list(conclusions.values()) + [artifact["version"]]
    ):
        status = "complete_with_conflict"
    elif any(v["state"] == "unresolved" for v in conclusions.values()):
        status = "complete_with_unresolved_fields"
    else:
        status = "complete"
    return {
        "contract_version": CONTRACT_VERSION,
        "artifact": artifact,
        "assessment": conclusions,
        "evidence": {
            "erebus": {
                "availability": "available"
                if catalog
                else evidence.get("lookup_status", "unavailable"),
                "catalog_refs": catalog_refs,
                "authority_refs": authority_refs,
                "av_refs": av_refs,
            },
            "permissions": permission_result,
            "scytale": scytale,
        },
        "confidence": {
            "representation": "field_support_and_unmodified_source_policy",
            "model_probability": None,
            "av_source_policy": verdicts,
        },
        "provenance": {
            "engine_version": engine_version,
            "code_version": code_version or source_code_version(),
            "evidence_digest": digest(evidence),
            "source_snapshots": evidence.get("source_snapshots", {}),
            "references": refs,
            "rule_id": engine_version,
        },
        "processing": {
            "status": status,
            "reasons": reasons,
            "unresolved_fields": [
                k for k, v in conclusions.items() if v["state"] == "unresolved"
            ],
        },
    }
