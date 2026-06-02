"""Shared operator-state resolution for startup and diagnostics menus."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from obsidiandroid.common.cohort_artifacts import load_cohort_contract_state
from obsidiandroid.common.cohort_methodology import (
    extract_taxonomy_label_drift,
    resolve_cohort_lock_status,
)
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.common.publication_readiness import coalesce_publication_ready_status
from obsidiandroid.governance.evidence_mode_resolver import (
    coalesce_manifest_evidence_mode,
    coalesce_manifest_publication_mode,
)

from obsidiandroid.cli.menu import run_locator
from obsidiandroid.cli.menu.display_mode import resolve_display_mode
from obsidiandroid.cli.menu.vendor_parser_state import get_parser_summary_state


def output_root() -> Path:
    """Return configured output root."""
    return canonical_output_root()


def resolve_best_run_index_path(run_root: Path) -> tuple[Path, bool]:
    """Return best available authoritative run index and canonical-presence flag."""
    diagnostics_dir = run_root / "diagnostics"
    canonical = diagnostics_dir / "run_science_index.md"
    candidates = [
        canonical,
        run_root / "run_evidence_index.md",
        diagnostics_dir / "index.md",
        diagnostics_dir / "run_artifact_index.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate, candidate == canonical
    return canonical, False


def publication_exports_available(run_id: str | None, *, base: Path) -> bool:
    token = str(run_id or "").strip()
    if not token:
        return False
    paper_dir = run_locator.resolve_run_root_for_run_id(token, output_base=base) / "paper_exports"
    return paper_dir.exists() and paper_dir.is_dir()


def has_structural_bundle(run_id: str | None, *, base: Path) -> bool:
    token = str(run_id or "").strip()
    if not token:
        return False
    bundle_dir = run_locator.resolve_run_root_for_run_id(token, output_base=base) / "bundles" / "permission_trends"
    return bundle_dir.exists() and bundle_dir.is_dir()


def latest_run_has_provenance(run_id: str | None, *, base: Path) -> bool:
    token = str(run_id or "").strip()
    if not token:
        return False
    diagnostics = run_locator.resolve_run_root_for_run_id(token, output_base=base) / "diagnostics"
    split_ledger = diagnostics / f"split_freeze_headline_{token}.csv"
    required = [
        split_ledger,
        diagnostics / f"run_paths_manifest_{token}.json",
        diagnostics / f"experiment_registry_{token}.json",
    ]
    return all(path.exists() for path in required)


def latest_run_has_diagnostics(run_id: str | None, *, base: Path) -> bool:
    """Return whether any run-scoped diagnostics artifacts exist for a given run."""
    token = str(run_id or "").strip()
    if not token:
        return False
    diagnostics = run_locator.resolve_run_root_for_run_id(token, output_base=base) / "diagnostics"
    if not diagnostics.is_dir():
        return False
    try:
        return any(diagnostics.iterdir())
    except OSError:
        return False


def _resolve_cohort_contract_state(run_root: Path, run_id: str) -> dict[str, Any]:
    """Resolve run-scoped cohort filter contract artifacts for operator surfaces."""
    return load_cohort_contract_state(diagnostics_dir=run_root / "diagnostics", run_id=run_id)


def build_operator_state(*, output_base: Path | None = None, run_id: str | None = None) -> dict[str, Any]:
    """Build shared operator-facing state for the latest run and workspace."""
    display_mode = resolve_display_mode()
    base = Path(output_base).resolve() if output_base is not None else output_root().resolve()
    latest_run_id = run_locator.read_latest_run_id()
    locked_run_id = run_locator.read_locked_publication_run_id()
    manifest, resolved_run_id, manifest_path = run_locator.resolve_latest_manifest_payload(output_base=base)
    effective_run_id = str(run_id or resolved_run_id or latest_run_id or "").strip()
    if effective_run_id and effective_run_id != str(resolved_run_id or "").strip():
        manifest, manifest_path = run_locator.resolve_manifest_for_run_id(effective_run_id)
        resolved_run_id = effective_run_id
    run_root = (
        run_locator.resolve_run_root_for_run_id(effective_run_id, output_base=base)
        if effective_run_id
        else Path()
    )
    diagnostics_dir = run_root / "diagnostics" if effective_run_id else Path()
    canonical_manifest_path = run_root / "run_manifest.json" if effective_run_id else Path()
    best_index_path, has_canonical_run_science = (
        resolve_best_run_index_path(run_root) if effective_run_id else (Path(), False)
    )
    cohort_contract_state = (
        _resolve_cohort_contract_state(run_root, effective_run_id)
        if effective_run_id
        else {
            "cohort_filter_summary_path": Path(),
            "cohort_filter_summary": {},
            "cohort_filter_contract_path": Path(),
            "cohort_filter_contract": {},
            "cohort_gate_counts_path": Path(),
            "cohort_gate_rows": [],
            "cohort_membership_mode": "standard_contract_filters",
            "cohort_membership_authority_note": "",
            "min_malicious_detections_threshold": 0,
            "min_malicious_detections_rescued_unknown_consensus": 0,
        }
    )

    profile_params = manifest.get("profile_params") if isinstance(manifest.get("profile_params"), dict) else {}
    profile_id = str(profile_params.get("profile_id", "") or "").strip()
    publication_ready_status = coalesce_publication_ready_status(
        manifest if isinstance(manifest, dict) else {}
    )
    evidence_mode = coalesce_manifest_evidence_mode(manifest.get("evidence_mode")) if isinstance(manifest, dict) else False
    publication_ready_mode = coalesce_manifest_publication_mode(manifest if isinstance(manifest, dict) else None)
    cohort_lock_status = resolve_cohort_lock_status(manifest if isinstance(manifest, dict) else {})
    taxonomy_label_drift = extract_taxonomy_label_drift(manifest if isinstance(manifest, dict) else {})

    return {
        "display_mode": display_mode,
        "output_root": base,
        "latest_run_id": effective_run_id,
        "locked_run_id": str(locked_run_id or "").strip(),
        "locked_publication_run_id": str(locked_run_id or "").strip(),
        "manifest_path": manifest_path,
        "manifest_payload": manifest if isinstance(manifest, dict) else {},
        "resolved_run_id": str(resolved_run_id or "").strip(),
        "run_root": run_root,
        "diagnostics_dir": diagnostics_dir,
        "canonical_manifest_path": canonical_manifest_path,
        "profile_id": profile_id,
        "latest_run_has_provenance": latest_run_has_provenance(effective_run_id, base=base),
        "latest_run_has_diagnostics": latest_run_has_diagnostics(effective_run_id, base=base),
        "has_publication_exports": publication_exports_available(effective_run_id, base=base),
        "has_structural_bundle": has_structural_bundle(effective_run_id, base=base),
        "publication_ready_status": publication_ready_status,
        "cohort_lock_status": cohort_lock_status,
        "taxonomy_label_drift": taxonomy_label_drift,
        "evidence_mode": evidence_mode,
        "publication_ready_mode": publication_ready_mode,
        "has_locked_publication_run": bool(str(locked_run_id or "").strip()),
        "best_run_index_path": best_index_path,
        "has_canonical_run_science": has_canonical_run_science,
        "parser_summary": get_parser_summary_state(mode=display_mode),
        **cohort_contract_state,
    }


__all__ = [
    "build_operator_state",
    "has_structural_bundle",
    "latest_run_has_diagnostics",
    "latest_run_has_provenance",
    "output_root",
    "publication_exports_available",
    "resolve_best_run_index_path",
]
