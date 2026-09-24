"""Frozen cohort trust, cutoff attribution and review-only workload tests."""

import csv
import hashlib
import json

import pytest

from obsidiandroid.assessment.composition import compose_assessment
from obsidiandroid.assessment_batch import BatchAssessmentService
from obsidiandroid.assessment_batch.cohort import FrozenCohort
from obsidiandroid.cli.assessment_cohort import main
from test_assessment_batch import Repo, inputs, manifest, snapshot, CUTOFF


def filehash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value))


def write_tsv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def seal(root):
    links = {
        "snapshot_tsv_sha256": "broad_cohort_snapshot.tsv",
        "batch_evidence_sha256": "batch_evidence.json",
        "selection_manifest_sha256": "batch_manifest.json",
        "exclusion_ledger_sha256": "exclusion_ledger.json",
    }
    value = json.loads((root / "cohort_manifest.json").read_text())
    value.update({k: filehash(root / v) for k, v in links.items()})
    write_json(root / "cohort_manifest.json", value)
    files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"
    )
    (root / "checksums.sha256").write_text(
        "".join(f"{filehash(p)}  {p.relative_to(root)}\n" for p in files)
    )
    return filehash(root / "checksums.sha256")


@pytest.fixture
def packet(tmp_path):
    root = tmp_path / "packet"
    root.mkdir()
    (root / "packets").mkdir()
    _, snap = inputs(2)
    entries = snap["entries"]
    for p in entries:
        p["context"]["permission_coverage"].update(
            declared_count=2,
            observed_count=1,
            projection_state="PARTIAL",
            missing_declared_tokens=["android.permission.CAMERA"],
        )
        p["context"]["static_baseline"] = {
            "status": "VALID_APK",
            "compatibility": "UNKNOWN",
            "exact_bytes_verified": True,
            "path": "/external/not-opened.json",
            "sha256": "c" * 64,
        }
    # A valid APK baseline does not silently repair unsupported catalog identity.
    entries[0]["engine_evidence"]["catalog"][0]["platform"] = "unknown"
    entries[0]["engine_evidence"]["catalog"][0]["artifact_type"] = None
    m, snap = manifest(entries), snapshot(entries)
    repo = Repo(tmp_path / "store")
    old = repo.store.append(
        compose_assessment(entries[0]["sha256"], entries[0]["engine_evidence"]),
        assessed_at_utc="2026-09-21T00:01:00+00:00",
    )
    m["pinned_revisions"] = {entries[0]["sha256"]: old["assessment_id"]}
    svc = BatchAssessmentService(m, snap, repo)
    plan = svc.plan()
    svc.apply(plan, expected_plan_digest=plan["plan_digest"])
    records = [repo.current(p["sha256"]) for p in entries]
    rows = []
    pins = []
    for p, r in zip(entries, records):
        name = "packets/" + p["sha256"] + ".json"
        write_json(root / name, p)
        row = {
            "cohort_id": "fixture",
            "sha256": p["sha256"],
            "assessment_id": r["assessment_id"],
            "revision": r["revision"],
            "assessment_created_at": r["assessed_at_utc"],
            "evidence_cutoff_at": CUTOFF,
            "cutoff_basis": "ORIGINAL_FROZEN_SNAPSHOT_CAPTURE_UPPER_BOUND"
            if r == old
            else "STORED_BATCH_SNAPSHOT_CUTOFF",
            "assessment_snapshot_reference": "/external/not-opened.json",
            "assessment_snapshot_file_sha256": "d" * 64,
            "packet_file": name,
            "packet_file_sha256": filehash(root / name),
        }
        rows.append(row)
        if r == old:
            pins.append(
                {
                    "sha256": p["sha256"],
                    "assessment_id": r["assessment_id"],
                    "revision": r["revision"],
                    "evidence_cutoff_at": CUTOFF,
                    "cutoff_basis": row["cutoff_basis"],
                    "snapshot_file_sha256": "d" * 64,
                }
            )
    write_tsv(root / "broad_cohort_snapshot.tsv", rows)
    write_tsv(root / "pilot_predynamic_revisions.tsv", pins)
    (root / "assessments.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records)
    )
    write_json(root / "batch_manifest.json", m)
    write_json(root / "batch_evidence.json", snap)
    write_json(root / "cohort_manifest.json", {"cohort_id": "fixture", "count": 2})
    write_json(root / "exclusion_ledger.json", {})
    return root, seal(root), entries, records


