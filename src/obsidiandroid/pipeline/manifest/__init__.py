"""Pipeline manifest helpers (hashing, writer, paper exports, runtime support).

Implementation is canonical under ``obsidiandroid.pipeline.manifest`` (**Pass 76**);
``analysis.pipeline.manifest`` is an identity shim to this package and its submodules.
"""

from __future__ import annotations

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
