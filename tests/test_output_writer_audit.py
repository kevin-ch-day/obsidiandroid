"""Smoke tests for :mod:`scripts.dev.output_writer_audit` (read-only AST scan)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def _audit_mod():
    pytest.importorskip("scripts.dev.output_writer_audit", reason="scripts package not on path")
    from scripts.dev import output_writer_audit as mod

    return mod


def test_collect_hits_pipeline_sample(_audit_mod) -> None:
    hits = _audit_mod.collect_hits([_REPO_ROOT / "src" / "obsidiandroid" / "pipeline"])
    assert hits, "expected output-related writes under obsidiandroid/pipeline"
    assert any("sample_exports.py" in h.rel_path for h in hits)
    assert any("mirror_csv_text_run_then_global" in h.target_expr for h in hits)


def test_emit_csv_header_and_rows(_audit_mod) -> None:
    hits = _audit_mod.collect_hits([_REPO_ROOT / "src" / "obsidiandroid" / "pipeline"])
    hits = [h for h in hits if "sample_exports.py" in h.rel_path]
    assert hits
    buf = io.StringIO()
    _audit_mod.emit_csv(hits, buf)
    lines = buf.getvalue().splitlines()
    assert lines[0].startswith("module,function,write_pattern")
    assert len(lines) >= 2
