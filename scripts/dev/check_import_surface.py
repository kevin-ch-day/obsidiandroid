#!/usr/bin/env python3
"""Smoke-check that ``obsidiandroid`` and CLI/pipeline entry modules import correctly.

Run from the repository root after ``pip install -e .`` or with ``PYTHONPATH`` including
``src/`` (see AGENTS.md and STRUCTURE_MIGRATION_PLAN.md). Exits nonzero on failure.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType


def _module_path(mod: ModuleType) -> str:
    path = getattr(mod, "__file__", None)
    return str(path) if path else "(namespace package)"


def main() -> int:
    """Import key surfaces and verify ``run_pipeline`` identity."""
    try:
        pkg = importlib.import_module("obsidiandroid")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid -> {_module_path(pkg)}")

    for name in (
        "obsidiandroid.cli.startup_menu",
        "obsidiandroid.cli.pipeline_entry",
        "obsidiandroid.pipeline",
    ):
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            print(f"FAIL: import {name}: {exc}", file=sys.stderr)
            return 1
        print(f"OK   {name} -> {_module_path(mod)}")

    runner_mod = importlib.import_module("analysis.pipeline.runner")
    pipeline_mod = importlib.import_module("obsidiandroid.pipeline")
    if pipeline_mod.run_pipeline is not runner_mod.run_pipeline:
        print(
            "FAIL: obsidiandroid.pipeline.run_pipeline is not analysis.pipeline.runner.run_pipeline",
            file=sys.stderr,
        )
        return 1
    print("OK   obsidiandroid.pipeline.run_pipeline is analysis.pipeline.runner.run_pipeline")
    if pipeline_mod.DIAGNOSTICS_DIR != runner_mod.DIAGNOSTICS_DIR:
        print("FAIL: pipeline facade DIAGNOSTICS_DIR mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PARSER_QUALITY_PATH != runner_mod.PARSER_QUALITY_PATH:
        print("FAIL: pipeline facade PARSER_QUALITY_PATH mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PIPELINE_MAIN_LOGGER is not runner_mod.PIPELINE_MAIN_LOGGER:
        print("FAIL: pipeline facade PIPELINE_MAIN_LOGGER mismatch", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.pipeline public facade matches runner (DIAGNOSTICS_DIR, paths, logger)")

    common_checks = (
        "obsidiandroid.common.hash_utils",
        "obsidiandroid.common.ml_console",
        "obsidiandroid.common.display_distribution",
    )
    for name in common_checks:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            print(f"FAIL: import {name}: {exc}", file=sys.stderr)
            return 1
        print(f"OK   {name} -> {_module_path(mod)}")

    hash_pkg = importlib.import_module("obsidiandroid.common.hash_utils")
    shim_hash = importlib.import_module("utils.hash_utils")
    if shim_hash.sha256_hex is not hash_pkg.sha256_hex:
        print("FAIL: utils.hash_utils.sha256_hex is not obsidiandroid.common.hash_utils.sha256_hex", file=sys.stderr)
        return 1
    print("OK   utils.hash_utils re-exports match obsidiandroid.common.hash_utils")

    try:
        gov_mod = importlib.import_module("obsidiandroid.governance.evidence_mode_resolver")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.governance.evidence_mode_resolver: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.governance.evidence_mode_resolver -> {_module_path(gov_mod)}")

    shim_em = importlib.import_module("utils.evidence_mode_resolver")
    if shim_em.resolve_evidence_mode is not gov_mod.resolve_evidence_mode:
        print(
            "FAIL: utils.evidence_mode_resolver.resolve_evidence_mode is not canonical",
            file=sys.stderr,
        )
        return 1
    print("OK   utils.evidence_mode_resolver re-exports match governance canonical module")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
