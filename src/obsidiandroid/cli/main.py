"""Direct pipeline entrypoint and compatibility exports."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib import import_module

_EXPORTS = {
    "DIAGNOSTICS_DIR": ("obsidiandroid.pipeline", "DIAGNOSTICS_DIR"),
    "PIPELINE_MAIN_LOGGER": ("obsidiandroid.pipeline", "PIPELINE_MAIN_LOGGER"),
    "PARSER_QUALITY_PATH": ("obsidiandroid.pipeline", "PARSER_QUALITY_PATH"),
    "run_pipeline": ("obsidiandroid.pipeline", "run_pipeline"),
    "_apply_confusion_matrix_policy": (
        "obsidiandroid.orchestration.runtime_reporting", "apply_confusion_matrix_policy"
    ),
    "_enforce_duplicate_sha_policy": (
        "obsidiandroid.orchestration.runtime_reporting", "enforce_duplicate_sha_policy"
    ),
    "_export_model_config_snapshot": (
        "obsidiandroid.orchestration.runtime_reporting", "export_model_config_snapshot"
    ),
    "finalize_run_manifest_stage": (
        "obsidiandroid.pipeline.stage_manifest", "finalize_run_manifest_stage"
    ),
    "load_and_prepare_samples": (
        "obsidiandroid.pipeline.stage_samples", "load_and_prepare_samples"
    ),
    "run_av_analysis_stage": (
        "obsidiandroid.pipeline.stage_av_vendor", "run_av_analysis_stage"
    ),
    "profile_manager": ("obsidiandroid.cli.profile_manager", None),
    "runtime_logging": ("obsidiandroid.observability.logging.runtime", None),
}

__all__ = ["main", *_EXPORTS]


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr = target
    module = import_module(module_path)
    return module if attr is None else getattr(module, attr)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the full malware classification workflow."""
    parser = argparse.ArgumentParser(description=main.__doc__, allow_abbrev=False)
    parser.add_argument("--allow-evidence-override", action="store_true")
    parser.add_argument("--allow-global-artifacts", action="store_true")
    options = parser.parse_args(argv)

    # Resolve only after argparse has handled help or rejected invalid input.
    execute = globals()["run_pipeline"] if "run_pipeline" in globals() else __getattr__("run_pipeline")
    return execute(
        allow_evidence_override=options.allow_evidence_override,
        allow_global_artifacts=options.allow_global_artifacts,
    )


def pipeline_exit_code() -> int:
    """Run the direct CLI with its shared Ctrl+C exit status."""
    try:
        return main()
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Pipeline aborted by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(pipeline_exit_code())
