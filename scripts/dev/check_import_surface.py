#!/usr/bin/env python3
"""Smoke-check that ``obsidiandroid`` and CLI/pipeline entry modules import correctly.

Also enforces **thin compatibility shims** (no duplicated implementation at legacy paths):
repo-root ``utils/*.py`` (excluding bootstrap/entry special cases), ``utils/exporting``
leaf modules, and ``utils/logging``—see :func:`collect_thin_compat_shim_violations`.

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
        "obsidiandroid.labeling.taxonomy",
        "obsidiandroid.vendors",
        "obsidiandroid.vendors.parsing",
        "obsidiandroid.vendors.contracts",
        "obsidiandroid.evaluation",
    ):
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            print(f"FAIL: import {name}: {exc}", file=sys.stderr)
            return 1
        print(f"OK   {name} -> {_module_path(mod)}")

    canon_runner = importlib.import_module("obsidiandroid.pipeline.runner")
    legacy_runner = importlib.import_module("analysis.pipeline.runner")
    if canon_runner is not legacy_runner:
        print(
            "FAIL: obsidiandroid.pipeline.runner must be identical ModuleType to analysis.pipeline.runner shim",
            file=sys.stderr,
        )
        return 1
    pipeline_mod = importlib.import_module("obsidiandroid.pipeline")
    if pipeline_mod.run_pipeline is not canon_runner.run_pipeline:
        print(
            "FAIL: obsidiandroid.pipeline.run_pipeline is not obsidiandroid.pipeline.runner.run_pipeline",
            file=sys.stderr,
        )
        return 1
    print("OK   obsidiandroid.pipeline.run_pipeline is obsidiandroid.pipeline.runner.run_pipeline (legacy shim identical)")
    if pipeline_mod.DIAGNOSTICS_DIR != canon_runner.DIAGNOSTICS_DIR:
        print("FAIL: pipeline facade DIAGNOSTICS_DIR mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PARSER_QUALITY_PATH != canon_runner.PARSER_QUALITY_PATH:
        print("FAIL: pipeline facade PARSER_QUALITY_PATH mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PIPELINE_MAIN_LOGGER is not canon_runner.PIPELINE_MAIN_LOGGER:
        print("FAIL: pipeline facade PIPELINE_MAIN_LOGGER mismatch", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.pipeline public facade matches runner (DIAGNOSTICS_DIR, paths, logger)")
    _pipeline_physical_attrs = (
        "attach_engine_metadata",
        "av_engine_pipeline",
        "contract_filters",
        "engine_normalization",
        "main_facade",
        "runner",
        "run_bounds",
        "runtime_policy",
        "sample_exports",
        "sample_preparation",
        "score_av_engines",
        "stage_ablation",
        "stage_av_vendor",
        "stage_feature_enrichment",
        "stage_manifest",
        "stage_modeling",
        "stage_permission_trends_report",
        "stage_results_warehouse",
        "stage_samples",
        "vendor_metadata_pipeline",
        "engine_pipeline_utils",
        "permission_trends_selection",
    )
    for attr in _pipeline_physical_attrs:
        physical_mod = importlib.import_module(f"obsidiandroid.pipeline.{attr}")
        legacy_mod = importlib.import_module(f"analysis.pipeline.{attr}")
        if physical_mod is not legacy_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.{attr} physical vs analysis.pipeline.{attr} shim mismatch",
                file=sys.stderr,
            )
            return 1
        facade_mod = getattr(pipeline_mod, attr)
        if facade_mod is not physical_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.{attr} façade mismatch vs obsidiandroid.pipeline.{attr}",
                file=sys.stderr,
            )
            return 1
    print(
        "OK   obsidiandroid.pipeline façade + leaf identity (Pass 66–71, 74); analysis.pipeline shims identical"
    )

    _manifest_facade = importlib.import_module("obsidiandroid.pipeline.manifest")
    _manifest_pairs = (
        ("hashing", "obsidiandroid.pipeline.manifest.hashing"),
        ("paper_compliance_checks", "obsidiandroid.pipeline.manifest.paper_compliance_checks"),
        ("paper_figure_renderers", "obsidiandroid.pipeline.manifest.paper_figure_renderers"),
        ("runtime_support", "obsidiandroid.pipeline.manifest.runtime_support"),
        ("writer", "obsidiandroid.pipeline.manifest.writer"),
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
        legacy_mod = importlib.import_module(f"analysis.pipeline.manifest.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.manifest.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.manifest physical; analysis.pipeline.manifest shims (Pass 76)")

    _artifacts_facade = importlib.import_module("obsidiandroid.pipeline.artifacts")
    _artifacts_pairs = (
        ("paths", "obsidiandroid.pipeline.artifacts.paths"),
        ("registry", "obsidiandroid.pipeline.artifacts.registry"),
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
        legacy_mod = importlib.import_module(f"analysis.pipeline.artifacts.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.artifacts.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.artifacts physical; analysis.pipeline.artifacts shims (Pass 76)")

    _fe_pairs = (
        ("assign_tier_scores", "obsidiandroid.feature_engineering.assign_tier_scores"),
        ("compute_vendor_scores", "obsidiandroid.feature_engineering.compute_vendor_scores"),
        ("prepare_engine_metrics", "obsidiandroid.feature_engineering.prepare_engine_metrics"),
        ("pattern_analysis", "obsidiandroid.feature_engineering.pattern_analysis"),
    )
    for attr, canon_name in _fe_pairs:
        canon_mod = importlib.import_module(canon_name)
        # Package namespace binds ``assign_tier_scores`` to a function, not the submodule — skip getattr.
        alias_mod = importlib.import_module(f"obsidiandroid.feature_engineering.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.feature_engineering.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.feature_engineering.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.feature_engineering.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.feature_engineering physical; analysis.feature_engineering shims (Pass 78)")

    _orch_pairs = (
        ("metadata_features", "obsidiandroid.orchestration.metadata_features"),
        ("methodology_artifacts", "obsidiandroid.orchestration.methodology_artifacts"),
        ("permission_features", "obsidiandroid.orchestration.permission_features"),
        ("profile_filters", "obsidiandroid.orchestration.profile_filters"),
        ("runtime_reporting", "obsidiandroid.orchestration.runtime_reporting"),
    )
    for attr, canon_name in _orch_pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.orchestration.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.orchestration.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.orchestration.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.orchestration.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.orchestration physical; analysis.orchestration shims (Pass 80)")

    _matrix_pairs = (
        ("av_binary_matrix_builder", "obsidiandroid.matrix.av_binary_matrix_builder"),
        ("enrich_malicious_scores", "obsidiandroid.matrix.enrich_malicious_scores"),
        ("enrich_score_features", "obsidiandroid.matrix.enrich_score_features"),
    )
    for attr, canon_name in _matrix_pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.matrix.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.matrix.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.matrix.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.matrix.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.matrix physical; analysis.matrix shims (Pass 80)")

    _risk_band_pairs = (
        ("assign_risk_band", "obsidiandroid.risk_band.assign_risk_band"),
        ("phase_score_engines", "obsidiandroid.risk_band.phase_score_engines"),
    )
    for attr, canon_name in _risk_band_pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.risk_band.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.risk_band.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.risk_band.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.risk_band.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.risk_band physical; analysis.risk_band shims (Pass 81)")

    _permission_trends_facade = importlib.import_module("obsidiandroid.pipeline.permission_trends")
    _permission_trends_pairs = (
        ("bundle_manifest", "obsidiandroid.pipeline.permission_trends.bundle_manifest"),
        ("constants", "obsidiandroid.pipeline.permission_trends.constants"),
        ("publish_paths", "obsidiandroid.pipeline.permission_trends.publish_paths"),
        ("reporting_support", "obsidiandroid.pipeline.permission_trends.reporting_support"),
        ("sample_permission_data", "obsidiandroid.pipeline.permission_trends.sample_permission_data"),
        ("stats_core", "obsidiandroid.pipeline.permission_trends.stats_core"),
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
        legacy_mod = importlib.import_module(f"analysis.pipeline.permission_trends.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.permission_trends.{attr} legacy shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.permission_trends submodules match legacy shims (Pass 74)")

    _modeling_facade = importlib.import_module("obsidiandroid.modeling")
    _modeling_pairs = (
        ("data_alignment", "obsidiandroid.modeling.data_alignment"),
        ("distribution_reporter", "obsidiandroid.modeling.distribution_reporter"),
        ("feature_label_alignment_helper", "obsidiandroid.modeling.feature_label_alignment_helper"),
        ("ml_result_analyzer", "obsidiandroid.modeling.ml_result_analyzer"),
        ("ml_result_validator", "obsidiandroid.modeling.ml_result_validator"),
        ("model_prediction", "obsidiandroid.modeling.model_prediction"),
        ("model_trainer_factory", "obsidiandroid.modeling.model_trainer_factory"),
        ("pipeline_core", "obsidiandroid.modeling.pipeline_core"),
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
        if attr in {
            "data_alignment",
            "distribution_reporter",
            "feature_label_alignment_helper",
            "ml_result_analyzer",
            "ml_result_validator",
            "model_prediction",
            "model_trainer_factory",
            "pipeline_core",
        }:
            if attr in {
                "data_alignment",
                "model_prediction",
                "model_trainer_factory",
                "pipeline_core",
            }:
                legacy_name = f"ml_classification.training.{attr}"
            else:
                legacy_name = f"ml_classification.ml_utils.{attr}"
            legacy_mod = importlib.import_module(legacy_name)
            if legacy_mod is not canon_mod:
                print(
                    f"FAIL: {legacy_name} did not resolve to {canon_name}",
                    file=sys.stderr,
                )
                return 1
    feature_alignment_canon = importlib.import_module("obsidiandroid.modeling.feature_alignment_utils")
    feature_alignment_legacy = importlib.import_module("ml_classification.ml_utils.feature_alignment_utils")
    if feature_alignment_legacy is not feature_alignment_canon:
        print(
            "FAIL: ml_classification.ml_utils.feature_alignment_utils did not resolve to "
            "obsidiandroid.modeling.feature_alignment_utils",
            file=sys.stderr,
        )
        return 1
    _physical_training_slices = (
        "pipeline_result_promoter",
        "train_model_executor",
        "model_training",
        "prediction_builder",
        "model_evaluation",
        "training_helpers",
    )
    for mod in _physical_training_slices:
        canon_tm = importlib.import_module(f"obsidiandroid.modeling.{mod}")
        legacy_tm = importlib.import_module(f"ml_classification.training.{mod}")
        if legacy_tm is not canon_tm:
            print(
                f"FAIL: ml_classification.training.{mod} did not resolve to "
                f"obsidiandroid.modeling.{mod}",
                file=sys.stderr,
            )
            return 1
    del mod, canon_tm, legacy_tm, _physical_training_slices
    for mod in (
        "random_forest_trainer",
        "balanced_random_forest_trainer",
        "logistic_regression_trainer",
        "svm_trainer",
        "xgboost_trainer",
    ):
        canon_tr = importlib.import_module(f"obsidiandroid.modeling.ml_trainers.{mod}")
        legacy_tr = importlib.import_module(f"ml_classification.training.ml_trainers.{mod}")
        if legacy_tr is not canon_tr:
            print(
                f"FAIL: ml_classification.training.ml_trainers.{mod} did not resolve to "
                f"obsidiandroid.modeling.ml_trainers.{mod}",
                file=sys.stderr,
            )
            return 1
    del mod, canon_tr, legacy_tr
    print("OK   obsidiandroid.modeling submodules match ml_classification")

    _features_facade = importlib.import_module("obsidiandroid.features")
    _features_pairs = (
        ("feature_encoder", "obsidiandroid.features.vectorization.feature_encoder"),
        ("feature_engine_selection", "obsidiandroid.features.vectorization.feature_engine_selection"),
        ("feature_schema_audit", "obsidiandroid.features.feature_schema_audit"),
        ("feature_vector_builder", "obsidiandroid.features.vectorization.feature_vector_builder"),
        ("feature_vendor_extractor", "obsidiandroid.features.vectorization.feature_vendor_extractor"),
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
        if attr == "feature_schema_audit":
            legacy_name = "ml_classification.training.feature_schema_audit"
        else:
            legacy_name = f"ml_classification.vectorization.{attr}"
        legacy_mod = importlib.import_module(legacy_name)
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: {legacy_name} legacy shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print(
        "OK   obsidiandroid.features physical vectorization; ml_classification.vectorization shims identical (Pass 83)"
    )

    _labeling_facade = importlib.import_module("obsidiandroid.labeling")
    _labeling_pairs = (
        ("classification_label_resolver", "obsidiandroid.labeling.classification_label_resolver"),
        ("label_builder_wrapper", "obsidiandroid.labeling.label_builder_wrapper"),
        ("label_field_normalizer", "obsidiandroid.labeling.label_field_normalizer"),
        ("label_format_generator", "obsidiandroid.labeling.label_format_generator"),
        ("label_input_validator", "obsidiandroid.labeling.label_input_validator"),
        ("label_postprocessor", "obsidiandroid.labeling.label_postprocessor"),
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
        legacy_mod = importlib.import_module(f"ml_classification.labeling.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: ml_classification.labeling.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.labeling physical/alias submodules match legacy shims")

    # Pass 58: ``labeling.taxonomy`` is a deliberate wrapper module (not a ModuleType alias).
    taxonomy_mod = importlib.import_module("obsidiandroid.labeling.taxonomy")
    tax_path = Path(taxonomy_mod.__file__).resolve()
    if tax_path != (_REPO_ROOT / "src/obsidiandroid/labeling/taxonomy.py").resolve():
        print(
            f"FAIL: obsidiandroid.labeling.taxonomy expected at src/obsidiandroid/labeling/taxonomy.py, got {tax_path}",
            file=sys.stderr,
        )
        return 1
    import ml_classification.common.malware_family_constants as _mfc_tax

    if taxonomy_mod.normalize_family_name("Flu-Bot") != _mfc_tax.normalize_family_name("Flu-Bot"):
        print("FAIL: labeling.taxonomy.normalize_family_name diverged from legacy", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.labeling.taxonomy wrapper resolves and matches legacy normalization")

    mfc_canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    mfc_legacy = importlib.import_module("ml_classification.common.malware_family_constants")
    if mfc_legacy is not mfc_canon:
        print(
            "FAIL: ml_classification.common.malware_family_constants did not resolve to "
            "obsidiandroid.labeling.malware_family_constants",
            file=sys.stderr,
        )
        return 1
    print("OK   malware-family constants canonical module matches legacy shim")

    _cb_facade = importlib.import_module("obsidiandroid.classification_builder")
    _cb_submods = (
        "classification_constants",
        "classification_row_builder",
        "prediction_utils",
        "record_enrichment",
        "sample_classification_builder",
        "vendor_record_selector",
    )
    for name in _cb_submods:
        canon_cb = importlib.import_module(f"obsidiandroid.classification_builder.{name}")
        facade_cb = getattr(_cb_facade, name)
        if facade_cb is not canon_cb:
            print(
                f"FAIL: obsidiandroid.classification_builder.{name} facade mismatch vs canonical submodule",
                file=sys.stderr,
            )
            return 1
        legacy_cb = importlib.import_module(f"ml_classification.builder.{name}")
        if legacy_cb is not canon_cb:
            print(
                f"FAIL: ml_classification.builder.{name} did not resolve to "
                f"obsidiandroid.classification_builder.{name}",
                file=sys.stderr,
            )
            return 1
    del _cb_facade, _cb_submods, name, canon_cb, facade_cb, legacy_cb
    print("OK   obsidiandroid.classification_builder matches ml_classification.builder shims")

    _vendors_facade = importlib.import_module("obsidiandroid.vendors")
    _vendors_parsing_pkg = importlib.import_module("obsidiandroid.vendors.parsing")
    _vendors_pairs = (
        ("vendor_parser_map", "obsidiandroid.vendors.parsing.vendor_parser_map"),
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
        legacy_mod = importlib.import_module(f"analysis.vendor_processing.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: import analysis.vendor_processing.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.vendors top-level aliases match obsidiandroid.vendors.parsing + legacy shim")

    _vendors_parsing_pairs = (
        "generic_label_parser",
        "vendor_parser_map",
        "parser_defaults",
        "parser_confidence_estimator",
    )
    for name in _vendors_parsing_pairs:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{name}")
        pkg_attr = getattr(_vendors_parsing_pkg, name)
        if pkg_attr is not canon_mod:
            print(
                f"FAIL: obsidiandroid.vendors.parsing.{name} package attr mismatch",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.vendor_processing.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.vendor_processing.{name} legacy shim mismatch",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.vendors.parsing key modules preserve identity with legacy shim")

    # Pass 60: model.parsing / model.vendor physical move to obsidiandroid.vendors.contracts.
    contracts_pairs = (
        ("parsed_label_metadata", "model.parsing.parsed_label_metadata"),
        ("record_core", "model.vendor.record_core"),
        ("feature_engine", "model.vendor.feature_engine"),
        ("record_diagnostics", "model.core.record_diagnostics"),
        ("metadata_normalizer", "model.utils.metadata_normalizer"),
    )
    for canon_name, legacy_name in contracts_pairs:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.contracts.{canon_name}")
        legacy_mod = importlib.import_module(legacy_name)
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: {legacy_name} did not resolve to obsidiandroid.vendors.contracts.{canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   model.parsing/model.vendor/model core helper shims match obsidiandroid.vendors.contracts")

    risk_band_config = importlib.import_module("obsidiandroid.risk_band.risk_band_config")
    legacy_risk_band_config = importlib.import_module("model.core.risk_band_config")
    if legacy_risk_band_config is not risk_band_config:
        print(
            "FAIL: model.core.risk_band_config did not resolve to obsidiandroid.risk_band.risk_band_config",
            file=sys.stderr,
        )
        return 1
    print("OK   model.core.risk_band_config shim matches obsidiandroid.risk_band.risk_band_config")

    # Passes 61–63: evaluation physical moves; legacy package registers identity.
    eval_pairs = (
        "accuracy_band_utils",
        "av_results_fetcher",
        "engine_scoring_summary",
        "evaluate_av_classifications",
        "ml_comparator_summary",
        "ml_eval_engine",
        "ml_report_builder",
        "model_tuning",
        "random_forest_diagnostics",
        "vendor_classification_inspector",
        "vendor_classification_parser",
        "vendor_feature_extractor",
        "vendor_parser_matching",
        "vendor_parser_utils",
        "vendor_score_calculator",
        "vendor_summary_builder",
    )
    for name in eval_pairs:
        canon_mod = importlib.import_module(f"obsidiandroid.evaluation.{name}")
        legacy_mod = importlib.import_module(f"analysis.evaluation.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.evaluation.{name} did not resolve to obsidiandroid.evaluation.{name}",
                file=sys.stderr,
            )
            return 1
    print("OK   analysis.evaluation package shim matches obsidiandroid.evaluation")

    _ml_cls_eval_three = ("ml_eval_engine", "ml_comparator_summary", "accuracy_band_utils")
    for mod in _ml_cls_eval_three:
        canon_ml = importlib.import_module(f"obsidiandroid.evaluation.{mod}")
        legacy_ml = importlib.import_module(f"ml_classification.ml_utils.{mod}")
        if legacy_ml is not canon_ml:
            print(
                f"FAIL: ml_classification.ml_utils.{mod} did not resolve to "
                f"obsidiandroid.evaluation.{mod}",
                file=sys.stderr,
            )
            return 1
    canon_rb = importlib.import_module("obsidiandroid.evaluation.ml_report_builder")
    legacy_rb = importlib.import_module("ml_classification.reporting.ml_report_builder")
    if legacy_rb is not canon_rb:
        print(
            "FAIL: ml_classification.reporting.ml_report_builder did not resolve to "
            "obsidiandroid.evaluation.ml_report_builder",
            file=sys.stderr,
        )
        return 1
    splitter_canon = importlib.import_module("obsidiandroid.modeling.dataset_splitter")
    splitter_legacy = importlib.import_module("ml_classification.ml_utils.dataset_splitter")
    if splitter_legacy is not splitter_canon:
        print(
            "FAIL: ml_classification.ml_utils.dataset_splitter did not resolve to "
            "obsidiandroid.modeling.dataset_splitter",
            file=sys.stderr,
        )
        return 1
    del mod, canon_ml, legacy_ml, _ml_cls_eval_three, canon_rb, legacy_rb, splitter_canon, splitter_legacy

    # Vendor execution: physical move from analysis.execution to obsidiandroid.vendors.execution.
    exec_pairs = (
        "av_parser_executor",
        "vendor_parser_runner",
        "vendor_record_factory",
        "vendor_classification_processor",
    )
    for name in exec_pairs:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.execution.{name}")
        legacy_mod = importlib.import_module(f"analysis.execution.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.execution.{name} did not resolve to obsidiandroid.vendors.execution.{name}",
                file=sys.stderr,
            )
            return 1
    print("OK   analysis.execution package shim matches obsidiandroid.vendors.execution")

    _governance_facade = importlib.import_module("obsidiandroid.governance")
    _governance_pairs = (
        ("exceptions", "obsidiandroid.governance.exceptions"),
        ("integrity", "obsidiandroid.governance.integrity"),
        ("policy", "obsidiandroid.governance.policy"),
        ("readiness", "obsidiandroid.governance.readiness"),
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
        legacy_mod = importlib.import_module(f"analysis.pipeline.governance.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.governance.{attr} legacy shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.governance pipeline governance matches legacy shims (Pass 75)")

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
    _diag_names = (
        "ablation_cohort_diagnostics",
        "alignment_gap_diagnostics",
        "cohort_foundation_export",
        "cohort_sample_id_audit",
        "cohort_vocabulary",
        "feature_builder_drop_trace",
        "feature_build_coverage_export",
        "feature_column_survival_export",
        "feature_lineage_report",
        "feature_matrix_gap_lineage",
        "fused_permission_matrix_audit",
        "output_artifact_policy",
        "output_inventory",
        "permission_training_survival_audit",
        "rf_feature_importance_export",
        "split_ledger_resolve",
    )
    for name in _diag_names:
        canon_mod = importlib.import_module(f"obsidiandroid.diagnostics.{name}")
        legacy_mod = importlib.import_module(f"analysis.diagnostics.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.diagnostics.{name} did not resolve to "
                f"obsidiandroid.diagnostics.{name}",
                file=sys.stderr,
            )
            return 1
        facade_mod = getattr(diag_facade, name)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.diagnostics.{name} facade mismatch vs canonical",
                file=sys.stderr,
            )
            return 1
    _diag_pkg_names = ("research_validity", "hostile_audit")
    for pkg_name in _diag_pkg_names:
        canon_pkg = importlib.import_module(f"obsidiandroid.diagnostics.{pkg_name}")
        legacy_pkg = importlib.import_module(f"analysis.diagnostics.{pkg_name}")
        if legacy_pkg is not canon_pkg:
            print(
                f"FAIL: analysis.diagnostics.{pkg_name} did not resolve to "
                f"obsidiandroid.diagnostics.{pkg_name}",
                file=sys.stderr,
            )
            return 1
        if getattr(diag_facade, pkg_name) is not canon_pkg:
            print(
                f"FAIL: obsidiandroid.diagnostics.{pkg_name} façade mismatch vs canonical package",
                file=sys.stderr,
            )
            return 1

    _rv_bundle_canon = importlib.import_module("obsidiandroid.diagnostics.research_validity.bundle")
    _rv_bundle_legacy = importlib.import_module("analysis.diagnostics.research_validity.bundle")
    if _rv_bundle_legacy is not _rv_bundle_canon:
        print(
            "FAIL: research_validity.bundle identity mismatch "
            "(analysis.diagnostics vs obsidiandroid.diagnostics)",
            file=sys.stderr,
        )
        return 1
    _ha_bundle_canon = importlib.import_module("obsidiandroid.diagnostics.hostile_audit.bundle")
    _ha_bundle_legacy = importlib.import_module("analysis.diagnostics.hostile_audit.bundle")
    if _ha_bundle_legacy is not _ha_bundle_canon:
        print(
            "FAIL: hostile_audit.bundle identity mismatch "
            "(analysis.diagnostics vs obsidiandroid.diagnostics)",
            file=sys.stderr,
        )
        return 1
    print("OK   obsidiandroid.diagnostics package matches analysis.diagnostics shim")

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
