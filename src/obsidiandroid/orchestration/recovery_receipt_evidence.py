"""Read-only verification of Erebus PI recovery plan/sample receipt bindings."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import pandas as pd


def _digest(value: object, *, newline: bool = False) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((payload + ("\n" if newline else "")).encode("utf-8")).hexdigest()


def _read_private_json(path: Path, *, label: str) -> dict:
    """Read one immutable evidence file through a nonblocking, no-follow fd."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            metadata = os.fstat(handle.fileno())
            if (not stat.S_ISREG(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_uid != os.geteuid()):
                raise ValueError(f"{label} must be a private regular file")
            document = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return document


def _action_source_binding(action: dict) -> dict:
    fields = (
        "sample_id", "sha256", "source_event_id", "source_bounded_result_id",
        "source_execution_id", "source_reservation_id", "source_ingest_id",
        "source_row_identity_digest", "source_payload_hash",
        "source_evidence_receipt_sha256", "raw_permission_names_digest",
        "projected_permission_names_digest", "source_raw_permission_detail_digest",
    )
    return {
        **{field: action.get(field) for field in fields},
        "projected_permission_names_digest_from_plan": _digest(
            action["projected_permission_names"]
        ),
        "observation_origin": "provider_reported_virustotal_androguard",
    }


def load_recovery_receipt_evidence(
    plan_path: Path,
    receipt_directory: Path,
    *,
    expected_plan_digest: str,
    expected_manifest_digest: str | None = None,
    expected_selection_digest: str | None = None,
) -> pd.DataFrame:
    """Verify immutable completed receipts and derive exact provider token rows.

    This is a consumer-side evidence check, not a substitute for Erebus's live
    preflight or production execution gate. A plan action without a completed
    bound receipt contributes no positive provider evidence.
    """
    plan = _read_private_json(plan_path, label="recovery plan")
    if not isinstance(plan, dict) or plan.get("plan_digest") != expected_plan_digest:
        raise ValueError("recovery plan identity differs")
    if _digest({k: v for k, v in plan.items() if k != "plan_digest"}, newline=True) != expected_plan_digest:
        raise ValueError("recovery plan digest differs")
    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise ValueError("recovery plan action set is invalid")
    if (expected_manifest_digest is None) != (expected_selection_digest is None):
        raise ValueError("exact recovery manifest/selection binding is incomplete")
    by_digest: dict[str, dict] = {}
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("recovery plan action is invalid")
        digest = action.get("action_digest")
        if _digest({k: v for k, v in action.items() if k != "action_digest"}, newline=True) != digest:
            raise ValueError("recovery action digest differs")
        if digest in by_digest:
            raise ValueError("duplicate recovery action")
        by_digest[digest] = action
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in sorted(receipt_directory.glob("pi-production-sample-*.json")):
        receipt = _read_private_json(path, label="recovery sample receipt")
        if not isinstance(receipt, dict) or receipt.get("receipt_format") != "erebus-pi-production-sample-receipt-v1":
            raise ValueError("recovery sample receipt format differs")
        if _digest({k: v for k, v in receipt.items() if k != "receipt_digest"}) != receipt.get("receipt_digest"):
            raise ValueError("recovery sample receipt digest differs")
        digest = str(receipt.get("action_digest") or "")
        action = by_digest.get(digest)
        if action is None or digest in seen:
            raise ValueError("recovery receipt action is extra or duplicated")
        if path.name != f"pi-production-sample-{digest}.json":
            raise ValueError("recovery receipt filename differs from action")
        seen.add(digest)
        result = receipt.get("result")
        if (
            receipt.get("plan_digest") != expected_plan_digest
            or receipt.get("plan_core_digest") != plan.get("plan_core_digest")
            or receipt.get("single_use_execution_id") != plan.get("single_use_execution_id")
            or receipt.get("provider_requests") != 0
            or receipt.get("primary_catalog_mutations") != 0
            or receipt.get("execution_scope") != "PRODUCTION_PI_ONLY_RECOVERY"
            or receipt.get("production_effect") != "local_permission_intel_materialization"
            or (
                expected_manifest_digest is not None
                and receipt.get("exact_manifest_digest") != expected_manifest_digest
            )
            or (
                expected_selection_digest is not None
                and receipt.get("exact_selection_digest") != expected_selection_digest
            )
            or not isinstance(result, dict)
            or result.get("sample_id") != action.get("sample_id")
            or result.get("action_digest") != digest
            or result.get("classification") not in {"COMPLETED", "ALREADY_PRESENT"}
            or result.get("target_pi_catalog") != plan.get("pi_catalog")
            or result.get("source_primary_catalog") != plan.get("primary_catalog")
            or result.get("provider_requests") != 0
            or result.get("primary_mutations") != 0
            or (
                expected_manifest_digest is not None
                and receipt.get("action_source_binding") != _action_source_binding(action)
            )
            or (
                receipt.get("action_source_binding") is not None
                and receipt.get("action_source_binding") != _action_source_binding(action)
            )
        ):
            raise ValueError("recovery sample receipt binding differs")
        token_evidence = action.get("token_evidence")
        if not isinstance(token_evidence, list):
            raise ValueError("recovery action token provenance is absent")
        for token in action.get("projected_permission_names", []):
            origins = [item for item in token_evidence if isinstance(item, dict)
                       and item.get("projected_pi_token") == token]
            if not origins:
                raise ValueError("recovery projected token lacks raw provider evidence")
            for origin in origins:
                rows.append({
                "sample_id": action["sample_id"],
                "sha256": action["sha256"],
                "permission_string": token,
                "raw_token": origin["provider_token"],
                "projection_policy_version": origin["projection_policy_version"],
                "analysis_date_utc": action["analysis_date_utc"],
                "plan_core_digest": plan["plan_core_digest"],
                "batch_id": plan["single_use_execution_id"],
                "action_digest": digest,
                "receipt_digest": receipt["receipt_digest"],
                })
    return pd.DataFrame(rows, columns=[
        "sample_id", "sha256", "permission_string", "raw_token",
        "projection_policy_version", "analysis_date_utc",
        "plan_core_digest", "batch_id", "action_digest", "receipt_digest",
    ])


def reconcile_provider_observations(
    samples: pd.DataFrame, observations: pd.DataFrame, receipts: pd.DataFrame
) -> pd.DataFrame:
    """Require catalog SHA, exact PI token, VT event, plan core and batch match."""
    required = {
        "sample_id", "permission_string", "observation_source",
        "recovery_plan_core", "recovery_batch_id", "event_analysis_date_utc",
        "event_source_system", "event_source_engine", "canonical_permission",
        "current_evidence_state", "current_identifier_kind", "unresolved_conflict_count",
    }
    if not {"sample_id", "sha256"} <= set(samples) or not required <= set(observations):
        raise ValueError("provider observation join contract is incomplete")
    if samples["sample_id"].duplicated().any() or samples["sha256"].duplicated().any():
        raise ValueError("catalog sample identity is duplicated")
    sha_by_id = dict(zip(samples["sample_id"], samples["sha256"], strict=True))
    receipt_by_key: dict[tuple[object, object, object, object], list[dict]] = {}
    for item in receipts.to_dict("records"):
        key = (item["sample_id"], item["permission_string"],
               item["analysis_date_utc"], item["plan_core_digest"])
        receipt_by_key.setdefault(key, []).append(item)
    rows: list[dict[str, object]] = []
    # The event join can return several historical VT events for one PI row.
    # A mismatched older event is not a second unresolved permission when a
    # receipt-bound event for the same exact observation is also present.
    observation_groups: dict[tuple[object, str], list[dict]] = {}
    for item in observations.to_dict("records"):
        sample_id = item["sample_id"]
        if sample_id not in sha_by_id:
            raise ValueError("PI observation is outside selected catalog samples")
        projected = str(item["permission_string"] or "")
        observation_groups.setdefault((sample_id, projected), []).append(item)
    for (sample_id, projected), group in observation_groups.items():
        matched: list[tuple[dict, dict]] = []
        for item in group:
            key = (sample_id, projected, item["event_analysis_date_utc"],
                   item["recovery_plan_core"])
            for candidate in receipt_by_key.get(key, []):
                if (candidate["sha256"] == sha_by_id[sample_id]
                        and candidate["batch_id"] == item["recovery_batch_id"]
                        and item["event_source_system"] == "virustotal"
                        and item["event_source_engine"] == "androguard"
                        and item["observation_source"] == "virustotal"):
                    matched.append((item, candidate))
        if matched:
            for item, match in matched:
                canonical_value = item.get("canonical_permission")
                canonical = (
                    "" if pd.isna(canonical_value) else str(canonical_value)
                )
                conflict_value = item.get("unresolved_conflict_count")
                conflict_count = (
                    0 if pd.isna(conflict_value) else int(conflict_value)
                )
                identity_ok = (
                    item["current_evidence_state"] == "ACCEPTED_CANONICAL"
                    and item["current_identifier_kind"] == "PERMISSION"
                    and canonical == projected
                    and conflict_count == 0
                )
                if identity_ok:
                    identity_status = "ACCEPTED_EXACT"
                elif conflict_count:
                    identity_status = "CONFLICT"
                elif (
                    canonical and canonical != projected
                    and item["current_evidence_state"] == "ACCEPTED_CANONICAL"
                    and item["current_identifier_kind"] == "PERMISSION"
                ):
                    identity_status = "UNRESOLVED_ALIAS"
                else:
                    identity_status = "UNRESOLVED_IDENTITY"
                rows.append({
                    "sample_id": sample_id, "sha256": sha_by_id[sample_id],
                    "raw_token": match["raw_token"], "projected_token": projected,
                    "observation_origin": "provider", "source_verified": True,
                    "source_receipt_digest": match["receipt_digest"],
                    "event_verified": True,
                    "identity_status": identity_status,
                    "canonical_token": canonical,
                    "alias_release_digest": "",
                })
        else:
            item = group[0]
            rows.append({
                "sample_id": sample_id, "sha256": sha_by_id[sample_id],
                "raw_token": projected, "projected_token": projected,
                "observation_origin": (
                    "provider" if item["observation_source"] == "virustotal"
                    else "unknown"
                ),
                "source_verified": False, "identity_status": "UNRESOLVED_SOURCE",
                "source_receipt_digest": "", "event_verified": False,
                "canonical_token": "", "alias_release_digest": "",
            })
    return pd.DataFrame(rows, columns=[
        "sample_id", "sha256", "raw_token", "projected_token",
        "observation_origin", "source_verified", "identity_status",
        "source_receipt_digest", "event_verified", "canonical_token",
        "alias_release_digest",
    ]).drop_duplicates(ignore_index=True)
