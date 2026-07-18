"""Regression checks for canonical package facades."""

from __future__ import annotations

from pathlib import Path


def test_ml_facades_match_ml_classification_modules() -> None:
    """Canonical ML facades preserve their retained compatibility-module identities."""
    import importlib

    from obsidiandroid.features.features_facade_manifest import FEATURES_FACADE_ALIAS_TARGETS
    from obsidiandroid.modeling.modeling_facade_manifest import (
        MODELING_FACADE_EAGER_SUBMODULE_NAMES,
    )

    import obsidiandroid.features as features_facade
    import obsidiandroid.modeling as modeling_facade

    for attr in MODELING_FACADE_EAGER_SUBMODULE_NAMES:
        canon_name = f"obsidiandroid.modeling.{attr}"
        canon_mod = importlib.import_module(canon_name)
        assert getattr(modeling_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.modeling.{attr}")
        assert alias_mod is canon_mod
    for attr, canon_name in FEATURES_FACADE_ALIAS_TARGETS:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(features_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.features.{attr}")
        assert alias_mod is canon_mod

def test_labeling_taxonomy_is_wrapper_not_legacy_module_alias() -> None:
    """The canonical taxonomy module wraps helpers rather than aliasing them."""
    import importlib
    from pathlib import Path

    tax = importlib.import_module("obsidiandroid.labeling.taxonomy")
    canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    assert tax is not canon
    path = Path(tax.__file__).resolve()
    assert path.name == "taxonomy.py"
    assert "obsidiandroid" in path.parts and "labeling" in path.parts
    assert tax.normalize_family_name("Flu-Bot") == canon.normalize_family_name("Flu-Bot")


def test_taxonomy_module_is_canonical_src_file() -> None:
    """The taxonomy wrapper must remain a canonical source file, not an alias shim."""
    import obsidiandroid.labeling.malware_family_constants as canon_constants
    import obsidiandroid.labeling.taxonomy as taxonomy

    path = Path(taxonomy.__file__).resolve()
    assert path.name == "taxonomy.py"
    assert path.parts[-3:-1] == ("obsidiandroid", "labeling")
    for raw in ("HQWar", "Flu-Bot", 15, "Cabassous", "", None):
        assert taxonomy.normalize_family_name(raw) == canon_constants.normalize_family_name(raw)


def test_taxonomy_public_functions_match_canonical_constants() -> None:
    import obsidiandroid.labeling.malware_family_constants as canon_constants
    import obsidiandroid.labeling.taxonomy as taxonomy

    for raw in ("HQWar", "Flu-Bot", 15, "Cabassous", "", None):
        assert taxonomy.normalize_family_name(raw) == canon_constants.normalize_family_name(raw)

    assert taxonomy.is_known_family_name("hqwar") == canon_constants.is_known_family_name("hqwar")
    assert taxonomy.is_known_family_name("TrickMo") == canon_constants.is_known_family_name("TrickMo")
    assert taxonomy.canonicalize_family_label("Cabassous") == canon_constants.canonicalize_family_label("Cabassous")


def test_taxonomy_functions_are_not_constants_object_identity() -> None:
    """Wrappers deliberately do not re-export underlying function objects."""
    import obsidiandroid.labeling.malware_family_constants as canon_constants
    import obsidiandroid.labeling.taxonomy as taxonomy

    assert taxonomy.normalize_family_name is not canon_constants.normalize_family_name
    assert taxonomy.is_known_family_name is not canon_constants.is_known_family_name
    assert taxonomy.canonicalize_family_label is not canon_constants.canonicalize_family_label


def test_malware_family_constants_canonical_behavior() -> None:
    """Malware-family constants live canonically under ``obsidiandroid.labeling``."""
    import importlib

    canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    assert canon.normalize_family_name("Flu-Bot") == "flubot"
    assert canon.canonicalize_family_label("Cabassous") == "FluBot"
    assert canon.normalize_family_name("Toxic Panda") == "toxicpanda"
    assert canon.canonicalize_family_label("GravityRAT") == "GravityRAT"
    assert canon.normalize_family_name("PixPirate") == "pixpirate"
    assert canon.canonicalize_family_label("BlankBot") == "BlankBot"
    assert canon.normalize_family_name("OTPStealer") == "otpstealer"
    assert canon.canonicalize_family_label("OTPStealer") == "OTPStealer"
    assert canon.normalize_family_name("Arsink RAT") == "arsinkrat"
    assert canon.canonicalize_family_label("Arsink RAT") == "ArsinkRAT"
    assert canon.normalize_family_name("Fantasy Hub") == "fantasyhub"
    assert canon.canonicalize_family_label("Fantasy Hub") == "FantasyHub"
    assert canon.normalize_family_name("Recruit Rat") == "recruitrat"
    assert canon.normalize_family_name("Taxi Spy RAT") == "taxispyrat"
    assert canon.normalize_family_name("Play Praetors") == "playpraetors"
    assert canon.normalize_family_name("Droid Lock") == "droidlock"
    assert canon.normalize_family_name("Metasploit") == "unknown"
    assert canon.canonicalize_family_label("Trojan.MetaSploit") == "unknown"


def test_ml_classification_ml_utils_namespace_is_retired() -> None:
    """``ml_utils`` compatibility imports are intentionally retired."""
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.ml_utils")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.ml_utils.distribution_reporter")


def test_ml_classification_training_namespace_is_retired() -> None:
    """Legacy training compatibility imports are intentionally retired."""
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training.pipeline_core")


def test_ml_classification_training_ml_trainers_namespace_is_retired() -> None:
    """Legacy trainer subpackage imports are intentionally retired."""
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training.ml_trainers")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training.ml_trainers.random_forest_trainer")


