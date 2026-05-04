"""Tests for governance primitive helper modules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.governance import evidence_mode_resolver
from utils import artifacts
from utils import canonicalization
from utils import path_safety


def test_resolve_evidence_mode_precedence_cli_wins() -> None:
    """CLI input should win over env/profile."""
    result = evidence_mode_resolver.resolve_evidence_mode(
        cli_value=False,
        env_value="1",
        profile={"paper_mode": True},
        default=False,
        strict_env=True,
    )
    assert result.resolved_value is False
    assert result.source == "cli"


def test_resolve_evidence_mode_invalid_env_strict_raises() -> None:
    """Invalid strict env input should raise config error."""
    with pytest.raises(evidence_mode_resolver.EvidenceModeConfigError):
        evidence_mode_resolver.resolve_evidence_mode(
            cli_value=None,
            env_value="2",
            profile={},
            default=False,
            strict_env=True,
        )


def test_resolve_evidence_mode_env_overrides_profile() -> None:
    """Env should win over profile when CLI is not provided."""
    result = evidence_mode_resolver.resolve_evidence_mode(
        cli_value=None,
        env_value="0",
        profile={"paper_mode": True},
        default=True,
        strict_env=True,
    )
    assert result.resolved_value is False
    assert result.source == "env"


def test_enforce_immutable_lock_allows_same_value() -> None:
    """Existing lock should permit matching requested values."""
    assert (
        evidence_mode_resolver.enforce_immutable_lock(
            locked_value=True,
            requested_value=True,
        )
        is True
    )


def test_enforce_immutable_lock_rejects_override() -> None:
    """Existing lock should reject value flips."""
    with pytest.raises(evidence_mode_resolver.EvidenceModeImmutableError):
        evidence_mode_resolver.enforce_immutable_lock(
            locked_value=False,
            requested_value=True,
        )


def test_safe_join_rejects_escape(tmp_path: Path) -> None:
    """safe_join should reject path traversal."""
    with pytest.raises(path_safety.UnsafePathError):
        path_safety.safe_join(tmp_path, "..\\outside.txt")


def test_canonical_csv_bytes_are_deterministic() -> None:
    """Canonical CSV serializer should emit stable UTF-8 data."""
    rows = [{"sample_id": " 2 ", "sha256": "aa", "split_role": "test"}]
    payload = canonicalization.canonical_csv_bytes(
        rows=rows,
        fieldnames=["sample_id", "sha256", "split_role"],
    )
    assert payload.decode("utf-8") == "sample_id,sha256,split_role\n2,aa,test\n"


def test_manifest_writer_rejects_duplicate_keys_in_paper_mode(tmp_path: Path) -> None:
    """Paper mode manifest writer should reject duplicate artifact keys."""
    run_root = tmp_path / "run"
    run_root.mkdir(parents=True, exist_ok=True)
    file_path = run_root / "a.csv"
    file_path.write_text("x\n1\n", encoding="utf-8")
    writer = artifacts.ManifestWriter(run_root=run_root, paper_mode=True)
    writer.add_file(
        artifact_key=artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
        path=file_path,
        content_type="text/csv",
        description="split",
    )
    with pytest.raises(ValueError):
        writer.add_file(
            artifact_key=artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
            path=file_path,
            content_type="text/csv",
            description="split2",
        )


def test_manifest_writer_writes_json(tmp_path: Path) -> None:
    """Manifest writer should persist artifact index json."""
    run_root = tmp_path / "run"
    run_root.mkdir(parents=True, exist_ok=True)
    file_path = run_root / "d.csv"
    file_path.write_text("x\n1\n", encoding="utf-8")
    out_path = run_root / "run_paths_manifest_test.json"
    writer = artifacts.ManifestWriter(run_root=run_root, paper_mode=False)
    writer.add_file(
        artifact_key=artifacts.ArtifactKey.DUPLICATE_SHA_REPORT_CSV,
        path=file_path,
        content_type="text/csv",
        description="dup-report",
    )
    writer.write_json(out_path, run_id="r1", profile_name="banker")
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
    assert artifacts.ArtifactKey.DUPLICATE_SHA_REPORT_CSV in payload["artifacts"]


def test_manifest_writer_excludes_non_run_scoped_artifact_in_non_paper_mode(tmp_path: Path) -> None:
    """Non-paper mode should exclude out-of-run artifacts with explicit status."""
    run_root = tmp_path / "run"
    run_root.mkdir(parents=True, exist_ok=True)
    external_path = tmp_path / "external.csv"
    external_path.write_text("x\n1\n", encoding="utf-8")
    out_path = run_root / "run_paths_manifest_test.json"

    writer = artifacts.ManifestWriter(run_root=run_root, paper_mode=False)
    writer.add_file(
        artifact_key=artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
        path=external_path,
        content_type="text/csv",
        description="split",
    )
    writer.write_json(out_path, run_id="r1", profile_name="banker")
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    entry = payload["artifacts"][artifacts.ArtifactKey.SPLIT_AUDIT_CSV]
    assert entry["status"] == "excluded_non_run_scoped"
    assert writer.excluded_non_run_scoped_count == 1


def test_manifest_writer_rejects_non_run_scoped_artifact_in_paper_mode(tmp_path: Path) -> None:
    """Paper mode should hard-fail on out-of-run artifacts."""
    run_root = tmp_path / "run"
    run_root.mkdir(parents=True, exist_ok=True)
    external_path = tmp_path / "external.csv"
    external_path.write_text("x\n1\n", encoding="utf-8")
    writer = artifacts.ManifestWriter(run_root=run_root, paper_mode=True)
    with pytest.raises(ValueError):
        writer.add_file(
            artifact_key=artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
            path=external_path,
            content_type="text/csv",
            description="split",
        )
