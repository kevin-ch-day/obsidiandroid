#!/usr/bin/env python3
"""Smoke-check that ``obsidiandroid`` and CLI/pipeline entry modules import correctly.

Also enforces **thin compatibility shims** (no duplicated implementation at legacy paths):
repo-root ``utils/*.py`` (excluding bootstrap/entry special cases), ``utils/exporting``
leaf modules, ``utils/menu``, ``utils/ui``, and ``utils/logging``—see
:func:`collect_thin_compat_shim_violations`.

Fails if any tracked-style ``*.py`` tree under the repo starts with a **UTF-8 BOM**
(``\ufeff``), which breaks :func:`ast.parse` and confuses diffs—see
:func:`collect_utf8_bom_python_sources`.

Run from the repository root after ``pip install -e .`` or with ``PYTHONPATH`` including
``src/`` (see docs/AGENTS.md and docs/STRUCTURE_MIGRATION_PLAN.md). Exits nonzero on failure.
"""

from __future__ import annotations

import ast
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

_UTF8_BOM = b"\xef\xbb\xbf"
# Directory name fragments skipped when scanning for UTF-8 BOM (generated / vendor trees).
_BOM_SCAN_SKIP_DIR_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "output",
        "logs",
        ".pytest_tmp",
        "build",
        "dist",
        "htmlcov",
        "wandb",
        "mlruns",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        "node_modules",
        ".cursor",
    }
)

# Ensure repo root is importable (``scripts.*``, ``utils``) when this
# file is run from another working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _module_path(mod: ModuleType) -> str:
    path = getattr(mod, "__file__", None)
    return str(path) if path else "(namespace package)"


@dataclass(frozen=True)
class _ThinCompatShimPolicy:
    """Declarative checks for star-import / re-export compatibility modules."""

    label: str
    relative_parts: tuple[str, ...]
    max_lines: int
    required_substrings: tuple[str, ...]
    relocate_hint: str
    exclude_names: frozenset[str] = frozenset()


# Repo-root ``utils/*.py`` only (not subpackages). Excludes bootstrap, module-alias, and
# ``if __name__ == "__main__"`` entry shims.
_POLICY_UTILS_ROOT_SHIMS = _ThinCompatShimPolicy(
    label="utils/*.py root shims",
    relative_parts=("utils",),
    max_lines=24,
    required_substrings=("utils.repo_import_paths", "obsidiandroid"),
    relocate_hint="src/obsidiandroid",
    exclude_names=frozenset(
        {
            "__init__.py",
            "repo_import_paths.py",
            "export_manager.py",
            "startup_menu.py",
        }
    ),
)


_THIN_COMPAT_SHIM_POLICIES: tuple[_ThinCompatShimPolicy, ...] = (
    _POLICY_UTILS_ROOT_SHIMS,
    _ThinCompatShimPolicy(
        label="utils/exporting leaf shims",
        relative_parts=("utils", "exporting"),
        max_lines=16,
        required_substrings=("utils.repo_import_paths", "obsidiandroid.common"),
        relocate_hint="obsidiandroid.common.export_*",
        exclude_names=frozenset({"__init__.py"}),
    ),
    _ThinCompatShimPolicy(
        label="utils/menu shims",
        relative_parts=("utils", "menu"),
        max_lines=16,
        required_substrings=("utils.repo_import_paths", "obsidiandroid.cli.menu"),
        relocate_hint="obsidiandroid.cli.menu",
        exclude_names=frozenset({"__init__.py"}),
    ),
    _ThinCompatShimPolicy(
        label="utils/ui shims",
        relative_parts=("utils", "ui"),
        max_lines=16,
        required_substrings=("utils.repo_import_paths", "obsidiandroid.cli.ui"),
        relocate_hint="obsidiandroid.cli.ui",
        exclude_names=frozenset({"__init__.py"}),
    ),
    _ThinCompatShimPolicy(
        label="utils/logging shims",
        relative_parts=("utils", "logging"),
        max_lines=24,
        required_substrings=("utils.repo_import_paths", "obsidiandroid.observability.logging"),
        relocate_hint="obsidiandroid.observability.logging",
    ),
)


