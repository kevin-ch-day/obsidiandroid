"""Tests for manifest-stage run-scoped authority coverage bundle emission."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.pipeline.manifest import stage_manifest_writers


def test_emit_run_authority_coverage_bundle_appends_run_scoped_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "output" / "runs" / "r_auth" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    def _fake_generate_authority_coverage_artifacts(**kwargs):
        for key in ("md_path", "missing_out", "unknown_type_out", "year_type_out"):
            Path(kwargs[key]).write_text(f"{key}\n", encoding="utf-8")
        return {
            "ok": True,
            "source_mode": "live_view",
            "warning": None,
            "md_path": kwargs["md_path"],
            "missing_out": kwargs["missing_out"],
            "unknown_type_out": kwargs["unknown_type_out"],
            "year_type_out": kwargs["year_type_out"],
        }

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.family_type_authority_coverage.generate_authority_coverage_artifacts",
        _fake_generate_authority_coverage_artifacts,
    )

    artifact_list: list[str] = []
    manifest_context: dict[str, object] = {}
    bundle = stage_manifest_writers.emit_run_authority_coverage_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="r_auth",
        artifact_list=artifact_list,
        manifest_context=manifest_context,
    )

    assert bundle["ok"] is True
    assert manifest_context["authority_coverage_source_mode"] == "live_view"
    assert str(diagnostics_dir / "family_type_authority_coverage_r_auth.md") in artifact_list
    assert str(diagnostics_dir / "family_type_authority_missing_candidates_r_auth.csv") in artifact_list
    assert str(diagnostics_dir / "family_type_authority_unknown_type_r_auth.csv") in artifact_list
    assert str(diagnostics_dir / "family_type_authority_year_type_r_auth.csv") in artifact_list


def test_emit_run_authority_coverage_bundle_writes_stub_when_view_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "output" / "runs" / "r_missing" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.family_type_authority_coverage.generate_authority_coverage_artifacts",
        lambda **_kwargs: {
            "ok": False,
            "source_mode": "live_view_missing",
            "warning": (
                "Authority view unavailable; run `database/sql/view_android_sample_family_type_authority.sql` "
                "against Erebus before using this diagnostic."
            ),
        },
    )

    artifact_list: list[str] = []
    manifest_context: dict[str, object] = {}
    bundle = stage_manifest_writers.emit_run_authority_coverage_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="r_missing",
        artifact_list=artifact_list,
        manifest_context=manifest_context,
    )

    stub_path = diagnostics_dir / "family_type_authority_coverage_r_missing.md"
    assert bundle["ok"] is False
    assert manifest_context["authority_coverage_source_mode"] == "live_view_missing"
    assert stub_path.exists()
    assert str(stub_path) in artifact_list
    text = stub_path.read_text(encoding="utf-8")
    assert "Status: `unavailable`" in text
    assert "view_android_sample_family_type_authority.sql" in text
