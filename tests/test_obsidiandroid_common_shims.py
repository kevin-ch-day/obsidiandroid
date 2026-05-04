"""Canonical vs legacy ``utils`` shim identity for ``obsidiandroid.common`` migration."""

from __future__ import annotations

import obsidiandroid.common.canonicalization as canon_pkg
import obsidiandroid.common.display_distribution as dist_pkg
import obsidiandroid.common.hash_utils as hash_pkg
import obsidiandroid.common.ml_console as console_pkg
import obsidiandroid.common.path_safety as path_pkg
import obsidiandroid.common.runtime_paths as rt_pkg
from utils import canonicalization as canon_shim
from utils import display_distribution as dist_shim
from utils import hash_utils as hash_shim
from utils import ml_console as ml_shim
from utils import path_safety as path_shim
from utils import runtime_paths as rt_shim


def test_hash_utils_shim_is_canonical() -> None:
    assert hash_shim.sha256_hex is hash_pkg.sha256_hex
    assert hash_shim.hash_payload is hash_pkg.hash_payload
    assert hash_shim.short_hash is hash_pkg.short_hash
    assert hash_shim.canonical_json_bytes is hash_pkg.canonical_json_bytes


def test_canonicalization_shim_is_canonical() -> None:
    assert canon_shim.normalize_sha256 is canon_pkg.normalize_sha256
    assert canon_shim.canonical_csv_bytes is canon_pkg.canonical_csv_bytes
    assert canon_shim.SHA256_PATTERN is canon_pkg.SHA256_PATTERN


def test_path_safety_shim_is_canonical() -> None:
    assert path_shim.safe_join is path_pkg.safe_join
    assert path_shim.UnsafePathError is path_pkg.UnsafePathError


def test_runtime_paths_shim_is_canonical() -> None:
    assert rt_shim.resolve_diagnostics_dir is rt_pkg.resolve_diagnostics_dir


def test_ml_console_shim_is_canonical() -> None:
    assert ml_shim.get_mode is console_pkg.get_mode
    assert ml_shim.is_minimal is console_pkg.is_minimal
    assert ml_shim.is_research is console_pkg.is_research
    assert ml_shim.is_debug is console_pkg.is_debug
    assert ml_shim.show_debug_tables is console_pkg.show_debug_tables


def test_display_distribution_shim_is_canonical() -> None:
    assert dist_shim.print_distribution is dist_pkg.print_distribution