def test_labeling_classification_builder_inference_and_engine_weights_packages_export_canonical_modules() -> None:
    """Canonical package attributes expose the remaining physically canonical helper modules."""
    import importlib

    package_to_names = {
        "obsidiandroid.labeling": (
            "classification_label_resolver",
            "label_builder_wrapper",
            "label_field_normalizer",
            "label_format_generator",
            "label_input_validator",
            "label_postprocessor",
        ),
        "obsidiandroid.classification_builder": (
            "classification_constants",
            "classification_row_builder",
            "prediction_utils",
            "record_enrichment",
            "sample_classification_builder",
            "vendor_record_selector",
        ),
        "obsidiandroid.inference": (
            "label_consensus_engine",
            "malware_type_engine",
            "signal_health_checker",
            "threat_class_engine",
        ),
        "obsidiandroid.engine_weights": (
            "assign_detection_tiers",
            "build_classification_weights",
            "classification_weight_inspector",
            "classification_weight_utils",
            "compute_reliability_score",
            "engine_weights_utils",
        ),
    }
    for pkg_name, names in package_to_names.items():
        pkg = importlib.import_module(pkg_name)
        for name in names:
            sub = importlib.import_module(f"{pkg_name}.{name}")
            assert getattr(pkg, name) is sub

def test_vendors_facade_matches_vendor_processing_modules() -> None:
    """The vendors facade points at the canonical parsing package."""
    import importlib

    import obsidiandroid.vendors as vendors_facade

    canon_mod = importlib.import_module("obsidiandroid.vendors.parsing.vendor_parser_map")
    assert getattr(vendors_facade, "vendor_parser_map") is canon_mod
    alias_mod = importlib.import_module("obsidiandroid.vendors.vendor_parser_map")
    assert alias_mod is canon_mod


def test_vendors_parsing_modules_match_package_attributes() -> None:
    """Vendor parser package attributes resolve to canonical submodules."""
    import importlib

    from obsidiandroid.vendors.parsing.vendor_parser_submodule_manifest import (
        VENDOR_PARSER_SUBMODULE_NAMES,
    )

    import obsidiandroid.vendors.parsing as parsing_pkg

    for name in VENDOR_PARSER_SUBMODULE_NAMES:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{name}")
        assert getattr(parsing_pkg, name) is canon_mod


def test_evaluation_package_exports_canonical_modules() -> None:
    """Evaluation package attributes resolve to canonical submodules."""
    import importlib

    import obsidiandroid.evaluation as evaluation_pkg

    for name in evaluation_pkg.__all__:
        if name in {"VendorClassificationParseResult", "parse_vendor_classifications"}:
            continue
        canon_mod = importlib.import_module(f"obsidiandroid.evaluation.{name}")
        assert getattr(evaluation_pkg, name) is canon_mod

    for mod in ("ml_eval_engine", "ml_comparator_summary", "accuracy_band_utils"):
        importlib.import_module(f"obsidiandroid.evaluation.{mod}")


def test_vendor_execution_package_exports_match_canonical_modules() -> None:
    """Vendor execution package exports resolve to canonical submodules."""
    import importlib

    import obsidiandroid.vendors.execution as execution_pkg

    for name in execution_pkg.__all__:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.execution.{name}")
        assert canon_mod.__name__ == f"obsidiandroid.vendors.execution.{name}"

def test_diagnostics_facade_modules_match_canonical_submodules() -> None:
    """Diagnostics package attributes resolve to canonical submodules."""
    import importlib

    import obsidiandroid.diagnostics as facade

    top_level_names = (
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
        "family_label_taxonomy_audit",
        "reproducibility_workbench",
        "fused_permission_matrix_audit",
        "headline_evaluation_export",
        "output_artifact_policy",
        "rf_feature_importance_export",
        "split_ledger_resolve",
        "output_inventory",
        "permission_training_survival_audit",
    )
    for name in top_level_names:
        canon = importlib.import_module(f"obsidiandroid.diagnostics.{name}")
        assert getattr(facade, name) is canon

    for pkg in ("research_validity", "hostile_audit"):
        canon_pkg = importlib.import_module(f"obsidiandroid.diagnostics.{pkg}")
        assert getattr(facade, pkg) is canon_pkg
        bundle_canon = importlib.import_module(f"obsidiandroid.diagnostics.{pkg}.bundle")
        assert bundle_canon is getattr(canon_pkg, "bundle")


def test_database_facade_modules_resolve_canonically() -> None:
    """``obsidiandroid.database`` exposes canonical façade modules."""
    import importlib

    from obsidiandroid.database.facade_manifest import FACADE_MODULE_PAIRS

    import obsidiandroid.database as facade

    for attr, canon_name in FACADE_MODULE_PAIRS:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(facade, attr) is canon_mod
        assert importlib.import_module(f"obsidiandroid.database.{attr}") is canon_mod
