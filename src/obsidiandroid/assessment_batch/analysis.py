"""Descriptive, attribution-aware cohort metrics; never a labeling engine."""

from __future__ import annotations
from collections import Counter, defaultdict
import json
import re


def normalize(value):
    return re.sub(r"[\s_-]+", "", str(value or "").strip().casefold())


def summarize(packets, records):
    """Return row-level coverage, disagreements and rates with explicit denominators.

    Parsed VT vendor tokens remain assertions. Alias-aware lexical variation is
    not independent-source conflict adjudication; lineage counts do not prove
    source independence. No counterfactual classifications are generated.
    """
    bysha = {r["artifact"]["sha256"]: r for r in records}
    if (
        len(packets) != len(records)
        or len(bysha) != len(records)
        or set(bysha) != {p["sha256"] for p in packets}
    ):
        raise ValueError("Cohort records and evidence scope differ")
    rows = []
    cases = []
    pairs = []
    for packet in packets:
        sha = packet["sha256"]
        r = bysha[sha]
        e = packet["engine_evidence"]
        c = packet["context"]
        family = r["assessment"]["family"]
        type_ = r["assessment"]["type"]
        mb = c.get("malwarebazaar_claim") or {}
        claims = []
        systems = set()
        if mb:
            systems.add("malwarebazaar")
            if mb.get("signature"):
                claims.append(
                    {
                        "source": "malwarebazaar",
                        "label": mb["signature"],
                        "reference": c["malwarebazaar_receipt"]["raw_sha256"],
                    }
                )
        for source in c["source_evidence"]:
            try:
                raw = json.loads(source.get("raw_value") or "{}")
            except (ValueError, TypeError):
                raw = {}
            if not isinstance(raw, dict):
                raw = {}
            lineage = (
                raw.get("source_lineage")
                or raw.get("discovery_source")
                or "unresolved-source-lineage"
            )
            system = (
                "malwarebazaar"
                if "malwarebazaar" in lineage.casefold()
                else lineage.casefold()
            )
            systems.add(system)
            if raw.get("source_family_label"):
                claims.append(
                    {
                        "source": system,
                        "label": raw["source_family_label"],
                        "reference": source["source_evidence_id"],
                    }
                )
            if (
                raw.get("source_type_label")
                and type_["state"] == "supported"
                and normalize(raw["source_type_label"])
                not in {
                    normalize(type_["value"]["name"]),
                    normalize(type_["value"]["slug"]),
                }
            ):
                cases.append(
                    {
                        "sha256": sha,
                        "kind": "SOURCE_TYPE_LEXICAL_DIFFERENCE",
                        "source": system,
                        "claim": raw["source_type_label"],
                        "assessment": type_["value"],
                        "interpretation": "Lexical difference; type synonym equivalence not adjudicated",
                    }
                )
        retained = bool(e.get("av_scan") or e["permissions"].get("retained"))
        if retained or e.get("av_labels"):
            systems.add("virustotal")
        for label in e.get("av_labels", []):
            if label.get("parsed_family_token"):
                claims.append(
                    {
                        "source": "virustotal:" + label["vendor_key"],
                        "label": label["parsed_family_token"],
                        "reference": label["evidence_id"],
                    }
                )
        alias_targets = defaultdict(set)
        for alias in e.get("aliases", []):
            if alias.get("is_active") == 1:
                alias_targets[normalize(alias["alias_token"])].add(
                    normalize(alias["canonical_family_slug"])
                )

        def normalized_claim(label):
            token = normalize(label)
            targets = alias_targets.get(token, set())
            return next(iter(targets)) if len(targets) == 1 else token

        labels = {normalized_claim(q["label"]) for q in claims}
        claim_sources = {q["source"] for q in claims}
        comparable_sources = len(claim_sources) >= 2
        lexical_disagreement = comparable_sources and len(labels) > 1
        if lexical_disagreement:
            cases.append(
                {
                    "sha256": sha,
                    "kind": "SOURCE_FAMILY_LEXICAL_DISAGREEMENT",
                    "source": sorted(claim_sources),
                    "claim": claims,
                    "assessment": family,
                    "interpretation": "Attributed parsed/source-token variation; vendors and mirrors are not proven independent",
                }
            )
        if family["state"] == "conflict":
            cases.append(
                {
                    "sha256": sha,
                    "kind": "GOVERNED_FAMILY_CONFLICT",
                    "source": "erebus-governance",
                    "claim": family["candidates"],
                    "assessment": None,
                    "interpretation": family["reason"],
                }
            )
        if type_["state"] == "supported" and family["state"] != "supported":
            cases.append(
                {
                    "sha256": sha,
                    "kind": "SUPPORTED_TYPE_WITH_UNSUPPORTED_FAMILY",
                    "source": "governed-assessment",
                    "claim": type_["value"],
                    "assessment": family,
                    "interpretation": "Dimensions assessed independently",
                }
            )
        if family["state"] == "supported" and type_["state"] != "supported":
            cases.append(
                {
                    "sha256": sha,
                    "kind": "SUPPORTED_FAMILY_WITH_UNSUPPORTED_TYPE",
                    "source": "governed-assessment",
                    "claim": family["value"],
                    "assessment": type_,
                    "interpretation": "Dimensions assessed independently",
                }
            )
        comparison = (
            "NO_SIGNATURE" if not mb.get("signature") else "FAMILY_NOT_SUPPORTED"
        )
        if mb.get("signature") and family["state"] == "supported":
            names = {
                normalize(family["value"]["name"]),
                normalize(family["value"]["slug"]),
            }
            direct = normalize(mb["signature"]) in names
            alias = normalized_claim(mb["signature"]) in names
            comparison = (
                "DIRECT_AGREEMENT"
                if direct
                else "ALIAS_AGREEMENT"
                if alias
                else "LEXICAL_DISAGREEMENT"
            )
            pairs.append(
                {
                    "sha256": sha,
                    "signature": mb["signature"],
                    "family": family["value"],
                    "direct_match": direct,
                    "alias_aware_match": direct or alias,
                }
            )
            if not (direct or alias):
                cases.append(
                    {
                        "sha256": sha,
                        "kind": "MALWAREBAZAAR_GOVERNED_FAMILY_DISAGREEMENT",
                        "source": "malwarebazaar",
                        "claim": mb["signature"],
                        "assessment": family["value"],
                        "interpretation": "Comparable supported family; lexical/available-governed-alias mismatch, not independent ground truth",
                    }
                )
        static = c.get("static_baseline")
        validated = bool(static and static["status"] == "VALID_APK")
        pi = bool(e["permissions"]["observations"])
        if validated and mb.get("file_type") and mb["file_type"] != "apk":
            cases.append(
                {
                    "sha256": sha,
                    "kind": "STATIC_PROVIDER_ARTIFACT_CONTRADICTION",
                    "source": "malwarebazaar",
                    "claim": mb["file_type"],
                    "assessment": "VALID_APK",
                    "interpretation": "Exact static evidence differs from provider metadata",
                }
            )
        rows.append(
            {
                "sha256": sha,
                "assessment_id": r["assessment_id"],
                "revision": r["revision"],
                "family_state": family["state"],
                "type_state": type_["state"],
                "variant_state": r["assessment"]["variant"]["state"],
                "processing_status": r["processing"]["status"],
                "artifact_classification": c["artifact_classification"],
                "artifact_identity_basis": c["artifact_identity_basis"],
                "external_lineages": sorted(systems),
                "external_lineage_count": len(systems),
                "source_independence_established": False,
                "source_family_assertions": claims,
                "multi_assertion_comparable": comparable_sources,
                "source_family_lexical_disagreement": lexical_disagreement,
                "malwarebazaar_signature": mb.get("signature"),
                "malwarebazaar_family_comparison": comparison,
                "vt_retained_evidence_available": retained,
                "permission_observations_available": pi,
                "permission_observation_count": len(e["permissions"]["observations"]),
                "permission_unresolved_count": r["evidence"]["permissions"].get(
                    "unresolved_count"
                ),
                "projection_state": c["permission_coverage"]["projection_state"],
                "exact_bytes_verified": bool(static and static["exact_bytes_verified"]),
                "exact_apk_static_validated": validated,
                "static_attempt_status": static["status"]
                if static
                else "NOT_AVAILABLE",
                "compatibility": static["compatibility"]
                if static
                else "UNKNOWN_NO_EXACT_STATIC",
                "runtime_evidence_rows": len(e["scytale"]["dynamic"]),
            }
        )

    def rate(n, d):
        return {"numerator": n, "denominator": d, "rate": n / d if d else None}

    summary = {
        "total": len(rows),
        "family": dict(Counter(r["family_state"] for r in rows)),
        "type": dict(Counter(r["type_state"] for r in rows)),
        "variant": dict(Counter(r["variant_state"] for r in rows)),
        "processing": dict(Counter(r["processing_status"] for r in rows)),
        "artifact_classification": dict(
            Counter(r["artifact_classification"] for r in rows)
        ),
        "artifact_identity_basis": dict(
            Counter(r["artifact_identity_basis"] for r in rows)
        ),
        "projection": dict(Counter(r["projection_state"] for r in rows)),
        "permission_observations_available": sum(
            r["permission_observations_available"] for r in rows
        ),
        "exact_bytes_verified": sum(r["exact_bytes_verified"] for r in rows),
        "exact_apk_static_validated": sum(
            r["exact_apk_static_validated"] for r in rows
        ),
        "mb_signature_present": sum(bool(r["malwarebazaar_signature"]) for r in rows),
        "mb_direct_agreement": rate(sum(p["direct_match"] for p in pairs), len(pairs)),
        "mb_alias_aware_agreement": rate(
            sum(p["alias_aware_match"] for p in pairs), len(pairs)
        ),
        "source_lexical_disagreement": rate(
            sum(r["source_family_lexical_disagreement"] for r in rows),
            sum(r["multi_assertion_comparable"] for r in rows),
        ),
        "disagreement_cases": dict(Counter(r["kind"] for r in cases)),
        "disagreement_unique_hashes": len({r["sha256"] for r in cases}),
        "interpretation": "Descriptive convenience cohort; lexical agreement/variation is not ground truth, source independence or causation; no runtime effect estimated",
    }
    summary["coverage_family_crosstabs"] = {
        name: [
            {
                "available": v,
                "family_state": state,
                "count": sum(r[name] == v and r["family_state"] == state for r in rows),
            }
            for v in [False, True]
            for state in ["supported", "conflict", "unresolved"]
        ]
        for name in [
            "permission_observations_available",
            "exact_apk_static_validated",
            "vt_retained_evidence_available",
        ]
    }
    summary["source_lineage_support"] = [
        {
            "group": label,
            "total": len(group),
            "supported_families": sum(r["family_state"] == "supported" for r in group),
            "independence_established": False,
        }
        for label, group in [
            ("none", [r for r in rows if r["external_lineage_count"] == 0]),
            ("single", [r for r in rows if r["external_lineage_count"] == 1]),
            ("multiple", [r for r in rows if r["external_lineage_count"] >= 2]),
        ]
    ]
    return {
        "summary": summary,
        "evidence_matrix": rows,
        "disagreements": cases,
        "mb_comparable_pairs": pairs,
    }