def test_resolves_original_cutoff_without_rewriting_legacy(packet):
    root, pin, entries, records = packet
    before = filehash(root / "assessments.jsonl")
    c = FrozenCohort(root, expected_checksums_sha256=pin)
    old = c.inspect(entries[0]["sha256"])
    new = c.inspect(entries[1]["sha256"])
    assert old["assessment"] == records[0] and not old["cutoff"]["stored_in_revision"]
    assert old["cutoff"]["basis"] == "ORIGINAL_FROZEN_SNAPSHOT_CAPTURE_UPPER_BOUND"
    assert new["cutoff"]["stored_in_revision"]
    assert (
        c.summary()["hashes_verified"] == 2
        and not c.summary()["external_references_checked"]
    )
    assert filehash(root / "assessments.jsonl") == before
    # Returned data cannot mutate the inspector's verified state.
    old["assessment"]["revision"] = 99
    assert c.inspect(entries[0]["sha256"])["assessment"]["revision"] == 1


def test_followups_bind_hash_baseline_and_tokens_without_writes(packet):
    root, pin, _, _ = packet
    c = FrozenCohort(root, expected_checksums_sha256=pin)
    assert c.summary()["followup_counts"] == {
        "CATALOG_IDENTITY_BINDING_REVIEW": 1,
        "SOURCE_AWARE_PERMISSION_PROJECTION_REVIEW": 2,
        "STATIC_COMPATIBILITY_REVIEW": 2,
    }
    task = next(
        t
        for t in c.followups()
        if t["kind"] == "SOURCE_AWARE_PERMISSION_PROJECTION_REVIEW"
    )
    assert task["missing_declared_tokens"] == ["android.permission.CAMERA"]
    assert (
        task["static_baseline_sha256"] == "c" * 64
        and not task["external_baseline_reverified"]
    )


@pytest.mark.parametrize(
    "case", ["pin", "bytes", "duplicate_path", "traversal", "symlink"]
)
def test_bad_seal_and_unsafe_paths_refused(packet, case):
    root, pin, _, _ = packet
    if case == "pin":
        pin = "0" * 64
    elif case == "bytes":
        (root / "assessments.jsonl").write_text("{}\n")
    elif case == "symlink":
        target = root / "exclusion_ledger.json"
        target.unlink()
        target.symlink_to(root / "cohort_manifest.json")
    else:
        line = (root / "checksums.sha256").read_text().splitlines()[0]
        with (root / "checksums.sha256").open("a") as f:
            f.write(
                line + "\n" if case == "duplicate_path" else "0" * 64 + "  ../escape\n"
            )
        pin = filehash(root / "checksums.sha256")
    with pytest.raises(ValueError):
        FrozenCohort(root, expected_checksums_sha256=pin)


@pytest.mark.parametrize(
    "case",
    [
        "revision",
        "cutoff",
        "pilot_pin",
        "scope",
        "duplicate_record",
        "duplicate_header",
    ],
)
def test_resealed_semantic_inconsistencies_refused(packet, case):
    root, _, _, _ = packet
    if case in {"revision", "cutoff", "scope", "duplicate_header"}:
        p = root / "broad_cohort_snapshot.tsv"
        with p.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        if case == "revision":
            rows[0]["revision"] = "2"
        elif case == "cutoff":
            rows[0]["evidence_cutoff_at"] = "2026-09-21T00:00:01+00:00"
        elif case == "scope":
            rows.pop()
        write_tsv(p, rows)
        if case == "duplicate_header":
            p.write_text(
                p.read_text().replace("cohort_id\tsha256", "sha256\tsha256", 1)
            )
    elif case == "pilot_pin":
        p = root / "pilot_predynamic_revisions.tsv"
        with p.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        rows[0]["assessment_id"] = "a" * 64
        write_tsv(p, rows)
    else:
        p = root / "assessments.jsonl"
        p.write_text(p.read_text() + p.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError):
        FrozenCohort(root, expected_checksums_sha256=seal(root))


def test_verified_contents_remain_stable_after_external_change(packet):
    root, pin, entries, records = packet
    c = FrozenCohort(root, expected_checksums_sha256=pin)
    (root / "assessments.jsonl").write_text("{}\n")
    assert c.inspect(entries[0]["sha256"])["assessment"] == records[0]


def test_cli_summary_exact_sha_followups_and_failure(packet, capsys):
    root, pin, entries, _ = packet
    args = ["--packet", str(root), "--expect-checksums-sha256", pin]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["hashes_verified"] == 2
    assert main(args + ["--sha256", entries[0]["sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["pilot_original_revision"]
    assert main(args + ["--followups"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 5
    assert main(args + ["--sha256", "f" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "verification_failed"


def test_resealed_record_body_cannot_keep_old_immutable_id(packet):
    root, _, _, _ = packet
    p = root / "assessments.jsonl"
    records = [json.loads(line) for line in p.read_text().splitlines()]
    records[0]["assessment"]["family"]["reason"] = "Changed after freeze"
    p.write_text("".join(json.dumps(r) + "\n" for r in records))
    with pytest.raises(ValueError, match="Immutable assessment digest"):
        FrozenCohort(root, expected_checksums_sha256=seal(root))
