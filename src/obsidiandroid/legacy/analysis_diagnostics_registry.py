"""Legacy ``analysis.diagnostics`` shim registry."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

_CANONICAL_ROOT = "obsidiandroid.diagnostics"
_LEGACY_ROOT = "analysis.diagnostics"
_SHIM_STEM = "analysis_diagnostics_registry"

DIAGNOSTICS_NESTED_LEGACY_PACKAGES: tuple[str, ...] = ("research_validity", "hostile_audit")


def _ensure_same_object(legacy_modname: str, canon_modname: str) -> None:
    canon = importlib.import_module(canon_modname)
    sys.modules.setdefault(legacy_modname, canon)


def _public_top_level_module_names() -> tuple[str, ...]:
    here = Path(importlib.import_module(_CANONICAL_ROOT).__file__).resolve().parent
    names: list[str] = []
    for path in sorted(here.glob("*.py")):
        stem = path.stem
        if stem.startswith("_") or stem in {"__init__", "analysis_diagnostics_shim", _SHIM_STEM}:
            continue
        names.append(stem)
    return tuple(names)


DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES: tuple[str, ...] = _public_top_level_module_names()


def register_analysis_diagnostics_legacy_aliases() -> None:
    """Wire ``analysis.diagnostics.<suffix>`` to canonical ``obsidiandroid.diagnostics`` modules."""
    for name in DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES:
        _ensure_same_object(f"{_LEGACY_ROOT}.{name}", f"{_CANONICAL_ROOT}.{name}")

    for pkg in DIAGNOSTICS_NESTED_LEGACY_PACKAGES:
        pkg_canon_name = f"{_CANONICAL_ROOT}.{pkg}"
        canon_pkg = importlib.import_module(pkg_canon_name)
        sys.modules.setdefault(f"{_LEGACY_ROOT}.{pkg}", canon_pkg)

        pkg_path = canon_pkg.__name__ + "."
        if not getattr(canon_pkg, "__path__", None):
            continue
        for _finder, modname, _ispkg in pkgutil.walk_packages(canon_pkg.__path__, pkg_path):
            canon_mod = importlib.import_module(modname)
            suffix = modname.removeprefix(_CANONICAL_ROOT + ".")
            sys.modules.setdefault(f"{_LEGACY_ROOT}.{suffix}", canon_mod)


__all__ = (
    "DIAGNOSTICS_NESTED_LEGACY_PACKAGES",
    "DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES",
    "register_analysis_diagnostics_legacy_aliases",
)
