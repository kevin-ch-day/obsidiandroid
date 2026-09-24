"""Verify and inspect frozen cohort metadata without live DB or provider access."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path, PurePosixPath

from obsidiandroid.assessment.composition import digest, validate_sha256
from obsidiandroid.assessment.contract import validate_body
from .service import body, utc


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def _indexed(rows, key):
    result = {}
    for row in rows:
        identity = row[key]
        if identity in result:
            raise ValueError("Duplicate cohort identity")
        result[identity] = row
    return result


class FrozenCohort:
    """Load a caller-pinned seal and cross-check the contained assessment mapping.

    External references are displayed but never opened. The object reports the
    frozen revision, not live database freshness. Input bytes are retained after
    hashing so later reads cannot silently consume a changed on-disk export.
    """

    def __init__(self, directory, *, expected_checksums_sha256):
        root = Path(directory)
        expected = validate_sha256(expected_checksums_sha256)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Cohort must be a regular directory")
        root = root.resolve()
        seal = root / "checksums.sha256"
        if seal.is_symlink() or not seal.is_file():
            raise ValueError("Missing regular checksum manifest")
        if seal.stat().st_size > 1024 * 1024:
            raise ValueError("Oversized checksum manifest")
        raw = seal.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Checksum manifest pin mismatch")
        contents = {}
        total = 0
        for line in raw.decode().splitlines():
            checksum, name = line.split("  ", 1)
            validate_sha256(checksum)
            relative = PurePosixPath(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or str(relative) != name
                or name in contents
                or "\\" in name
            ):
                raise ValueError("Unsafe or duplicate sealed path")
            target = root
            for component in relative.parts:
                target = target / component
                if target.is_symlink():
                    raise ValueError("Symlink in sealed path")
            if not target.is_file() or target.stat().st_size > 256 * 1024**2:
                raise ValueError("Missing or oversized sealed file")
            total += target.stat().st_size
            if total > 512 * 1024**2:
                raise ValueError("Cohort exceeds bounded size")
            data = target.read_bytes()
            if hashlib.sha256(data).hexdigest() != checksum:
                raise ValueError("Sealed file digest mismatch")
            contents[name] = data
        if not contents:
            raise ValueError("Empty seal")
        self._contents = contents
        self.seal_sha256 = expected
        self.manifest = _json(contents["cohort_manifest.json"])
        self._rows = _indexed(self._tsv("broad_cohort_snapshot.tsv"), "sha256")
        self._records = _indexed(
            [_json(line) for line in contents["assessments.jsonl"].splitlines()],
            "assessment_id",
        )
        self._pilot = _indexed(self._tsv("pilot_predynamic_revisions.tsv"), "sha256")
        self._packets = {}
        manifest = self.manifest
        links = {
            "snapshot_tsv_sha256": "broad_cohort_snapshot.tsv",
            "batch_evidence_sha256": "batch_evidence.json",
            "selection_manifest_sha256": "batch_manifest.json",
            "exclusion_ledger_sha256": "exclusion_ledger.json",
        }
        for field, name in links.items():
            if hashlib.sha256(contents[name]).hexdigest() != manifest[field]:
                raise ValueError("Cohort manifest link mismatch")
        selection = _json(contents["batch_manifest.json"])
        snapshot = _json(contents["batch_evidence.json"])
        if (
            digest(snapshot["entries"]) != snapshot["content_sha256"]
            or selection["snapshot_digest"] != snapshot["content_sha256"]
        ):
            raise ValueError("Canonical evidence snapshot digest mismatch")
        packets = _indexed(snapshot["entries"], "sha256")
        if (
            not 1 <= len(self._rows) <= 250
            or len(self._rows) != manifest["count"]
            or len(self._records) != len(self._rows)
            or set(packets) != set(self._rows)
            or len(selection["hashes"]) != len(self._rows)
            or set(selection["hashes"]) != set(self._rows)
        ):
            raise ValueError("Cohort scope mismatch")
        if set(self._pilot) != set(selection.get("pinned_revisions", {})):
            raise ValueError("Pilot scope mismatch")
        for sha, row in self._rows.items():
            if validate_sha256(sha) != sha:
                raise ValueError("Noncanonical cohort SHA")
            record = self._records[row["assessment_id"]]
            validate_body(body(record), record["assessed_at_utc"])
            expected_id = digest(
                {
                    "artifact_sha256": sha,
                    "input_digest": digest(body(record)),
                    "revision": record["revision"],
                    "previous_assessment_id": record["previous_assessment_id"],
                }
            )
            if record["assessment_id"] != expected_id:
                raise ValueError("Immutable assessment digest mismatch")
            if row["cohort_id"] != manifest["cohort_id"]:
                raise ValueError("Cohort identity mismatch")
            if (
                record["artifact"]["sha256"] != sha
                or record["revision"] != int(row["revision"])
                or record["assessed_at_utc"] != row["assessment_created_at"]
            ):
                raise ValueError("Assessment revision mapping mismatch")
            cutoff = utc(row["evidence_cutoff_at"])
            if cutoff > utc(record["assessed_at_utc"]):
                raise ValueError("Evidence cutoff postdates assessment")
            packet_bytes = contents[row["packet_file"]]
            if hashlib.sha256(packet_bytes).hexdigest() != row["packet_file_sha256"]:
                raise ValueError("Packet link mismatch")
            packet = _json(packet_bytes)
            if packet != packets[sha] or packet["engine_evidence"]["sha256"] != sha:
                raise ValueError("Normalized packet identity mismatch")
            if packet["engine_evidence"].get("scytale", {}).get("dynamic"):
                raise ValueError("Runtime evidence in pre-runtime cohort")
            context = record["provenance"].get("batch_context")
            if sha in self._pilot:
                pin = self._pilot[sha]
                if (
                    pin["assessment_id"] != record["assessment_id"]
                    or selection["pinned_revisions"][sha] != record["assessment_id"]
                    or int(pin["revision"]) != record["revision"]
                    or pin["evidence_cutoff_at"] != row["evidence_cutoff_at"]
                    or pin["cutoff_basis"] != row["cutoff_basis"]
                    or pin["snapshot_file_sha256"]
                    != row["assessment_snapshot_file_sha256"]
                ):
                    raise ValueError("Frozen pilot mapping mismatch")
            elif not context or (
                context["evidence_cutoff_at"] != row["evidence_cutoff_at"]
                or context["packet_sha256"] != digest(packet)
                or context["snapshot_digest"] != snapshot["content_sha256"]
            ):
                raise ValueError("Stored cutoff or evidence binding mismatch")
            self._packets[sha] = packet

    def _tsv(self, name):
        reader = csv.DictReader(
            io.StringIO(self._contents[name].decode()), delimiter="\t"
        )
        if not reader.fieldnames or len(reader.fieldnames) != len(
            set(reader.fieldnames)
        ):
            raise ValueError("Duplicate or missing TSV header")
        return list(reader)

    def inspect(self, sha):
        """Return the frozen assessment and explicitly sourced cutoff context."""
        sha = validate_sha256(sha)
        row = self._rows[sha]
        record = self._records[row["assessment_id"]]
        packet = self._packets[sha]
        return deepcopy(
            {
                "sha256": sha,
                "assessment": record,
                "cutoff": {
                    "evidence_cutoff_at": row["evidence_cutoff_at"],
                    "basis": row["cutoff_basis"],
                    "stored_in_revision": "batch_context" in record["provenance"],
                    "snapshot_reference": row["assessment_snapshot_reference"],
                    "snapshot_file_sha256": row["assessment_snapshot_file_sha256"],
                },
                "context": packet["context"],
                "pilot_original_revision": sha in self._pilot,
                "scope": "Frozen snapshot only; live database and external files not checked",
                "checksums_sha256": self.seal_sha256,
            }
        )

    def followups(self):
        """Create review-only exact-hash tasks; never propose unscoped SQL writes."""
        result = []
        for sha in sorted(self._rows):
            packet = self._packets[sha]
            context = packet["context"]
            static = context.get("static_baseline")
            if not static:
                continue
            record = self._records[self._rows[sha]["assessment_id"]]
            tasks = []
            if static["status"] != "VALID_APK":
                tasks.append(("STATIC_PARSE_REVIEW", "ScytaleDroid", []))
            else:
                if record["processing"]["status"] == "unsupported_artifact":
                    tasks.append(("CATALOG_IDENTITY_BINDING_REVIEW", "Erebus", []))
                coverage = context["permission_coverage"]
                if coverage["projection_state"] in {"ABSENT", "PARTIAL"}:
                    tasks.append(
                        (
                            "SOURCE_AWARE_PERMISSION_PROJECTION_REVIEW",
                            "Erebus / Permission Intel",
                            coverage["missing_declared_tokens"],
                        )
                    )
                if static["compatibility"] == "UNKNOWN":
                    tasks.append(("STATIC_COMPATIBILITY_REVIEW", "ScytaleDroid", []))
            for kind, owner, tokens in tasks:
                result.append(
                    {
                        "sha256": sha,
                        "kind": kind,
                        "owner": owner,
                        "assessment_id": record["assessment_id"],
                        "static_baseline_reference": static["path"],
                        "static_baseline_sha256": static["sha256"],
                        "missing_declared_tokens": deepcopy(tokens),
                        "pilot_original_revision": sha in self._pilot,
                        "scope": "Review only; no source mutation or acquisition authorized",
                        "external_baseline_reverified": False,
                    }
                )
        return result

    def summary(self):
        """Report verified scope and review workload without claiming live health."""
        tasks = self.followups()
        return {
            "contract": "obsidiandroid.frozen-cohort-inspection.v1",
            "cohort_id": self.manifest["cohort_id"],
            "hashes_verified": len(self._rows),
            "sealed_files_verified": len(self._contents),
            "pilot_revisions_verified": len(self._pilot),
            "cutoff_basis_counts": dict(
                Counter(r["cutoff_basis"] for r in self._rows.values())
            ),
            "followup_counts": dict(Counter(r["kind"] for r in tasks)),
            "followup_unique_hashes": len({r["sha256"] for r in tasks}),
            "checksums_sha256": self.seal_sha256,
            "live_database_checked": False,
            "external_references_checked": False,
            "mutations_performed": False,
        }