def _validate_single_thin_compat_policy(repo_root: Path, policy: _ThinCompatShimPolicy) -> list[str]:
    errors: list[str] = []
    shim_dir = repo_root.joinpath(*policy.relative_parts)
    if not shim_dir.is_dir():
        return [f"missing shim directory: {shim_dir.relative_to(repo_root)}"]

    for path in sorted(shim_dir.glob("*.py")):
        if path.name in policy.exclude_names:
            continue
        rel = path.relative_to(repo_root)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{rel}: cannot read file ({exc})")
            continue

        lines = text.splitlines()
        if len(lines) > policy.max_lines:
            errors.append(
                f"{rel}: {len(lines)} lines (max {policy.max_lines}); "
                f"move logic to {policy.relocate_hint}"
            )
            continue

        for sub in policy.required_substrings:
            if sub not in text:
                errors.append(f"{rel}: must contain {sub!r} (canonical import / bootstrap)")

        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error: {exc}")
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                errors.append(
                    f"{rel}: shim must not define {node.name!r} at module level "
                    f"(implement under {policy.relocate_hint})"
                )

    return errors


def collect_thin_compat_shim_violations(repo_root: Path) -> list[str]:
    """Run all thin-compat shim policies; return prefixed error lines (empty if OK)."""
    out: list[str] = []
    for policy in _THIN_COMPAT_SHIM_POLICIES:
        for msg in _validate_single_thin_compat_policy(repo_root, policy):
            out.append(f"[{policy.label}] {msg}")
    return out


