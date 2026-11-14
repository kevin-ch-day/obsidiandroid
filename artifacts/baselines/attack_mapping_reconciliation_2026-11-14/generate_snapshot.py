#!/usr/bin/env python3
"""Read-only reconciliation snapshot: PI ATT&CK tables vs the ObsidianDroid v2 mapping.

Runs SELECT / SHOW CREATE VIEW only, through the local socket login given by
--db-user (default claude_ro). Never issues DDL/DML. Writes TSV/JSON files into
--out, which must not already contain outputs. Mapping strength is a property of
the seeded relationship rows, not behavioural evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

QUERIES = {
    "lut_rows": "SELECT attack_technique_id, attack_name, tactic, platform, source_url, notes, "
                "record_created_at_utc, record_updated_at_utc FROM android_attack_technique_lut ORDER BY attack_technique_id;",
    "mapping_rows": "SELECT m.mapping_id, m.permission_string_norm, HEX(m.permission_string_norm) AS permission_hex, "
                    "LENGTH(m.permission_string_norm) AS byte_length, CHAR_LENGTH(m.permission_string_norm) AS char_length, "
                    "COLLATION(m.permission_string_norm) AS collation_name, m.attack_technique_id, m.mapping_strength, "
                    "m.mapping_source, m.active_flag, m.evidence_note, m.record_created_at_utc, m.record_updated_at_utc, "
                    "a.lifecycle_status AS dict_aosp_lifecycle_status, a.protection_level AS dict_aosp_protection_level, "
                    "i.canonical_permission AS api_identity_canonical, i.authority_class AS api_identity_authority_class, "
                    "i.identity_status AS api_identity_status "
                    "FROM android_permission_attack_mapping m "
                    "LEFT JOIN android_permission_dict_aosp a ON a.constant_value_norm = m.permission_string_norm "
                    "LEFT JOIN api_permission_identity i ON LOWER(i.canonical_permission) = m.permission_string_norm "
                    "ORDER BY m.mapping_id;",
    "schema_migration_0058": "SELECT id, version, note, applied_at_utc FROM schema_migrations WHERE version='0058';",
    "view_summary_rows": "SELECT attack_technique_id, attack_name, tactic, sample_count, mapped_permission_observations "
                         "FROM v_android_permission_attack_surface_summary ORDER BY attack_technique_id;",
}
VIEWS = ("v_android_permission_attack_surface_current", "v_android_permission_attack_surface_summary")
DISPOSITIONS = ("exact_match", "case_only_difference", "db_only_legacy", "db_only_write_token",
                "yaml_only", "technique_absent_from_yaml")


def sql(user: str, database: str, statement: str, *, batch: bool = True) -> str:
    cmd = ["mariadb", "-u", user, database, "-e", statement]
    if batch:
        cmd.insert(3, "-B")
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def tsv_rows(text: str) -> list[dict]:
    return list(csv.DictReader(text.splitlines(), delimiter="\t"))


def write_tsv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("x", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def load_bundle(path: Path) -> dict:
    raw = path.read_bytes()
    bundle = json.loads(raw)
    objs = bundle["objects"]
    by_id = {o["id"]: o for o in objs}
    parents = {r["source_ref"]: r["target_ref"] for r in objs
               if r["type"] == "relationship" and r.get("relationship_type") == "subtechnique-of"}
    tactics = {o["x_mitre_shortname"]: o["name"] for o in objs if o["type"] == "x-mitre-tactic"}
    coll = next(o for o in objs if o["type"] == "x-mitre-collection")
    techniques = {}
    for o in objs:
        if o["type"] != "attack-pattern":
            continue
        ext = [r for r in o.get("external_references", []) if r.get("source_name") == "mitre-attack"]
        if not ext:
            continue
        phases = sorted(k["phase_name"] for k in o.get("kill_chain_phases", []) if k["kill_chain_name"] == "mitre-mobile-attack")
        parent = by_id.get(parents.get(o["id"], ""), {})
        techniques[ext[0]["external_id"]] = {
            "stix_id": o["id"], "name": o["name"], "version": o.get("x_mitre_version", ""),
            "modified": o["modified"], "revoked": bool(o.get("revoked", False)),
            "deprecated": bool(o.get("x_mitre_deprecated", False)), "url": ext[0].get("url", ""),
            "tactic_shortnames": phases, "tactic_names": [tactics.get(p, p) for p in phases],
            "display_alias": f"{parent['name']}: {o['name']}" if parent else None,
            "platforms": o.get("x_mitre_platforms", []),
        }
    return {"sha256": hashlib.sha256(raw).hexdigest(), "collection_version": coll["x_mitre_version"],
            "collection_modified": coll["modified"], "techniques": techniques, "path": str(path)}


def name_match(lut_name: str, t: dict | None) -> str:
    if t is None:
        return "technique_absent"
    if lut_name == t["name"]:
        return "exact"
    if t["display_alias"] and lut_name == t["display_alias"]:
        return "display_alias_parent_colon_sub"
    return "mismatch"


def tactic_match(lut_tactic: str, t: dict | None) -> str:
    if t is None:
        return "technique_absent"
    names = t["tactic_names"]
    if names == [lut_tactic]:
        return "exact"
    if lut_tactic in names:
        return "subset_single_of_multi"
    return "mismatch"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--yaml", type=Path, required=True)
    ap.add_argument("--bundle", type=Path, required=True, help="pinned Mobile ATT&CK v20.1 bundle")
    ap.add_argument("--earlier-bundle", type=Path, help="optional earlier Mobile ATT&CK bundle for release attribution")
    ap.add_argument("--db-user", default="claude_ro")
    ap.add_argument("--database", default="android_permission_intel")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if any(a.out.glob("*.tsv")):
        sys.exit("refusing to overwrite existing snapshot outputs")

    (a.out / "queries.sql").write_text(
        "-- Read-only statements executed by generate_snapshot.py (mariadb -u %s %s)\n" % (a.db_user, a.database)
        + "".join(f"\n-- {k}\n{v}\n" for k, v in QUERIES.items())
        + "".join(f"\nSHOW CREATE VIEW {v}\\G\n" for v in VIEWS), encoding="utf-8")

    results = {k: tsv_rows(sql(a.db_user, a.database, q)) for k, q in QUERIES.items()}
    write_tsv(a.out / "lut_rows.tsv", results["lut_rows"])
    write_tsv(a.out / "mapping_rows.tsv", results["mapping_rows"])
    write_tsv(a.out / "view_summary_rows.tsv", results["view_summary_rows"])
    (a.out / "view_definitions.txt").write_text(
        "".join(sql(a.db_user, a.database, f"SHOW CREATE VIEW {v}\\G", batch=False) for v in VIEWS), encoding="utf-8")

    current = load_bundle(a.bundle)
    earlier = load_bundle(a.earlier_bundle) if a.earlier_bundle else None
    label_cur = f"v{current['collection_version']}"
    label_old = f"v{earlier['collection_version']}" if earlier else None

    lut_cmp = []
    for r in results["lut_rows"]:
        tid = r["attack_technique_id"]; tc = current["techniques"].get(tid); te = earlier["techniques"].get(tid) if earlier else None
        nm_c, tc_c = name_match(r["attack_name"], tc), tactic_match(r["tactic"], tc)
        nm_e, tc_e = (name_match(r["attack_name"], te), tactic_match(r["tactic"], te)) if earlier else ("not_checked", "not_checked")
        if earlier:
            if nm_e in ("exact", "display_alias_parent_colon_sub") and tc_e == "exact":
                attribution = f"consistent_with_{label_old}"
            elif nm_c in ("exact", "display_alias_parent_colon_sub") and tc_c == "exact":
                attribution = f"consistent_with_{label_cur}_only"
            else:
                attribution = f"matches_neither_{label_old}_nor_{label_cur}"
        else:
            attribution = "undetermined_no_earlier_bundle_supplied"
        lut_cmp.append({
            "attack_technique_id": tid, "lut_name": r["attack_name"], "lut_tactic": r["tactic"], "lut_source_url": r["source_url"],
            f"{label_cur}_exists": tc is not None, f"{label_cur}_name": tc["name"] if tc else "",
            f"{label_cur}_display_alias": (tc or {}).get("display_alias") or "",
            f"{label_cur}_tactics": ";".join(tc["tactic_names"]) if tc else "",
            f"name_matches_{label_cur}": nm_c, f"tactic_matches_{label_cur}": tc_c,
            f"{label_cur}_revoked": (tc or {}).get("revoked", ""), f"{label_cur}_deprecated": (tc or {}).get("deprecated", ""),
            f"{label_cur}_technique_version": (tc or {}).get("version", ""), f"{label_cur}_modified": (tc or {}).get("modified", ""),
            f"{label_cur}_url": (tc or {}).get("url", ""),
            "url_differs_only_by_trailing_slash": bool(tc) and r["source_url"].rstrip("/") == tc["url"].rstrip("/") and r["source_url"] != tc["url"],
            "earlier_release_checked": label_old or "", "earlier_name": (te or {}).get("name", "") if earlier else "",
            "earlier_tactics": ";".join(te["tactic_names"]) if te else "", "earlier_technique_version": (te or {}).get("version", "") if earlier else "",
            "name_matches_earlier": nm_e, "tactic_matches_earlier": tc_e, "release_attribution": attribution,
        })
    write_tsv(a.out / "lut_vs_attack_releases.tsv", lut_cmp)

    mapping = yaml.safe_load(a.yaml.read_text(encoding="utf-8"))
    yaml_edges = {}
    for rule in mapping["rules"]:
        for tok in rule["required_any"]:
            yaml_edges[(tok, rule["attack_id"])] = rule
    yaml_techniques = {r["attack_id"] for r in mapping["rules"]}
    yaml_by_casefold = {(t.lower(), aid): (t, r) for (t, aid), r in yaml_edges.items()}
    edges, matched = [], set()
    for r in results["mapping_rows"]:
        key = (r["permission_string_norm"], r["attack_technique_id"])
        hit = yaml_by_casefold.get(key)
        strength_conflict = False
        if hit:
            tok, rule = hit; matched.add((tok, rule["attack_id"]))
            disposition = "exact_match" if tok == r["permission_string_norm"] else "case_only_difference"
            strength_conflict = r["mapping_strength"] == "strong" and rule["relationship_category"] == "CONTEXT_REQUIRED"
        elif r["attack_technique_id"] not in yaml_techniques:
            tok = rule = None; disposition = "technique_absent_from_yaml"
        elif r["dict_aosp_lifecycle_status"] == "legacy_removed" or r["api_identity_authority_class"] == "AOSP_HIDDEN":
            tok = rule = None; disposition = "db_only_legacy"
        elif ".write_" in r["permission_string_norm"]:
            tok = rule = None; disposition = "db_only_write_token"
        else:
            tok = rule = None; disposition = "db_only_unclassified"
        edges.append({
            "edge_source": "both" if hit else "db_only", "mapping_id": r["mapping_id"], "db_token": r["permission_string_norm"],
            "yaml_token": tok or "", "attack_id": r["attack_technique_id"], "db_mapping_strength": r["mapping_strength"],
            "db_active_flag": r["active_flag"], "yaml_rule_id": rule["rule_id"] if rule else "",
            "yaml_relationship_category": rule["relationship_category"] if rule else "",
            "yaml_allowed_roles": ";".join(rule["allowed_roles"]) if rule else "", "yaml_tactics": ";".join(rule["tactics"]) if rule else "",
            "dict_aosp_lifecycle_status": r["dict_aosp_lifecycle_status"], "api_identity_authority_class": r["api_identity_authority_class"],
            "disposition": disposition, "strength_conflict": strength_conflict,
        })
    for (tok, aid), rule in sorted(yaml_edges.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if (tok, aid) in matched:
            continue
        edges.append({"edge_source": "yaml_only", "mapping_id": "", "db_token": "", "yaml_token": tok, "attack_id": aid,
                      "db_mapping_strength": "", "db_active_flag": "", "yaml_rule_id": rule["rule_id"],
                      "yaml_relationship_category": rule["relationship_category"], "yaml_allowed_roles": ";".join(rule["allowed_roles"]),
                      "yaml_tactics": ";".join(rule["tactics"]), "dict_aosp_lifecycle_status": "", "api_identity_authority_class": "",
                      "disposition": "yaml_only", "strength_conflict": False})
    write_tsv(a.out / "db_rows_vs_yaml_edges.tsv", edges)

    counts = {}
    for e in edges:
        counts[e["disposition"]] = counts.get(e["disposition"], 0) + 1
    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "connection": f"{a.db_user}@localhost (unix socket), database {a.database}",
        "access_mode": "READ_ONLY_SELECT_AND_SHOW_VIEW", "ddl_or_dml_executed": False,
        "yaml": {"path": str(a.yaml), "sha256": hashlib.sha256(a.yaml.read_bytes()).hexdigest(), "version": mapping["version"],
                 "schema_version": mapping["schema_version"], "rule_count": len(mapping["rules"]), "edge_count": len(yaml_edges)},
        "current_bundle": {k: v for k, v in current.items() if k != "techniques"},
        "earlier_bundle": {k: v for k, v in earlier.items() if k != "techniques"} if earlier else None,
        "schema_migration_0058": results["schema_migration_0058"],
        "lut_rows": len(results["lut_rows"]), "mapping_rows": len(results["mapping_rows"]),
        "edge_disposition_counts": counts, "strength_conflicts": sum(e["strength_conflict"] for e in edges),
        "mapping_strength_semantics": "relationship property of seeded rows; not behavioural evidence",
    }
    (a.out / "snapshot_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt["edge_disposition_counts"]), "strength_conflicts", receipt["strength_conflicts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
