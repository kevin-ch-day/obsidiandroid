"""Shared batch planning/application; no provider I/O, SQL, taxonomy or runtime rules."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, UTC
import json
from pathlib import Path

from obsidiandroid.assessment.composition import (
    compose_assessment,
    digest,
    source_code_version,
    validate_sha256,
)
from obsidiandroid.assessment.contract import validate_body

META = {"assessment_id", "revision", "previous_assessment_id", "assessed_at_utc"}


class BatchConflict(ValueError):
    """A reviewed head, manifest or evidence constraint changed."""


def utc(value):
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.utcoffset() is None or when.utcoffset().total_seconds() != 0:
        raise ValueError("Evidence cutoff requires explicit UTC")
    return when


def body(record):
    return {k: deepcopy(v) for k, v in record.items() if k not in META}


def engine_body(record):
    value = body(record)
    value["provenance"].pop("batch_context", None)
    return value


def conclusions(record):
    return {
        section: {
            name: {k: value[k] for k in ("state", "value")}
            for name, value in record[section].items()
            if isinstance(value, dict) and "state" in value
        }
        for section in ("artifact", "assessment")
    }


def outcome(record):
    if record["processing"]["status"] == "error":
        return "FAILED_ASSESSMENT"
    if record["processing"]["status"] in {
        "insufficient_evidence",
        "unsupported_artifact",
    }:
        return "ASSESSED_INSUFFICIENT_EVIDENCE"
    states = [record["assessment"][k]["state"] for k in ("type", "family")]
    if "conflict" in states:
        return "ASSESSED_CONFLICTING"
    if states == ["supported", "supported"]:
        return "ASSESSED_SUPPORTED"
    return "ASSESSED_UNRESOLVED"


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def load_batch(manifest_path: Path, snapshot_path: Path):
    """Load bounded JSON files without interpreting paths supplied inside them."""

    def read(path):
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 256 * 1024**2
        ):
            raise ValueError("Batch input must be a bounded regular file")
        return json.loads(path.read_text(), object_pairs_hook=_unique)

    return read(Path(manifest_path)), read(Path(snapshot_path))


class BatchAssessmentService:
    """Plan all rows read-only, then apply reviewed per-artifact transactions.

    A repository supplies current/by_id and append_reviewed(body, expected_id,
    assessed_at_utc). Writers compare the reviewed head inside the artifact lock.
    There is no batch-wide transaction: on failure, completed records remain,
    the failure is classified, and all remaining rows are explicitly not attempted.
    """

    def __init__(self, manifest, snapshot, repository, *, maximum=250):
        if type(maximum) is not int or not 1 <= maximum <= 250:
            raise ValueError("Maximum must be 1..250")
        if (
            manifest.get("contract") != "obsidiandroid.batch-manifest.v1"
            or snapshot.get("contract") != "obsidiandroid.batch-evidence.v1"
        ):
            raise ValueError("Unsupported batch contract")
        hashes = [validate_sha256(s) for s in manifest["hashes"]]
        if not 1 <= len(hashes) <= maximum or len(hashes) != len(set(hashes)):
            raise ValueError("Batch must have unique exact hashes within limit")
        if hashes != manifest["hashes"]:
            raise ValueError("Manifest hashes must be canonical lowercase")
        cutoff = utc(manifest["evidence_cutoff_at"])
        if cutoff > datetime.now(UTC):
            raise ValueError("Evidence cutoff cannot be in the future")
        entries = snapshot["entries"]
        if (
            digest(entries) != snapshot["content_sha256"]
            or snapshot["content_sha256"] != manifest["snapshot_digest"]
        ):
            raise ValueError("Evidence snapshot digest mismatch")
        packets = {p["sha256"]: p for p in entries}
        if len(packets) != len(entries) or set(packets) != set(hashes):
            raise ValueError("Evidence snapshot scope mismatch")
        pins = manifest.get("pinned_revisions", {})
        if not set(pins) <= set(hashes):
            raise ValueError("Pinned revisions outside scope")
        for s, aid in pins.items():
            validate_sha256(aid)
        for s in hashes:
            p = packets[s]
            if (
                p["evidence_cutoff_at"] != manifest["evidence_cutoff_at"]
                or p["engine_evidence"]["sha256"] != s
            ):
                raise ValueError("Evidence identity/cutoff mismatch")
            catalog = p["engine_evidence"].get("catalog", [])
            if (
                len(catalog) != 1
                or catalog[0].get("sha256") != s
                or not catalog[0].get("sample_id")
            ):
                raise ValueError(
                    "Every batch hash must be already admitted with one exact catalog identity"
                )
            if p["engine_evidence"].get("errors"):
                raise ValueError(
                    "Source extraction errors require review before batching"
                )
            static = p["context"].get("static_baseline")
            if static and (
                not static.get("exact_bytes_verified") or not static.get("sha256")
            ):
                raise ValueError("Unbound static evidence")
            if s in pins and p["engine_evidence"].get("scytale", {}).get("dynamic"):
                raise ValueError("Frozen pilot cannot include runtime evidence")
        self.manifest = deepcopy(manifest)
        self.packets = deepcopy(packets)
        self.hashes = hashes
        self.repository = repository
        self.code_version = source_code_version()

    def _proposal(self, sha):
        packet = self.packets[sha]
        result = compose_assessment(
            sha, packet["engine_evidence"], code_version=self.code_version
        )
        context = packet["context"]
        result["provenance"]["batch_context"] = {
            "contract": "obsidiandroid.batch-context.v1",
            "evidence_cutoff_at": packet["evidence_cutoff_at"],
            "snapshot_reference": self.manifest["snapshot_reference"],
            "snapshot_digest": self.manifest["snapshot_digest"],
            "packet_sha256": digest(packet),
            "context_digest": digest(context),
            "static_baseline_reference": context.get("static_baseline"),
            "artifact_classification": context["artifact_classification"],
            "artifact_identity_basis": context["artifact_identity_basis"],
            "source_claim_policy": "Attributed evidence only; source claims do not promote V1 family/type",
        }
        return result

    def plan(self):
        rows = []
        for sha in self.hashes:
            current = self.repository.current(sha)
            proposed = self._proposal(sha)
            pin = self.manifest.get("pinned_revisions", {}).get(sha)
            needed = False
            if pin:
                if (
                    current is None
                    or current["assessment_id"] != pin
                    or self.repository.by_id(pin) != current
                ):
                    raise BatchConflict("Frozen pilot revision drift")
                action = "RETAIN_PINNED"
                change = (
                    "CURRENT_ASSESSMENT_STILL_VALID"
                    if engine_body(current) == engine_body(proposed)
                    else "NEW_EVIDENCE_AVAILABLE"
                )
                reason = "Dedicated pre-runtime revision remains frozen; broader context is retained separately"
                proposed = body(current)
            elif current is None:
                action, change, needed = "CREATE", "NO_ASSESSMENT", True
                reason = "No current assessment; exact admitted identity evaluated with explicit cutoff"
            else:
                old_context = (
                    current["provenance"].get("batch_context", {}).get("context_digest")
                )
                if (
                    engine_body(current) == engine_body(proposed)
                    and old_context
                    == proposed["provenance"]["batch_context"]["context_digest"]
                ):
                    action, change = "REUSE", "CURRENT_ASSESSMENT_STILL_VALID"
                    reason = "Same engine evidence and normalized context; time or cohort reference alone does not justify a revision"
                    proposed = body(current)
                else:
                    action, needed = "APPEND", True
                    change = (
                        "MATERIAL_ASSESSMENT_CHANGE"
                        if conclusions(current) != conclusions(proposed)
                        else "EVIDENCE_ADDED_NO_CONCLUSION_CHANGE"
                    )
                    reason = "Engine evidence or normalized source/static context differs; old revision remains immutable"
            validate_body(proposed, datetime.now(UTC).isoformat())
            rows.append(
                {
                    "sha256": sha,
                    "expected_current_id": current["assessment_id"]
                    if current
                    else None,
                    "action": action,
                    "change_state": change,
                    "new_revision_needed": needed,
                    "reason": reason,
                    "proposed_body": proposed,
                    "body_digest": digest(proposed),
                    "evaluation_state": outcome(proposed),
                    "evidence_completeness": self.packets[sha]["context"][
                        "permission_coverage"
                    ],
                }
            )
        plan = {
            "contract": "obsidiandroid.batch-plan.v1",
            "manifest_digest": digest(self.manifest),
            "snapshot_digest": self.manifest["snapshot_digest"],
            "code_version": self.code_version,
            "evidence_cutoff_at": self.manifest["evidence_cutoff_at"],
            "rows": rows,
            "clean": all(r["evaluation_state"] != "FAILED_ASSESSMENT" for r in rows),
        }
        plan["plan_digest"] = digest(plan)
        return plan

    def apply(self, plan, *, expected_plan_digest, emit=None):
        """Apply exactly the reviewed plan; refuse stale heads and stop on failure."""
        unsigned = {k: v for k, v in plan.items() if k != "plan_digest"}
        if (
            digest(unsigned) != expected_plan_digest
            or plan["plan_digest"] != expected_plan_digest
        ):
            raise BatchConflict("Reviewed plan digest mismatch")
        if (
            plan["manifest_digest"] != digest(self.manifest)
            or plan["code_version"] != source_code_version()
            or not plan["clean"]
        ):
            raise BatchConflict("Manifest/code changed or dry run not clean")
        # Full recomposition catches a syntactically signed but altered proposal.
        if self.plan() != plan:
            raise BatchConflict("Plan/head/evidence changed after review")
        result = {
            "contract": "obsidiandroid.batch-receipt.v1",
            "plan_digest": expected_plan_digest,
            "status": "running",
            "rows": [],
        }
        stopped = False
        for row in plan["rows"]:
            sha = row["sha256"]
            entry = {"sha256": sha, "action": row["action"]}
            if stopped:
                entry.update(
                    evaluation_state="NOT_ATTEMPTED_AFTER_FAILURE",
                    persistence="not_attempted",
                )
            else:
                try:
                    if row["new_revision_needed"]:
                        record = self.repository.append_reviewed(
                            row["proposed_body"],
                            expected_id=row["expected_current_id"],
                            assessed_at_utc=datetime.now(UTC).isoformat(),
                        )
                    else:
                        record = self.repository.current(sha)
                        if (
                            record is None
                            or record["assessment_id"] != row["expected_current_id"]
                        ):
                            raise BatchConflict("Retained revision changed")
                    if digest(body(record)) != row["body_digest"]:
                        raise BatchConflict(
                            "Persisted body differs from reviewed proposal"
                        )
                    entry.update(
                        evaluation_state=outcome(record),
                        persistence="written"
                        if row["new_revision_needed"]
                        else "retained",
                        assessment_id=record["assessment_id"],
                        revision=record["revision"],
                        assessed_at_utc=record["assessed_at_utc"],
                    )
                except Exception as exc:
                    stopped = True
                    entry.update(
                        evaluation_state="FAILED_ASSESSMENT",
                        error_type=type(exc).__name__,
                        persistence="unknown_requires_inspection",
                    )
                    try:
                        observed = self.repository.current(sha)
                        if (observed["assessment_id"] if observed else None) == row[
                            "expected_current_id"
                        ]:
                            entry["persistence"] = "unchanged_after_failure"
                        elif observed and digest(body(observed)) == row["body_digest"]:
                            entry["persistence"] = "reviewed_body_visible_after_error"
                            entry["assessment_id"] = observed["assessment_id"]
                    except Exception:
                        pass
            result["rows"].append(entry)
            if emit is not None:
                emit(deepcopy(entry))
        result["status"] = "stopped" if stopped else "complete"
        return result
