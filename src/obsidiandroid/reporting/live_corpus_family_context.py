"""Live-corpus family context + dominant-family robustness (offline).

Reads completed-run artifacts only. Separates local observed facts, local
authority, external reports, hypotheses, and validation states. Does not query
databases, enable Core persistence, mutate taxonomy, or run the pipeline.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from obsidiandroid.labeling.malware_family_constants import (
    canonicalize_family_label,
    normalize_family_name,
)
from obsidiandroid.reporting.cohort_count_contract import compute_cohort_identity_counts
def build_dominant_family_type_robustness(**_kwargs):
    """Stubbed in family-context commit; replaced by sensitivity module."""
    return pd.DataFrame()
from obsidiandroid.reporting.permission_governance_lanes import permission_lane_lookup
from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

CONTRACT_VERSION = "1.0.0"
COMPOSER_VERSION = "1.0.0"

EVIDENCE_STATES = (
    "LOCAL_OBSERVED",
    "LOCAL_AUTHORITY",
    "EXTERNAL_REPORTED",
    "HYPOTHESIS",
    "LOCALLY_SUPPORTED",
    "LOCALLY_MIXED",
    "NOT_OBSERVED",
    "NOT_TESTABLE_STATICALLY",
    "IDENTITY_UNCERTAIN",
)

AUDIT_FAMILIES = (
    "ClayRat",
    "Godfather",
    "ArsinkRAT",
    "Devixor",
    "Gigabud",
    "Nexus",
    "Joker",
    "SarangTrap",
    "Triada",
    "Irata",
    "CarrierBillingFraud",
    "Applite",
    "SpyNote",
    "PixPirate",
)

TOP_FAMILY_N = 15
HEADLINE_PREV_FLOOR = 20.0
ENRICHED_ROLES = (
    "low_prevalence_strongly_type_enriched",
    "common_type_enriched",
    "type_enriched",
)

# Public-role paraphrase for type-agreement checks (not authority).
PUBLIC_ROLE_TYPE_EXPECTATION: dict[str, tuple[str, ...]] = {
    "ClayRat": ("rat", "spyware"),
    "Godfather": ("banker", "rat"),
    "ArsinkRAT": ("rat",),
    "Devixor": ("banker", "rat", "ransomware"),
    "Gigabud": ("banker", "rat"),
    "Nexus": ("banker",),
    "Joker": ("subscription-fraud", "banker", "adware"),
    "SarangTrap": ("spyware", "rat", "trojan"),
    "Triada": ("backdoor",),
    "Irata": ("banker", "rat", "spyware"),
    "CarrierBillingFraud": ("subscription-fraud", "banker", "adware"),
    "Applite": (),  # identity uncertain — no forced expectation
    "SpyNote": ("rat",),
    "PixPirate": ("banker", "rat"),
}

# Curated external context: concise paraphrases + references only.
EXTERNAL_FAMILY_CONTEXT: tuple[dict[str, Any], ...] = (
    {
        "family_slug": "ClayRat",
        "external_source": "Zimperium; BleepingComputer",
        "source_date": "2025",
        "source_type": "vendor_blog; news",
        "reported_campaign_sample_period": "2025",
        "reported_capabilities": "SMS/call/contact theft; camera/screen/notifications; SMS self-propagation",
        "reported_delivery_mechanism": "Telegram/phishing; fake WhatsApp/TikTok/YouTube; SMS-handler sideload",
        "reported_geography": "Russia-centric reporting",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Godfather",
        "external_source": "Zimperium; MITRE ATT&CK S1231",
        "source_date": "2020-2025",
        "source_type": "vendor_blog; knowledge_base",
        "reported_campaign_sample_period": "since ~2020; ongoing",
        "reported_capabilities": "Banking fraud; accessibility/overlays; OTP theft; on-device virtualization",
        "reported_delivery_mechanism": "Trojanized apps; virtualization sandbox of bank apps",
        "reported_geography": "Global inject lists; some Turkey-focused virtualization campaigns",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "ArsinkRAT",
        "external_source": "Zimperium",
        "source_date": "2025",
        "source_type": "vendor_blog",
        "reported_campaign_sample_period": "late 2025 reporting",
        "reported_capabilities": "Cloud-native surveillance RAT; Firebase/Drive/Apps Script/Telegram C2",
        "reported_delivery_mechanism": "Mod/premium brand fakes via Telegram/Discord",
        "reported_geography": "Not fixed in paraphrase",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Devixor",
        "external_source": "public IOC / research notes preserved in corpus batches",
        "source_date": "2025",
        "source_type": "research_notes",
        "reported_campaign_sample_period": "from ~Oct 2025",
        "reported_capabilities": "Banking RAT; SMS/OTP; accessibility; ransomware lock module",
        "reported_delivery_mechanism": "Banking-fraud APKs",
        "reported_geography": "Iran-focused reporting",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Gigabud",
        "external_source": "Group-IB; Malpedia",
        "source_date": "2023-2025",
        "source_type": "vendor_blog; catalog",
        "reported_campaign_sample_period": "multi-year",
        "reported_capabilities": "Banking RAT; accessibility; screen capture/streaming; simulated taps",
        "reported_delivery_mechanism": "Fake airline/loan/gov apps",
        "reported_geography": "SEA then LATAM reporting",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Nexus",
        "external_source": "Cleafy",
        "source_date": "2024-2025",
        "source_type": "vendor_blog",
        "reported_campaign_sample_period": "MaaS era reporting",
        "reported_capabilities": "Overlays; keylogging; SMS 2FA theft; financial injects",
        "reported_delivery_mechanism": "Banking botnet / MaaS",
        "reported_geography": "Not fixed in paraphrase",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Joker",
        "external_source": "Trend Micro; Kaspersky",
        "source_date": "2017-2021+",
        "source_type": "vendor_blog",
        "reported_campaign_sample_period": "Play Store campaigns since ~2017",
        "reported_capabilities": "Premium/subscription fraud; SMS/notification OTP intercept",
        "reported_delivery_mechanism": "Play Store cat-and-mouse; staged payloads",
        "reported_geography": "Global Play Store",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "SarangTrap",
        "external_source": "Zimperium",
        "source_date": "2024-2025",
        "source_type": "vendor_advisory",
        "reported_campaign_sample_period": "dating-app campaign reporting",
        "reported_capabilities": "Contacts/photos exfiltration; extortion",
        "reported_delivery_mechanism": "Fake dating apps",
        "reported_geography": "Not fixed in paraphrase",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Triada",
        "external_source": "MITRE ATT&CK S0424; Kaspersky",
        "source_date": "2016-2025",
        "source_type": "knowledge_base; vendor_blog",
        "reported_campaign_sample_period": "long-running modular backdoor",
        "reported_capabilities": "Zygote/firmware persistence; modular downloads; SMS payment redirect",
        "reported_delivery_mechanism": "Root/firmware preinstall and modular drop",
        "reported_geography": "Not fixed in paraphrase",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Irata",
        "external_source": "Malpedia; vendor bulletins",
        "source_date": "2023-2025",
        "source_type": "catalog; bulletin",
        "reported_campaign_sample_period": "multi-campaign",
        "reported_capabilities": "Smishing RAT; banking theft; SMS/contacts for 2FA/propagation",
        "reported_delivery_mechanism": "Smishing / trojanized apps",
        "reported_geography": "Iran-origin reports; Italy campaigns noted",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "CarrierBillingFraud",
        "external_source": "name-aligned public subscription-fraud class (Joker/MobOk niche)",
        "source_date": "n/a",
        "source_type": "class_paraphrase",
        "reported_campaign_sample_period": "n/a",
        "reported_capabilities": "Carrier/WAP billing fraud; SMS/notification intercept",
        "reported_delivery_mechanism": "Silent premium subscribe flows",
        "reported_geography": "Not fixed",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "Applite",
        "external_source": "limited public writeups under this exact slug",
        "source_date": "n/a",
        "source_type": "identity_note",
        "reported_campaign_sample_period": "n/a",
        "reported_capabilities": "Unclear under exact slug",
        "reported_delivery_mechanism": "Unknown",
        "reported_geography": "Unknown",
        "evidence_independence": "IDENTITY_UNCERTAIN",
    },
    {
        "family_slug": "SpyNote",
        "external_source": "MITRE ATT&CK S0305; Fortinet",
        "source_date": "2016-2024",
        "source_type": "knowledge_base; vendor_blog",
        "reported_campaign_sample_period": "long-running RAT builder family",
        "reported_capabilities": "Accessibility abuse; keylog; remote control; wallet UI control",
        "reported_delivery_mechanism": "RAT builder / trojanized apps",
        "reported_geography": "Not fixed",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
    {
        "family_slug": "PixPirate",
        "external_source": "IBM; Cleafy",
        "source_date": "2023-2024",
        "source_type": "vendor_blog",
        "reported_campaign_sample_period": "Pix-payment campaigns",
        "reported_capabilities": "Brazilian banking RAT; ATS; accessibility; SMS; stealth dropper",
        "reported_delivery_mechanism": "Dropper + iconless droppee",
        "reported_geography": "Brazil-focused reporting",
        "evidence_independence": "EXTERNAL_REPORTED",
    },
)

HYPOTHESIS_SPECS: tuple[dict[str, Any], ...] = (
    {
        "hypothesis_id": "clayrat_sms_contact_phone",
        "family_slug": "ClayRat",
        "type_slug": "rat",
        "statement": "ClayRat shows SMS/contact/phone permission enrichment vs RAT baseline",
        "permission_needles": (
            "android.permission.send_sms",
            "android.permission.read_sms",
            "android.permission.receive_sms",
            "android.permission.read_contacts",
            "android.permission.call_phone",
            "android.permission.read_phone_state",
            "android.permission.read_call_log",
        ),
        "static_testable": True,
        "enrichment_pp": 10.0,
    },
    {
        "hypothesis_id": "godfather_accessibility_overlay",
        "family_slug": "Godfather",
        "type_slug": "banker",
        "statement": "Godfather shows accessibility/overlay-related declarations vs banker baseline",
        "permission_needles": (
            "android.permission.bind_accessibility_service",
            "android.permission.system_alert_window",
            "android.permission.package_usage_stats",
        ),
        "static_testable": True,
        "enrichment_pp": 10.0,
        "also_runtime_note": True,
    },
    {
        "hypothesis_id": "arsinkrat_network_storage",
        "family_slug": "ArsinkRAT",
        "type_slug": "rat",
        "statement": "ArsinkRAT shows broad network/storage capability structure",
        "permission_needles": (
            "android.permission.internet",
            "android.permission.access_network_state",
            "android.permission.read_external_storage",
            "android.permission.write_external_storage",
            "android.permission.manage_external_storage",
        ),
        "static_testable": True,
        "enrichment_pp": 5.0,
    },
    {
        "hypothesis_id": "devixor_sms_a11y_overlay",
        "family_slug": "Devixor",
        "type_slug": "banker",
        "statement": "Devixor shows SMS + accessibility/overlay combination",
        "permission_needles": (
            "android.permission.send_sms",
            "android.permission.read_sms",
            "android.permission.receive_sms",
            "android.permission.bind_accessibility_service",
            "android.permission.system_alert_window",
        ),
        "static_testable": True,
        "enrichment_pp": 10.0,
    },
    {
        "hypothesis_id": "gigabud_accessibility_screen",
        "family_slug": "Gigabud",
        "type_slug": "banker",
        "statement": "Gigabud shows accessibility/screen-related declarations",
        "permission_needles": (
            "android.permission.bind_accessibility_service",
            "android.permission.capture_secure_video_output",
            "android.permission.foreground_service_media_projection",
            "android.permission.project_media",
        ),
        "static_testable": True,
        "enrichment_pp": 10.0,
    },
    {
        "hypothesis_id": "joker_sms_notification_fraud",
        "family_slug": "Joker",
        "type_slug": "banker",
        "statement": "Joker shows SMS/notification subscription-fraud indicators",
        "permission_needles": (
            "android.permission.send_sms",
            "android.permission.receive_sms",
            "android.permission.read_sms",
            "android.permission.receive_boot_completed",
            "android.permission.post_notifications",
        ),
        "static_testable": True,
        "enrichment_pp": 10.0,
    },
    {
        "hypothesis_id": "triada_weak_ordinary_diff",
        "family_slug": "Triada",
        "type_slug": "backdoor",
        "statement": "Triada shows weaker ordinary app-permission differentiation vs banker/RAT",
        "permission_needles": (),
        "static_testable": True,
        "special": "weak_differentiation",
        "enrichment_pp": 0.0,
    },
    {
        "hypothesis_id": "godfather_virtualization_runtime",
        "family_slug": "Godfather",
        "type_slug": "banker",
        "statement": "Godfather on-device virtualization of bank apps",
        "permission_needles": (),
        "static_testable": False,
    },
    {
        "hypothesis_id": "arsinkrat_cloud_c2_runtime",
        "family_slug": "ArsinkRAT",
        "type_slug": "rat",
        "statement": "ArsinkRAT cloud C2 via Firebase/Drive/Apps Script",
        "permission_needles": (),
        "static_testable": False,
    },
)


def _trends_table(run_root: Path, stem: str, run_id: str) -> Path:
    return run_root / "bundles" / "permission_trends" / "tables" / f"{stem}_{run_id}.csv"


def _require_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def _optional_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def _norm_perm(value: Any) -> str:
    return str(value or "").strip().lower()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_source_identity(
    run_root: Path,
    *,
    expected_run_id: str,
) -> dict[str, Any]:
    """Fail hard when slot metadata disagrees with the requested run identity."""
    run_root = Path(run_root)
    expected = str(expected_run_id).strip()
    manifest_path = run_root / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing run_manifest.json under {run_root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = str(manifest.get("run_id") or "").strip()
    if actual != expected:
        raise ValueError(
            f"run identity mismatch: requested={expected!r} manifest={actual!r} slot={run_root}"
        )
    status = detect_source_run_status(run_root)
    snapshot_path = run_root / "diagnostics" / f"analysis_snapshot_{expected}.csv"
    if not snapshot_path.is_file():
        raise FileNotFoundError(snapshot_path)
    snap = pd.read_csv(snapshot_path)
    counts = compute_cohort_identity_counts(snap)
    coverage = _optional_csv(_trends_table(run_root, "permission_coverage_report", expected))
    perm_bearing = None
    if not coverage.empty and "samples_with_permission_rows" in coverage.columns:
        perm_bearing = int(coverage.iloc[0]["samples_with_permission_rows"])
    input_hashes = {
        "run_manifest.json": sha256_file(manifest_path),
        "analysis_snapshot": sha256_file(snapshot_path),
        "dataset_hash": str(manifest.get("dataset_hash") or ""),
        "config_hash": str(manifest.get("config_hash") or ""),
        "snapshot_sha256_hash": str(
            (manifest.get("analysis_snapshot") or {}).get("snapshot_sha256_hash") or ""
        ),
    }
    represented_types = sorted(
        {
            str(v).strip()
            for v in snap.get("type_slug", pd.Series(dtype=str)).fillna("").tolist()
            if str(v).strip()
        }
    )
    return {
        "run_id": actual,
        "profile_id": str(manifest.get("profile_id") or ""),
        "repository_commit": str(manifest.get("git_commit") or ""),
        "prepared_sample_count": int(manifest.get("cohort_prepared_row_count") or len(snap)),
        "permission_bearing_sample_count": perm_bearing,
        "represented_types": represented_types,
        "governed_known_family_count": int(counts["governed_known_family_count"]),
        "observed_family_label_count_including_unknown": int(
            counts["observed_family_label_count_including_unknown"]
        ),
        "governed_known_type_count": int(counts["governed_known_type_count"]),
        "observed_type_slug_count_including_unknown": int(
            counts["observed_type_slug_count_including_unknown"]
        ),
        "unknown_family_sample_count": int(counts["unknown_family_sample_count"]),
        "unknown_type_sample_count": int(counts["unknown_type_sample_count"]),
        "input_artifact_hashes": input_hashes,
        "run_status": status,
        "snapshot": snap,
        "manifest": manifest,
    }


def _family_support_map(fam_prev: pd.DataFrame) -> dict[str, int]:
    if fam_prev.empty:
        return {}
    work = fam_prev.copy()
    work["family_canonical"] = work["family_canonical"].astype(str)
    work["family_support"] = pd.to_numeric(work["family_support"], errors="coerce").fillna(0)
    return {
        str(k): int(v)
        for k, v in work.groupby("family_canonical")["family_support"].max().items()
    }


def _type_baseline_map(type_prev: pd.DataFrame) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    if type_prev.empty:
        return out
    for row in type_prev.itertuples(index=False):
        out[(str(row.type_slug), _norm_perm(row.permission))] = float(
            pd.to_numeric(getattr(row, "prevalence_pct", 0), errors="coerce") or 0.0
        )
    return out


def _top_permissions_for_family(
    fam_prev: pd.DataFrame,
    family: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    sub = fam_prev[fam_prev["family_canonical"].astype(str) == family].copy()
    if sub.empty:
        return []
    sub["prevalence_pct"] = pd.to_numeric(sub["prevalence_pct"], errors="coerce").fillna(0.0)
    sub = sub.sort_values("prevalence_pct", ascending=False).head(limit)
    return [
        {
            "permission": _norm_perm(r.permission),
            "prevalence_pct": float(r.prevalence_pct),
            "positive_count": int(pd.to_numeric(r.positive_count, errors="coerce") or 0),
        }
        for r in sub.itertuples(index=False)
    ]


def _family_balanced_context(
    fam_prev: pd.DataFrame,
    *,
    family: str,
    type_slug: str,
    top_perms: Sequence[str],
) -> list[dict[str, Any]]:
    """Family prevalence vs mean of other families in the same type."""
    rows: list[dict[str, Any]] = []
    type_frame = fam_prev[fam_prev["type_slug"].astype(str) == type_slug].copy()
    if type_frame.empty:
        return rows
    type_frame["permission"] = type_frame["permission"].map(_norm_perm)
    type_frame["prevalence_pct"] = pd.to_numeric(
        type_frame["prevalence_pct"], errors="coerce"
    ).fillna(0.0)
    for perm in top_perms:
        g = type_frame[type_frame["permission"] == perm]
        if g.empty:
            continue
        self_rows = g[g["family_canonical"].astype(str) == family]
        others = g[g["family_canonical"].astype(str) != family]
        self_prev = float(self_rows["prevalence_pct"].mean()) if not self_rows.empty else float("nan")
        other_prev = float(others["prevalence_pct"].mean()) if not others.empty else float("nan")
        rows.append(
            {
                "permission": perm,
                "family_prevalence_pct": self_prev,
                "other_families_mean_pct": other_prev,
                "delta_vs_other_families_pp": (
                    self_prev - other_prev
                    if pd.notna(self_prev) and pd.notna(other_prev)
                    else float("nan")
                ),
            }
        )
    return rows


def build_family_context_inventory(
    *,
    snapshot: pd.DataFrame,
    membership: pd.DataFrame,
    fam_prev: pd.DataFrame,
    type_prev: pd.DataFrame,
    pairwise_headline: pd.DataFrame,
    top_n: int = TOP_FAMILY_N,
) -> pd.DataFrame:
    """Local inventory for the largest families (no package/hash in headlines)."""
    snap = snapshot.copy()
    snap["family_canonical"] = snap["family_canonical"].fillna("").astype(str)
    snap = snap[~snap["family_canonical"].str.lower().isin(["", "unknown"])].copy()
    counts = (
        snap.groupby(["family_canonical", "family_id", "type_slug"], dropna=False)
        .size()
        .reset_index(name="sample_count")
    )
    # Collapse to primary type per family (mode by sample count).
    primary = (
        counts.sort_values("sample_count", ascending=False)
        .groupby("family_canonical", as_index=False)
        .first()
    )
    primary = primary.sort_values("sample_count", ascending=False).head(int(top_n))
    support_map = _family_support_map(fam_prev)
    type_base = _type_baseline_map(type_prev)

    mem = membership.copy() if not membership.empty else pd.DataFrame()
    if not mem.empty:
        mem["family_canonical"] = mem["family_canonical"].astype(str)
        pkg_col = "android_package_name" if "android_package_name" in mem.columns else None
    else:
        pkg_col = None

    rows: list[dict[str, Any]] = []
    for rec in primary.itertuples(index=False):
        family = str(rec.family_canonical)
        type_slug = str(rec.type_slug)
        fam_rows = snap[snap["family_canonical"] == family]
        years = pd.to_numeric(fam_rows.get("effective_first_seen_year"), errors="coerce").dropna()
        batches = (
            fam_rows.get("source_batch_label", pd.Series(dtype=str))
            .fillna("")
            .astype(str)
            .value_counts()
            .head(5)
        )
        batch_dist = ";".join(f"{k}:{int(v)}" for k, v in batches.items() if k)
        type_dist = (
            counts[counts["family_canonical"] == family]
            .sort_values("sample_count", ascending=False)
            .assign(pair=lambda d: d["type_slug"].astype(str) + ":" + d["sample_count"].astype(str))
            ["pair"]
            .tolist()
        )
        unique_sha = int(fam_rows["sha256"].nunique()) if "sha256" in fam_rows.columns else int(len(fam_rows))
        unique_pkg = None
        largest_pkg_share = None
        if pkg_col and not mem.empty:
            fam_mem = mem[mem["family_canonical"] == family]
            pkgs = fam_mem[pkg_col].fillna("").astype(str)
            pkgs = pkgs[pkgs.str.len() > 0]
            unique_pkg = int(pkgs.nunique())
            if unique_pkg > 0 and len(pkgs) > 0:
                largest_pkg_share = float(pkgs.value_counts().iloc[0] / len(pkgs))

        top_perms = _top_permissions_for_family(fam_prev, family)
        top_perm_names = [p["permission"] for p in top_perms]
        fb_ctx = _family_balanced_context(
            fam_prev, family=family, type_slug=type_slug, top_perms=top_perm_names[:6]
        )
        divergences = []
        for p in top_perms[:6]:
            base = type_base.get((type_slug, p["permission"]), float("nan"))
            divergences.append(
                {
                    "permission": p["permission"],
                    "family_prevalence_pct": p["prevalence_pct"],
                    "type_baseline_pct": base,
                    "delta_pp": (
                        p["prevalence_pct"] - base
                        if pd.notna(base)
                        else float("nan")
                    ),
                }
            )
        pair_bits: list[str] = []
        if not pairwise_headline.empty and "largest_family_canonical" in pairwise_headline.columns:
            hits = pairwise_headline[
                pairwise_headline["largest_family_canonical"].astype(str) == family
            ].copy()
            if not hits.empty and "family_balanced_prevalence_pct" in hits.columns:
                hits["family_balanced_prevalence_pct"] = pd.to_numeric(
                    hits["family_balanced_prevalence_pct"], errors="coerce"
                ).fillna(0.0)
                hits = hits.sort_values("family_balanced_prevalence_pct", ascending=False).head(5)
                for h in hits.itertuples(index=False):
                    pair_bits.append(
                        f"{_norm_perm(h.permission_a)}+{_norm_perm(h.permission_b)}"
                        f"({float(h.family_balanced_prevalence_pct):.1f}%)"
                    )
        if not pair_bits and len(top_perm_names) >= 2:
            # Descriptive prevalence-rank pairs only (not co-occurrence claims).
            pair_bits = [
                f"{top_perm_names[0]}+{top_perm_names[1]}(prevalence_rank)",
            ]

        perm_support = support_map.get(family)
        sample_count = int(rec.sample_count)
        coverage = (
            float(perm_support) / float(sample_count)
            if perm_support is not None and sample_count > 0
            else float("nan")
        )
        rows.append(
            {
                "family_canonical": family,
                "family_id": int(rec.family_id) if pd.notna(rec.family_id) else "",
                "primary_type_slug": type_slug,
                "type_slug_distribution": "|".join(type_dist),
                "sample_count": sample_count,
                "permission_evidence_support": perm_support if perm_support is not None else "",
                "permission_evidence_coverage": coverage,
                "first_observed_year": int(years.min()) if not years.empty else "",
                "last_observed_year": int(years.max()) if not years.empty else "",
                "source_batch_distribution": batch_dist,
                "unique_package_count": unique_pkg if unique_pkg is not None else "",
                "unique_sha_count": unique_sha,
                "available_lineage_group_count": "",  # not present in run-local membership
                "largest_package_share": largest_pkg_share if largest_pkg_share is not None else "",
                "sample_weighted_top_permissions": "|".join(
                    f"{p['permission']}:{p['prevalence_pct']:.1f}" for p in top_perms[:8]
                ),
                "family_balanced_context_json": json.dumps(fb_ctx, sort_keys=True),
                "top_permission_pairs": "|".join(pair_bits),
                "divergence_from_type_baseline_json": json.dumps(divergences, sort_keys=True),
                "evidence_state": "LOCAL_OBSERVED",
            }
        )
    return pd.DataFrame(rows)


def build_external_context_matrix(
    *,
    snapshot: pd.DataFrame,
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    """Join curated external paraphrases with local temporal overlap notes."""
    year_by_family: dict[str, tuple[Any, Any]] = {}
    if not inventory.empty:
        for r in inventory.itertuples(index=False):
            year_by_family[str(r.family_canonical)] = (
                getattr(r, "first_observed_year", ""),
                getattr(r, "last_observed_year", ""),
            )
    local_counts = (
        snapshot.assign(family_canonical=snapshot["family_canonical"].astype(str))
        .groupby("family_canonical")
        .size()
        .to_dict()
    )
    rows: list[dict[str, Any]] = []
    for ext in EXTERNAL_FAMILY_CONTEXT:
        family = str(ext["family_slug"])
        first_y, last_y = year_by_family.get(family, ("", ""))
        local_n = int(local_counts.get(family, 0))
        independence = str(ext.get("evidence_independence") or "EXTERNAL_REPORTED")
        if independence == "IDENTITY_UNCERTAIN":
            validation = "IDENTITY_UNCERTAIN"
            hypothesis = "Public identity under this exact slug is unclear; treat local labels as corpus-specific"
            limitations = "Do not import external role claims; identity uncertain"
        else:
            validation = "EXTERNAL_REPORTED"
            hypothesis = (
                f"If public capability notes hold statically, {family} should show related "
                "manifest permission enrichment vs its governed type baseline"
            )
            limitations = (
                "External paraphrase only; runtime/C2/virtualization may leave no static signal; "
                "not local ground truth"
            )
        temporal = (
            f"local_years={first_y}-{last_y}; local_n={local_n}"
            if local_n
            else f"local_n=0; not observed in prepared cohort"
        )
        rows.append(
            {
                "family_slug": family,
                "external_source": ext["external_source"],
                "source_date": ext["source_date"],
                "source_type": ext["source_type"],
                "reported_campaign_sample_period": ext["reported_campaign_sample_period"],
                "reported_capabilities": ext["reported_capabilities"],
                "reported_delivery_mechanism": ext["reported_delivery_mechanism"],
                "reported_geography": ext["reported_geography"],
                "local_temporal_overlap": temporal,
                "evidence_independence": independence,
                "local_testable_hypothesis": hypothesis,
                "local_validation_status": validation,
                "limitations": limitations,
                "local_sample_count": local_n,
            }
        )
    return pd.DataFrame(rows)


def _alias_path_from_raw(raw: str, canonical: str) -> str:
    raw_s = str(raw or "").strip()
    if not raw_s:
        return f"(blank)->normalize->{normalize_family_name(canonical)}->display->{canonical}"
    norm = normalize_family_name(raw_s)
    disp = canonicalize_family_label(raw_s)
    return f"{raw_s}->normalize->{norm}->display->{disp}"


def build_family_type_assignment_audit(
    *,
    snapshot: pd.DataFrame,
    families: Sequence[str] = AUDIT_FAMILIES,
) -> pd.DataFrame:
    """Audit governed type assignments for named families (read-only)."""
    snap = snapshot.copy()
    snap["family_canonical"] = snap["family_canonical"].fillna("").astype(str)
    rows: list[dict[str, Any]] = []
    for family in families:
        sub = snap[snap["family_canonical"] == family]
        if sub.empty:
            # try case-insensitive
            sub = snap[snap["family_canonical"].str.lower() == family.lower()]
        type_counts = (
            sub.groupby("type_slug").size().sort_values(ascending=False)
            if not sub.empty
            else pd.Series(dtype=int)
        )
        types = [str(t) for t in type_counts.index.tolist()]
        multi = len(types) > 1
        unknown_or_retired = any(
            t.lower() in {"unknown", "pua"} or t.lower().endswith("_retired") for t in types
        )
        expected = PUBLIC_ROLE_TYPE_EXPECTATION.get(family, ())
        primary = types[0] if types else ""
        if family == "Applite" or not expected:
            agree = "IDENTITY_UNCERTAIN"
            disagreement = "IDENTITY_UNCERTAIN"
        elif not types:
            agree = "NOT_OBSERVED"
            disagreement = "family_absent_from_prepared_cohort"
        elif primary in expected:
            agree = "LOCALLY_SUPPORTED"
            disagreement = "none"
        elif any(t in expected for t in types):
            agree = "LOCALLY_MIXED"
            disagreement = f"primary={primary}; expected_one_of={list(expected)}"
        else:
            agree = "LOCALLY_MIXED"
            disagreement = (
                f"governed_primary={primary}; public_role_expectation={list(expected)}; "
                "public role is not local authority"
            )
        raw_vals = (
            sub.get("family_label_raw", pd.Series(dtype=str)).fillna("").astype(str).value_counts().head(3)
            if not sub.empty
            else pd.Series(dtype=int)
        )
        alias_examples = [
            _alias_path_from_raw(raw, family) for raw in raw_vals.index.tolist()
        ]
        if not alias_examples:
            alias_examples = [_alias_path_from_raw(family, family)]
        family_id = ""
        if not sub.empty and "family_id" in sub.columns:
            ids = sub["family_id"].dropna().unique().tolist()
            family_id = "|".join(str(int(x)) if pd.notna(x) else "" for x in ids[:3])
        rows.append(
            {
                "family_canonical": family,
                "family_id": family_id,
                "governed_type_slug_values": "|".join(f"{t}:{int(type_counts[t])}" for t in types),
                "sample_count": int(len(sub)),
                "alias_normalization_path": " || ".join(alias_examples),
                "multi_type_family": bool(multi),
                "unknown_or_retired_types_present": bool(unknown_or_retired),
                "public_role_type_expectation": "|".join(expected) if expected else "IDENTITY_UNCERTAIN",
                "public_role_agreement_status": agree,
                "disagreement_status": disagreement,
                "evidence_state_authority": "LOCAL_AUTHORITY",
                "evidence_state_public_role": "EXTERNAL_REPORTED",
            }
        )
    return pd.DataFrame(rows)


def _permission_lookup(fam_prev: pd.DataFrame, family: str) -> dict[str, float]:
    sub = fam_prev[fam_prev["family_canonical"].astype(str) == family].copy()
    if sub.empty:
        return {}
    sub["permission"] = sub["permission"].map(_norm_perm)
    sub["prevalence_pct"] = pd.to_numeric(sub["prevalence_pct"], errors="coerce").fillna(0.0)
    return {str(r.permission): float(r.prevalence_pct) for r in sub.itertuples(index=False)}


def _match_needles(prev_map: Mapping[str, float], needles: Sequence[str]) -> list[dict[str, Any]]:
    out = []
    for needle in needles:
        n = _norm_perm(needle)
        # exact or suffix match on short name
        hits = [(p, v) for p, v in prev_map.items() if p == n or p.endswith("." + n.split(".")[-1])]
        if not hits:
            # token endswith
            short = n.split(".")[-1]
            hits = [(p, v) for p, v in prev_map.items() if p.endswith(short)]
        if hits:
            hits.sort(key=lambda x: x[1], reverse=True)
            out.append({"needle": n, "permission": hits[0][0], "prevalence_pct": hits[0][1]})
        else:
            out.append({"needle": n, "permission": "", "prevalence_pct": 0.0})
    return out


def validate_hypotheses(
    *,
    fam_prev: pd.DataFrame,
    type_prev: pd.DataFrame,
    snapshot: pd.DataFrame,
    specs: Sequence[Mapping[str, Any]] = HYPOTHESIS_SPECS,
) -> pd.DataFrame:
    """Test only statically observable permission hypotheses."""
    type_base = _type_baseline_map(type_prev)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        family = str(spec["family_slug"])
        type_slug = str(spec["type_slug"])
        sample_support = int((snapshot["family_canonical"].astype(str) == family).sum())
        static_yes = bool(spec.get("static_testable", False))
        if not static_yes:
            rows.append(
                {
                    "hypothesis_id": spec["hypothesis_id"],
                    "family_slug": family,
                    "type_slug": type_slug,
                    "statement": spec["statement"],
                    "testable_statically": "no",
                    "observed_permission_evidence": "",
                    "sample_support": sample_support,
                    "family_vs_type_baseline": "",
                    "effect_size_pp": "",
                    "family_balance_result": "",
                    "status": "NOT_TESTABLE_STATICALLY",
                    "limitations": (
                        "Runtime/virtualization/cloud-C2 capability cannot be confirmed "
                        "from static permission declarations alone; absence is not falsification"
                    ),
                }
            )
            continue

        if spec.get("special") == "weak_differentiation":
            # Compare mean absolute divergence of Triada top perms vs type baseline.
            fam_map = _permission_lookup(fam_prev, family)
            if not fam_map or sample_support <= 0:
                status = "NOT_OBSERVED"
                effect = ""
                evidence = ""
            else:
                deltas = []
                for perm, prev in sorted(fam_map.items(), key=lambda x: -x[1])[:25]:
                    base = type_base.get((type_slug, perm), 0.0)
                    deltas.append(abs(prev - float(base)))
                mean_abs = float(np.mean(deltas)) if deltas else 0.0
                effect = round(mean_abs, 3)
                evidence = f"mean_abs_delta_vs_type_baseline_pp={mean_abs:.2f}"
                # Weak differentiation if close to type baseline.
                status = "LOCALLY_SUPPORTED" if mean_abs < 15.0 else "LOCALLY_MIXED"
            rows.append(
                {
                    "hypothesis_id": spec["hypothesis_id"],
                    "family_slug": family,
                    "type_slug": type_slug,
                    "statement": spec["statement"],
                    "testable_statically": "yes",
                    "observed_permission_evidence": evidence,
                    "sample_support": sample_support,
                    "family_vs_type_baseline": evidence,
                    "effect_size_pp": effect,
                    "family_balance_result": "n/a_single_family_type_context",
                    "status": status,
                    "limitations": (
                        "Backdoor type is Triada-dominated in this cohort; "
                        "weak differentiation may reflect type concentration"
                    ),
                }
            )
            continue

        fam_map = _permission_lookup(fam_prev, family)
        matches = _match_needles(fam_map, list(spec.get("permission_needles") or ()))
        # Also family-balance: family vs other families in type for matched perms
        floor = float(spec.get("enrichment_pp") or 10.0)
        supported = 0
        mixed = 0
        absent = 0
        bits = []
        delta_bits = []
        fb_bits = []
        for m in matches:
            perm = m["permission"]
            prev = float(m["prevalence_pct"])
            if not perm or prev <= 0:
                absent += 1
                bits.append(f"{m['needle']}=NOT_OBSERVED")
                continue
            base = float(type_base.get((type_slug, perm), 0.0))
            delta = prev - base
            bits.append(f"{perm}={prev:.1f}%")
            delta_bits.append(f"{perm}:{delta:+.1f}pp")
            type_frame = fam_prev[
                (fam_prev["type_slug"].astype(str) == type_slug)
                & (fam_prev["permission"].map(_norm_perm) == perm)
            ]
            others = type_frame[type_frame["family_canonical"].astype(str) != family]
            other_mean = (
                float(pd.to_numeric(others["prevalence_pct"], errors="coerce").mean())
                if not others.empty
                else float("nan")
            )
            fb_delta = prev - other_mean if pd.notna(other_mean) else float("nan")
            fb_bits.append(
                f"{perm}:vs_others={fb_delta:+.1f}pp" if pd.notna(fb_delta) else f"{perm}:vs_others=na"
            )
            if delta >= floor or (pd.notna(fb_delta) and fb_delta >= floor):
                supported += 1
            elif prev >= HEADLINE_PREV_FLOOR and delta >= 0:
                mixed += 1
            elif prev > 0:
                mixed += 1
            else:
                absent += 1

        if supported >= max(1, len(matches) // 3) and supported > 0:
            status = "LOCALLY_SUPPORTED"
        elif supported > 0 or mixed > 0:
            status = "LOCALLY_MIXED"
        else:
            status = "NOT_OBSERVED"

        limitations = (
            "Static declarations only; runtime-only capabilities may still exist. "
            "NOT_OBSERVED does not falsify public reporting."
        )
        if spec.get("also_runtime_note"):
            limitations += " Overlay/virtualization behavior may leave sparse accessibility tokens."

        rows.append(
            {
                "hypothesis_id": spec["hypothesis_id"],
                "family_slug": family,
                "type_slug": type_slug,
                "statement": spec["statement"],
                "testable_statically": "yes",
                "observed_permission_evidence": "|".join(bits),
                "sample_support": sample_support,
                "family_vs_type_baseline": "|".join(delta_bits),
                "effect_size_pp": (
                    round(
                        float(
                            np.mean(
                                [
                                    float(x.split(":")[1].replace("pp", "").replace("+", ""))
                                    for x in delta_bits
                                ]
                            )
                        ),
                        3,
                    )
                    if delta_bits
                    else ""
                ),
                "family_balance_result": "|".join(fb_bits),
                "status": status,
                "limitations": limitations,
            }
        )
    return pd.DataFrame(rows)


# Dominant-family type-profile sensitivity lives in
# obsidiandroid.reporting.dominant_family_profile_sensitivity


def _render_markdown(
    *,
    identity: Mapping[str, Any],
    inventory: pd.DataFrame,
    external: pd.DataFrame,
    audit: pd.DataFrame,
    hypotheses: pd.DataFrame,
    robustness: pd.DataFrame,
) -> str:
    lines = [
        "# Live-corpus family context",
        "",
        "Evidence-separated corpus context for the completed all-current diagnostic run.",
        "External paraphrases are not local ground truth.",
        "",
        "## Source identity (LOCAL_OBSERVED / manifest)",
        "",
        f"- run_id: `{identity['run_id']}`",
        f"- profile_id: `{identity['profile_id']}`",
        f"- repository_commit: `{identity['repository_commit']}`",
        f"- prepared_sample_count: {identity['prepared_sample_count']}",
        f"- permission_bearing_sample_count: {identity['permission_bearing_sample_count']}",
        f"- governed_known_families: {identity['governed_known_family_count']}",
        f"- observed_family_labels_including_unknown: {identity['observed_family_label_count_including_unknown']}",
        f"- governed_known_types: {identity['governed_known_type_count']}",
        f"- observed_type_slugs_including_unknown: {identity['observed_type_slug_count_including_unknown']}",
        "",
        "## Top-family inventory summary (LOCAL_OBSERVED)",
        "",
        "| family | type | n | years | perm coverage |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for r in inventory.itertuples(index=False):
        years = f"{r.first_observed_year}-{r.last_observed_year}"
        cov = r.permission_evidence_coverage
        cov_s = f"{float(cov):.3f}" if cov != "" and pd.notna(cov) else ""
        lines.append(
            f"| {r.family_canonical} | {r.primary_type_slug} | {int(r.sample_count)} | {years} | {cov_s} |"
        )

    lines.extend(
        [
            "",
            "## Type-assignment audit (LOCAL_AUTHORITY vs EXTERNAL_REPORTED role)",
            "",
            "| family | governed types | public agreement | disagreement |",
            "| --- | --- | --- | --- |",
        ]
    )
    for r in audit.itertuples(index=False):
        lines.append(
            f"| {r.family_canonical} | {r.governed_type_slug_values} | "
            f"{r.public_role_agreement_status} | {r.disagreement_status} |"
        )

    lines.extend(
        [
            "",
            "## External-context matrix (EXTERNAL_REPORTED / IDENTITY_UNCERTAIN)",
            "",
            "See `family_external_context_matrix.csv`. Validation status remains external until "
            "hypothesis tests promote support states.",
            "",
            "## Hypothesis validation (static permissions only)",
            "",
            "| id | family | status | testable |",
            "| --- | --- | --- | --- |",
        ]
    )
    for r in hypotheses.itertuples(index=False):
        lines.append(
            f"| {r.hypothesis_id} | {r.family_slug} | {r.status} | {r.testable_statically} |"
        )

    lines.extend(
        [
            "",
            "## Dominant-family robustness by type",
            "",
            "| type | scenario | excluded | spearman | JSD | maxΔpp | class |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    if not robustness.empty:
        focus = robustness[robustness["scenario"] != "full"]
        for r in focus.itertuples(index=False):
            lines.append(
                f"| {r.type_slug} | {r.scenario} | {r.excluded_families} | "
                f"{r.spearman_vs_full_sw} | {r.js_distance_vs_full_sw} | "
                f"{r.max_abs_prevalence_shift_pp} | {r.robustness_class} |"
            )

    lines.extend(
        [
            "",
            "## Research interpretation",
            "",
            "1. Local facts (counts, prevalences, years, batches) are `LOCAL_OBSERVED`.",
            "2. Governed `family_id` / `type_slug` are `LOCAL_AUTHORITY` and were not modified.",
            "3. Public family writeups remain `EXTERNAL_REPORTED` and are not model features.",
            "4. Dominant families (especially ClayRat, Godfather) can shift type-level permission profiles; "
            "use leave-dominant scenarios before claiming broad type behavior.",
            "5. Missing static signals do not refute runtime-only public claims.",
            "",
            f"Contract version: `{CONTRACT_VERSION}`. Composer: `{COMPOSER_VERSION}`.",
            "",
        ]
    )
    return "\n".join(lines)


def compose_live_corpus_family_context(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
    top_n: int = TOP_FAMILY_N,
) -> dict[str, Any]:
    """Compose durable offline family-context + dominant-family robustness outputs."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    identity = verify_source_identity(run_root, expected_run_id=run_id)
    snap = identity["snapshot"]

    fam_prev = _require_csv(_trends_table(run_root, "permission_prevalence_by_family", run_id))
    type_prev = _require_csv(_trends_table(run_root, "permission_prevalence_by_type", run_id))
    membership = _optional_csv(run_root / "diagnostics" / f"cohort_membership_{run_id}.csv")
    if membership.empty:
        membership = _optional_csv(run_root / "diagnostics" / "cohort_membership.csv")
    type_inventory = _optional_csv(
        run_root
        / "diagnostics"
        / "type_permission_pattern_report"
        / f"type_inventory_{run_id}.csv"
    )
    role_ann = _optional_csv(
        run_root
        / "diagnostics"
        / "type_permission_pattern_report"
        / f"permission_role_annotations_{run_id}.csv"
    )
    pairwise = _optional_csv(
        run_root
        / "diagnostics"
        / "type_permission_pairwise"
        / f"pairwise_headline_{run_id}.csv"
    )
    if pairwise.empty:
        pairwise = _optional_csv(
            run_root
            / "diagnostics"
            / "type_permission_pairwise"
            / f"pairwise_headline_strong_{run_id}.csv"
        )
    audit_path = run_root / "diagnostics" / "permission_feature_audit.csv"
    lane_lookup = permission_lane_lookup(_optional_csv(audit_path)) if audit_path.is_file() else {}

    inventory = build_family_context_inventory(
        snapshot=snap,
        membership=membership,
        fam_prev=fam_prev,
        type_prev=type_prev,
        pairwise_headline=pairwise,
        top_n=top_n,
    )
    external = build_external_context_matrix(snapshot=snap, inventory=inventory)
    type_audit = build_family_type_assignment_audit(snapshot=snap)
    hypotheses = validate_hypotheses(fam_prev=fam_prev, type_prev=type_prev, snapshot=snap)
    robustness = build_dominant_family_type_robustness(
        fam_prev=fam_prev,
        type_inventory=type_inventory,
        role_annotations=role_ann,
        pairwise_headline=pairwise,
        lane_lookup=lane_lookup,
    )

    out_dir = (
        Path(output_dir)
        if output_dir
        else run_root / "diagnostics" / "live_corpus_family_context"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    derived = {
        "family_context_inventory.csv": inventory,
        "family_external_context_matrix.csv": external,
        "family_type_assignment_audit.csv": type_audit,
        "hypothesis_validation.csv": hypotheses,
        "dominant_family_robustness.csv": robustness,
    }
    output_hashes: dict[str, str] = {}
    for name, frame in derived.items():
        path = out_dir / name
        frame.to_csv(path, index=False)
        output_hashes[name] = sha256_file(path)

    md = _render_markdown(
        identity=identity,
        inventory=inventory,
        external=external,
        audit=type_audit,
        hypotheses=hypotheses,
        robustness=robustness,
    )
    md_path = out_dir / "live_corpus_family_context.md"
    md_path.write_text(md, encoding="utf-8")
    output_hashes[md_path.name] = sha256_file(md_path)

    # Input hashes for key sources (no mutation).
    input_paths = {
        "analysis_snapshot": run_root / "diagnostics" / f"analysis_snapshot_{run_id}.csv",
        "permission_prevalence_by_family": _trends_table(
            run_root, "permission_prevalence_by_family", run_id
        ),
        "permission_prevalence_by_type": _trends_table(
            run_root, "permission_prevalence_by_type", run_id
        ),
        "run_manifest": run_root / "run_manifest.json",
    }
    input_hashes = {k: sha256_file(p) for k, p in input_paths.items() if p.is_file()}
    input_hashes.update(identity["input_artifact_hashes"])

    manifest = {
        "composer": "live_corpus_family_context",
        "composer_version": COMPOSER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": generated_at,
        "run_id": identity["run_id"],
        "profile_id": identity["profile_id"],
        "repository_commit_at_run": identity["repository_commit"],
        "repository_commit_at_compose": resolve_git_commit(repo_root) if repo_root else "",
        "prepared_sample_count": identity["prepared_sample_count"],
        "permission_bearing_sample_count": identity["permission_bearing_sample_count"],
        "governed_known_family_count": identity["governed_known_family_count"],
        "observed_family_label_count_including_unknown": identity[
            "observed_family_label_count_including_unknown"
        ],
        "represented_types": identity["represented_types"],
        "run_status": identity["run_status"],
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "evidence_states": list(EVIDENCE_STATES),
        "boundaries": {
            "database_access": False,
            "core_access": False,
            "taxonomy_mutation": False,
            "pipeline_execution": False,
            "source_artifact_mutation": False,
            "external_as_ground_truth": False,
        },
    }
    man_path = out_dir / "manifest.json"
    man_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    man_path.write_text(man_text, encoding="utf-8")
    output_hashes["manifest.json"] = sha256_file(man_path)
    manifest["output_hashes"] = output_hashes
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sha_lines = [f"{digest}  {name}" for name, digest in sorted(output_hashes.items())]
    sha_path = out_dir / "SHA256SUMS"
    sha_path.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    return manifest


__all__ = [
    "AUDIT_FAMILIES",
    "COMPOSER_VERSION",
    "CONTRACT_VERSION",
    "EVIDENCE_STATES",
    "build_external_context_matrix",
    "build_family_context_inventory",
    "build_family_type_assignment_audit",
    "compose_live_corpus_family_context",
    "validate_hypotheses",
    "verify_source_identity",
]