def collect_utf8_bom_python_sources(repo_root: Path) -> list[str]:
    """Return repo-relative paths of ``*.py`` files that begin with a UTF-8 BOM byte sequence.

    Scan skips typical generated/vendor directories. Unreadable files are reported as
    errors so permission problems do not pass silently.
    """
    bad: list[str] = []
    for path in repo_root.rglob("*.py"):
        if any(p in _BOM_SCAN_SKIP_DIR_PARTS for p in path.parts):
            continue
        if any(p.endswith(".egg-info") for p in path.parts):
            continue
        rel = path.relative_to(repo_root)
        try:
            with path.open("rb") as fh:
                head = fh.read(3)
        except OSError as exc:
            bad.append(f"{rel} (unreadable: {exc})")
            continue
        if head == _UTF8_BOM:
            bad.append(str(rel))
    return bad


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
        "obsidiandroid.modeling",
        "obsidiandroid.features",
        "obsidiandroid.labeling",
        "obsidiandroid.vendors",
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
    _pipeline_module_pairs = (
        ("attach_engine_metadata", "analysis.pipeline.attach_engine_metadata"),
        ("av_engine_pipeline", "analysis.pipeline.av_engine_pipeline"),
        ("contract_filters", "analysis.pipeline.contract_filters"),
        ("engine_normalization", "analysis.pipeline.engine_normalization"),
        ("main_facade", "analysis.pipeline.main_facade"),
        ("runner", "analysis.pipeline.runner"),
        ("run_bounds", "analysis.pipeline.run_bounds"),
        ("runtime_policy", "analysis.pipeline.runtime_policy"),
        ("sample_exports", "analysis.pipeline.sample_exports"),
        ("sample_preparation", "analysis.pipeline.sample_preparation"),
        ("score_av_engines", "analysis.pipeline.score_av_engines"),
        ("stage_ablation", "analysis.pipeline.stage_ablation"),
        ("stage_av_vendor", "analysis.pipeline.stage_av_vendor"),
        ("stage_feature_enrichment", "analysis.pipeline.stage_feature_enrichment"),
        ("stage_manifest", "analysis.pipeline.stage_manifest"),
        ("stage_modeling", "analysis.pipeline.stage_modeling"),
        ("stage_permission_trends_report", "analysis.pipeline.stage_permission_trends_report"),
        ("stage_results_warehouse", "analysis.pipeline.stage_results_warehouse"),
        ("stage_samples", "analysis.pipeline.stage_samples"),
        ("vendor_metadata_pipeline", "analysis.pipeline.vendor_metadata_pipeline"),
    )
    for attr, canon_name in _pipeline_module_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(pipeline_mod, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline module aliases match analysis.pipeline")

    _manifest_facade = importlib.import_module("obsidiandroid.pipeline.manifest")
    _manifest_pairs = (
        ("hashing", "analysis.pipeline.manifest.hashing"),
        ("paper_compliance_checks", "analysis.pipeline.manifest.paper_compliance_checks"),
        ("paper_figure_renderers", "analysis.pipeline.manifest.paper_figure_renderers"),
        ("runtime_support", "analysis.pipeline.manifest.runtime_support"),
        ("writer", "analysis.pipeline.manifest.writer"),
    )
    for attr, canon_name in _manifest_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_manifest_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.manifest.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.manifest.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.pipeline.manifest.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.manifest submodules match analysis.pipeline.manifest")

    _artifacts_facade = importlib.import_module("obsidiandroid.pipeline.artifacts")
    _artifacts_pairs = (
        ("paths", "analysis.pipeline.artifacts.paths"),
        ("registry", "analysis.pipeline.artifacts.registry"),
    )
    for attr, canon_name in _artifacts_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_artifacts_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.artifacts.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.artifacts.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.pipeline.artifacts.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.artifacts submodules match analysis.pipeline.artifacts")

    _permission_trends_facade = importlib.import_module("obsidiandroid.pipeline.permission_trends")
    _permission_trends_pairs = (
        ("bundle_manifest", "analysis.pipeline.permission_trends.bundle_manifest"),
        ("constants", "analysis.pipeline.permission_trends.constants"),
        ("publish_paths", "analysis.pipeline.permission_trends.publish_paths"),
        ("reporting_support", "analysis.pipeline.permission_trends.reporting_support"),
        ("sample_permission_data", "analysis.pipeline.permission_trends.sample_permission_data"),
        ("stats_core", "analysis.pipeline.permission_trends.stats_core"),
    )
    for attr, canon_name in _permission_trends_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_permission_trends_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.permission_trends.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.permission_trends.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.pipeline.permission_trends.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.permission_trends submodules match analysis.pipeline.permission_trends")

    _modeling_facade = importlib.import_module("obsidiandroid.modeling")
    _modeling_pairs = (
        ("distribution_reporter", "ml_classification.ml_utils.distribution_reporter"),
        ("feature_label_alignment_helper", "ml_classification.ml_utils.feature_label_alignment_helper"),
        ("model_trainer_factory", "ml_classification.training.model_trainer_factory"),
        ("pipeline_core", "ml_classification.training.pipeline_core"),
    )
    for attr, canon_name in _modeling_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_modeling_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.modeling.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.modeling.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.modeling.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.modeling submodules match ml_classification")

    _features_facade = importlib.import_module("obsidiandroid.features")
    _features_pairs = (
        ("feature_vector_builder", "ml_classification.vectorization.feature_vector_builder"),
    )
    for attr, canon_name in _features_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_features_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.features.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.features.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.features.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.features submodules match ml_classification")

    _labeling_facade = importlib.import_module("obsidiandroid.labeling")
    _labeling_pairs = (
        ("classification_label_resolver", "ml_classification.labeling.classification_label_resolver"),
    )
    for attr, canon_name in _labeling_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_labeling_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.labeling.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.labeling.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.labeling.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.labeling submodules match ml_classification")

    _vendors_facade = importlib.import_module("obsidiandroid.vendors")
    _vendors_pairs = (
        ("vendor_parser_map", "analysis.vendor_processing.vendor_parser_map"),
    )
    for attr, canon_name in _vendors_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_vendors_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.vendors.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.vendors.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.vendors.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.vendors submodules match analysis.vendor_processing")

    _governance_facade = importlib.import_module("obsidiandroid.governance")
    _governance_pairs = (
        ("exceptions", "analysis.pipeline.governance.exceptions"),
        ("integrity", "analysis.pipeline.governance.integrity"),
    )
    for attr, canon_name in _governance_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_governance_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.governance.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.governance.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.governance.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.governance pipeline governance aliases match analysis.pipeline.governance")

    common_checks = (
        "obsidiandroid.common.hash_utils",
        "obsidiandroid.common.ml_console",
        "obsidiandroid.common.display_distribution",
        "obsidiandroid.common.output_paths",
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

    canon_op = importlib.import_module("obsidiandroid.common.output_paths")
    shim_op = importlib.import_module("utils.output_paths")
    if shim_op.output_root is not canon_op.output_root:
        print("FAIL: utils.output_paths.output_root shim mismatch", file=sys.stderr)
        return 1
    if shim_op.project_logs_root is not canon_op.project_logs_root:
        print("FAIL: utils.output_paths.project_logs_root shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.output_paths re-exports match obsidiandroid.common.output_paths")

    canon_disp = importlib.import_module("obsidiandroid.cli.ui.display")
    shim_disp = importlib.import_module("utils.display_utils")
    if shim_disp.print_table is not canon_disp.print_table:
        print("FAIL: utils.display_utils.print_table is not obsidiandroid.cli.ui.display.print_table", file=sys.stderr)
        return 1
    print("OK   utils.display_utils re-exports match obsidiandroid.cli.ui.display")

    canon_mlc = importlib.import_module("obsidiandroid.common.ml_console")
    shim_mlc = importlib.import_module("utils.ml_console")
    if shim_mlc.is_minimal is not canon_mlc.is_minimal:
        print("FAIL: utils.ml_console.is_minimal is not canonical ml_console", file=sys.stderr)
        return 1
    print("OK   utils.ml_console re-exports match obsidiandroid.common.ml_console")

    canon_occ = importlib.import_module("obsidiandroid.common.output_cleanup_clutter")
    shim_occ = importlib.import_module("utils.output_cleanup_clutter")
    if shim_occ.WORKBOOK_CORRUPT_GLOB != canon_occ.WORKBOOK_CORRUPT_GLOB:
        print("FAIL: output_cleanup_clutter shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.output_cleanup_clutter re-exports match obsidiandroid.common.output_cleanup_clutter")

    canon_av = importlib.import_module("obsidiandroid.common.av_detection_tiers")
    shim_av = importlib.import_module("utils.av_detection_tiers")
    if shim_av.get_detection_tier is not canon_av.get_detection_tier:
        print("FAIL: av_detection_tiers shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.av_detection_tiers re-exports match obsidiandroid.common.av_detection_tiers")

    canon_smp = importlib.import_module("obsidiandroid.common.sample_metadata_preprocessor")
    shim_smp = importlib.import_module("utils.sample_metadata_preprocessor")
    if shim_smp.prepare_sample_dataframe is not canon_smp.prepare_sample_dataframe:
        print("FAIL: sample_metadata_preprocessor shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.sample_metadata_preprocessor re-exports match obsidiandroid.common.sample_metadata_preprocessor")

    canon_cmp = importlib.import_module("obsidiandroid.governance.compliance")
    shim_cmp = importlib.import_module("utils.compliance")
    if shim_cmp.build_compliance_report is not canon_cmp.build_compliance_report:
        print("FAIL: utils.compliance shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.compliance re-exports match obsidiandroid.governance.compliance")

    canon_lt = importlib.import_module("obsidiandroid.reporting.latex_tables")
    shim_lt = importlib.import_module("utils.latex_tables")
    if shim_lt.LatexTableSpec is not canon_lt.LatexTableSpec:
        print("FAIL: utils.latex_tables LatexTableSpec shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.latex_tables re-exports match obsidiandroid.reporting.latex_tables")

    canon_fdr = importlib.import_module("obsidiandroid.reporting.family_distribution_report")
    shim_fdr = importlib.import_module("utils.family_distribution_report")
    if shim_fdr.print_family_distribution_stats is not canon_fdr.print_family_distribution_stats:
        print("FAIL: family_distribution_report shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.family_distribution_report re-exports match obsidiandroid.reporting.family_distribution_report")

    canon_pm = importlib.import_module("obsidiandroid.cli.profile_manager")
    shim_pm = importlib.import_module("utils.profile_manager")
    if shim_pm.load_profile is not canon_pm.load_profile:
        print("FAIL: profile_manager shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.profile_manager re-exports match obsidiandroid.cli.profile_manager")

    canon_crr = importlib.import_module("obsidiandroid.governance.cohort_readiness_report")
    shim_crr = importlib.import_module("utils.cohort_readiness_report")
    if shim_crr.print_cohort_readiness_report is not canon_crr.print_cohort_readiness_report:
        print("FAIL: cohort_readiness_report shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.cohort_readiness_report re-exports match obsidiandroid.governance.cohort_readiness_report")

    canon_crep = importlib.import_module("obsidiandroid.governance.cohort_reproducibility")
    shim_crep = importlib.import_module("utils.cohort_reproducibility")
    if shim_crep.apply_analysis_snapshot_lock is not canon_crep.apply_analysis_snapshot_lock:
        print("FAIL: cohort_reproducibility shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.cohort_reproducibility re-exports match obsidiandroid.governance.cohort_reproducibility")

    canon_rm = importlib.import_module("obsidiandroid.governance.run_manifest")
    shim_rm = importlib.import_module("utils.run_manifest")
    if shim_rm.generate_run_id is not canon_rm.generate_run_id:
        print("FAIL: run_manifest.generate_run_id shim mismatch", file=sys.stderr)
        return 1
    if shim_rm.write_run_manifest is not canon_rm.write_run_manifest:
        print("FAIL: run_manifest.write_run_manifest shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.run_manifest re-exports match obsidiandroid.governance.run_manifest")

    canon_art = importlib.import_module("obsidiandroid.governance.artifacts")
    shim_art = importlib.import_module("utils.artifacts")
    if shim_art.ManifestWriter is not canon_art.ManifestWriter:
        print("FAIL: artifacts.ManifestWriter shim mismatch", file=sys.stderr)
        return 1
    if shim_art.ArtifactKey is not canon_art.ArtifactKey:
        print("FAIL: artifacts.ArtifactKey shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.artifacts re-exports match obsidiandroid.governance.artifacts")

    canon_en = importlib.import_module("obsidiandroid.common.export_naming")
    shim_en = importlib.import_module("utils.exporting.naming")
    if shim_en.safe_sheet_name is not canon_en.safe_sheet_name:
        print(
            "FAIL: utils.exporting.naming.safe_sheet_name is not obsidiandroid.common.export_naming",
            file=sys.stderr,
        )
        return 1
    print("OK   utils.exporting.naming re-exports match obsidiandroid.common.export_naming")

    canon_ev = importlib.import_module("obsidiandroid.common.export_vendor_raw")
    shim_ev = importlib.import_module("utils.exporting.vendor_raw")
    if shim_ev.is_parquet_supported is not canon_ev.is_parquet_supported:
        print("FAIL: export_vendor_raw shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.exporting.vendor_raw re-exports match obsidiandroid.common.export_vendor_raw")

    canon_wb = importlib.import_module("obsidiandroid.common.export_workbook")
    shim_wb = importlib.import_module("utils.exporting.workbook")
    if shim_wb.WorkbookLock is not canon_wb.WorkbookLock:
        print("FAIL: export_workbook WorkbookLock shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.exporting.workbook re-exports match obsidiandroid.common.export_workbook")

    canon_cm = importlib.import_module("obsidiandroid.reporting.confusion_matrix_exporter")
    shim_cm = importlib.import_module("utils.confusion_matrix_exporter")
    if shim_cm.export_confusion_matrix_image is not canon_cm.export_confusion_matrix_image:
        print("FAIL: confusion_matrix_exporter export_confusion_matrix_image shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.confusion_matrix_exporter re-exports match obsidiandroid.reporting")

    canon_em = importlib.import_module("obsidiandroid.reporting.export_manager")
    shim_em = importlib.import_module("utils.export_manager")
    if shim_em is not canon_em:
        print(
            "FAIL: utils.export_manager must alias obsidiandroid.reporting.export_manager module object",
            file=sys.stderr,
        )
        return 1
    if shim_em.export_dataframe_to_excel is not canon_em.export_dataframe_to_excel:
        print("FAIL: export_manager.export_dataframe_to_excel shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.export_manager aliases obsidiandroid.reporting.export_manager")

    canon_me = importlib.import_module("obsidiandroid.modeling.model_exporter")
    shim_me = importlib.import_module("utils.model_exporter")
    if shim_me.export_model_to_file is not canon_me.export_model_to_file:
        print("FAIL: utils.model_exporter.export_model_to_file is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.model_exporter re-exports match obsidiandroid.modeling.model_exporter")

    canon_oh = importlib.import_module("obsidiandroid.common.output_hygiene")
    shim_oh = importlib.import_module("utils.output_hygiene")
    if shim_oh.resolve_stable_output_root_for_mirrors is not canon_oh.resolve_stable_output_root_for_mirrors:
        print("FAIL: utils.output_hygiene.resolve_stable_output_root_for_mirrors is not canonical", file=sys.stderr)
        return 1
    if shim_oh.mirror_csv_text_run_then_global is not canon_oh.mirror_csv_text_run_then_global:
        print("FAIL: utils.output_hygiene.mirror_csv_text_run_then_global is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.output_hygiene re-exports match obsidiandroid.common.output_hygiene")

    try:
        obs_pkg = importlib.import_module("obsidiandroid.observability")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.observability -> {_module_path(obs_pkg)}")

    try:
        canon_olog = importlib.import_module("obsidiandroid.observability.logging")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability.logging: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.observability.logging -> {_module_path(canon_olog)}")

    if obs_pkg.get_logger is not canon_olog.get_logger:
        print("FAIL: obsidiandroid.observability.get_logger is not logging.get_logger", file=sys.stderr)
        return 1
    if obs_pkg.log_event is not canon_olog.log_event:
        print("FAIL: obsidiandroid.observability.log_event is not logging.log_event", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.observability re-exports get_logger / log_event from logging subpackage")

    shim_olog = importlib.import_module("utils.logging")
    if shim_olog.get_logger is not canon_olog.get_logger:
        print("FAIL: utils.logging.get_logger is not canonical", file=sys.stderr)
        return 1
    if shim_olog.log_event is not canon_olog.log_event:
        print("FAIL: utils.logging.log_event is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.logging re-exports match obsidiandroid.observability.logging")

    canon_olog_logger = importlib.import_module("obsidiandroid.observability.logging.logger")
    shim_olog_logger = importlib.import_module("utils.logging.logger")
    if shim_olog_logger.close_all_loggers is not canon_olog_logger.close_all_loggers:
        print("FAIL: utils.logging.logger.close_all_loggers is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.logging.logger re-exports match obsidiandroid.observability.logging.logger")

    canon_olog_rt = importlib.import_module("obsidiandroid.observability.logging.runtime")
    shim_olog_rt = importlib.import_module("utils.logging.runtime")
    if shim_olog_rt.start_runtime_logging is not canon_olog_rt.start_runtime_logging:
        print("FAIL: utils.logging.runtime.start_runtime_logging is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.logging.runtime re-exports match obsidiandroid.observability.logging.runtime")

    try:
        pop_pkg = importlib.import_module("obsidiandroid.observability.pipeline_observability")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability.pipeline_observability: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.observability.pipeline_observability -> {_module_path(pop_pkg)}")

    canon_pu = importlib.import_module("obsidiandroid.cli.prompt_utils")
    shim_pu = importlib.import_module("utils.prompt_utils")
    if shim_pu.prompt_yes_no is not canon_pu.prompt_yes_no:
        print("FAIL: utils.prompt_utils.prompt_yes_no is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.prompt_utils re-exports match obsidiandroid.cli.prompt_utils")

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

    try:
        diag_facade = importlib.import_module("obsidiandroid.diagnostics")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.diagnostics: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.diagnostics -> {_module_path(diag_facade)}")
    _diag_pairs = (
        ("ablation_cohort_diagnostics", "analysis.diagnostics.ablation_cohort_diagnostics"),
        ("alignment_gap_diagnostics", "analysis.diagnostics.alignment_gap_diagnostics"),
        ("cohort_foundation_export", "analysis.diagnostics.cohort_foundation_export"),
        ("cohort_sample_id_audit", "analysis.diagnostics.cohort_sample_id_audit"),
        ("cohort_vocabulary", "analysis.diagnostics.cohort_vocabulary"),
        ("feature_builder_drop_trace", "analysis.diagnostics.feature_builder_drop_trace"),
        ("feature_build_coverage_export", "analysis.diagnostics.feature_build_coverage_export"),
        ("feature_column_survival_export", "analysis.diagnostics.feature_column_survival_export"),
        ("feature_lineage_report", "analysis.diagnostics.feature_lineage_report"),
        ("feature_matrix_gap_lineage", "analysis.diagnostics.feature_matrix_gap_lineage"),
        ("fused_permission_matrix_audit", "analysis.diagnostics.fused_permission_matrix_audit"),
        ("output_artifact_policy", "analysis.diagnostics.output_artifact_policy"),
        ("output_inventory", "analysis.diagnostics.output_inventory"),
        (
            "permission_training_survival_audit",
            "analysis.diagnostics.permission_training_survival_audit",
        ),
    )
    for attr, canon_name in _diag_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(diag_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.diagnostics.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    _diag_pkg_pairs = (
        ("research_validity", "analysis.diagnostics.research_validity"),
        ("hostile_audit", "analysis.diagnostics.hostile_audit"),
    )
    for attr, canon_name in _diag_pkg_pairs:
        canon_pkg = importlib.import_module(canon_name)
        facade_pkg = getattr(diag_facade, attr)
        if facade_pkg is not canon_pkg:
            print(
                f"FAIL: obsidiandroid.diagnostics.{attr} package mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_pkg = importlib.import_module(f"obsidiandroid.diagnostics.{attr}")
        if alias_pkg is not canon_pkg:
            print(
                f"FAIL: import obsidiandroid.diagnostics.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    _rv_bundle_canon = importlib.import_module("analysis.diagnostics.research_validity.bundle")
    _rv_bundle_alias = importlib.import_module("obsidiandroid.diagnostics.research_validity.bundle")
    if _rv_bundle_alias is not _rv_bundle_canon:
        print(
            "FAIL: obsidiandroid.diagnostics.research_validity.bundle != "
            "analysis.diagnostics.research_validity.bundle",
            file=sys.stderr,
        )
        return 1
    _ha_bundle_canon = importlib.import_module("analysis.diagnostics.hostile_audit.bundle")
    _ha_bundle_alias = importlib.import_module("obsidiandroid.diagnostics.hostile_audit.bundle")
    if _ha_bundle_alias is not _ha_bundle_canon:
        print(
            "FAIL: obsidiandroid.diagnostics.hostile_audit.bundle != "
            "analysis.diagnostics.hostile_audit.bundle",
            file=sys.stderr,
        )
        return 1
    print("OK   obsidiandroid.diagnostics submodules match analysis.diagnostics")

    try:
        db_facade = importlib.import_module("obsidiandroid.database")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.database: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.database -> {_module_path(db_facade)}")
    _database_pairs = (
        ("cohort_sql_fragments", "database.cohort_sql_fragments"),
        ("db_config", "database.db_config"),
        ("db_engine", "database.db_engine"),
        ("db_errors", "database.db_errors"),
        ("db_av_engine_detection_totals", "database.db_av_engine_detection_totals"),
        ("db_av_engine_verdicts", "database.db_av_engine_verdicts"),
        ("db_fetch_av_engine_raw_results", "database.db_fetch_av_engine_raw_results"),
        ("db_permission_analysis_queries", "database.db_permission_analysis_queries"),
        ("db_sample_metadata_contracts", "database.db_sample_metadata_contracts"),
        ("db_sample_metadata_fetchers", "database.db_sample_metadata_fetchers"),
        ("db_sample_metadata_queries", "database.db_sample_metadata_queries"),
        ("db_sample_malicious_scoring", "database.db_sample_malicious_scoring"),
        ("db_utils", "database.db_utils"),
        ("schema_map", "database.schema_map"),
        ("settings", "database.settings"),
        ("split_db_health", "database.split_db_health"),
    )
    for attr, canon_name in _database_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(db_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.database.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.database.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.database.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.database submodules match database")

    bom_paths = collect_utf8_bom_python_sources(_REPO_ROOT)
    if bom_paths:
        print(
            "FAIL: UTF-8 BOM (U+FEFF) at start of Python source — breaks ast.parse / tooling:",
            file=sys.stderr,
        )
        for item in bom_paths:
            print(f"  {item}", file=sys.stderr)
        print(
            "  Fix: save as UTF-8 without BOM, or re-save via utf-8-sig read + utf-8 write.",
            file=sys.stderr,
        )
        return 1
    print("OK   Python sources: no UTF-8 BOM prefix (repo scan)")

    thin_errors = collect_thin_compat_shim_violations(_REPO_ROOT)
    if thin_errors:
        for msg in thin_errors:
            print(f"FAIL: thin compat shim policy: {msg}", file=sys.stderr)
        return 1
    for policy in _THIN_COMPAT_SHIM_POLICIES:
        print(f"OK   {policy.label}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
