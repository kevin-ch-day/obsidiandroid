"""Tests for canonical runtime diagnostics helpers."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics import vendor_feature_validation


def test_vendor_validation_accepts_valid_runtime_output() -> None:
    output = {
        "summary_df": pd.DataFrame([[1, 2, 3]] * 5, columns=["a", "b", "c"]),
        "records_by_vendor": {"vendor": ["record"]},
        "parsed_data": {"vendor": [{"sample_id": 1}]},
    }

    result = vendor_feature_validation.validate_vendor_classification_output(output, strict=True)

    assert result is not None
    assert result[0] is output["summary_df"]
    assert result[2] is output["parsed_data"]


def test_runtime_source_does_not_import_scripts_namespace() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in (repo_root / "src" / "obsidiandroid").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == "scripts" or alias.name.startswith("scripts.") for alias in node.names):
                    offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "scripts" or node.module.startswith("scripts."):
                    offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")
    assert offenders == []


def test_database_mutator_scripts_are_outside_diagnostics_namespace() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    diagnostics_dir = repo_root / "scripts" / "diagnostics"
    maintenance_dir = repo_root / "scripts" / "maintenance"

    for filename in ("normalize_observed_filenames.py", "prune_malware_artifact_ingest_queue.py"):
        assert not (diagnostics_dir / filename).exists()
        assert (maintenance_dir / filename).is_file()
