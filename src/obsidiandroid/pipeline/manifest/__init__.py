"""Pipeline manifest helpers (hashing, writer, paper exports, runtime support).

Implementation is canonical under ``obsidiandroid.pipeline.manifest`` (**Pass 76**);
``analysis.pipeline.manifest`` is an identity shim to this package and its submodules.
"""

from __future__ import annotations

import sys

from . import (
    builder,
    confusion_matrix_paths,
    hashing,
    paper2_strict_exports,
    paper_compliance_checks,
    paper_figure_renderers,
    runtime_support,
    schema,
    stage_manifest_artifacts,
    stage_manifest_evidence_pack,
    stage_manifest_writers,
    writer,
)
from .hashing import canonical_csv_bytes, dataset_hash_from_sample_ids, sha256_hex

# When ``analysis.pipeline.manifest`` is an identity shim to this package, submodule imports
# like ``analysis.pipeline.manifest.hashing`` would otherwise create a second ``ModuleType``
# for the same file. Register legacy names so checks (and monkeypatch targets) match.
_LEGACY_MANIFEST_PREFIX = "analysis.pipeline.manifest."
for _name in (
    "builder",
    "confusion_matrix_paths",
    "hashing",
    "paper2_strict_exports",
    "paper_compliance_checks",
    "paper_figure_renderers",
    "runtime_support",
    "schema",
    "stage_manifest_artifacts",
    "stage_manifest_evidence_pack",
    "stage_manifest_writers",
    "writer",
):
    sys.modules[_LEGACY_MANIFEST_PREFIX + _name] = sys.modules[__name__ + "." + _name]

__all__ = [
    "builder",
    "canonical_csv_bytes",
    "confusion_matrix_paths",
    "dataset_hash_from_sample_ids",
    "hashing",
    "paper2_strict_exports",
    "paper_compliance_checks",
    "paper_figure_renderers",
    "runtime_support",
    "schema",
    "sha256_hex",
    "stage_manifest_artifacts",
    "stage_manifest_evidence_pack",
    "stage_manifest_writers",
    "writer",
]
