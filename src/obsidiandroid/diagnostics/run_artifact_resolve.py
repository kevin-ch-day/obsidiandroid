"""Resolve run-scoped artifacts across diagnostics and permission-trends bundles."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.common.output_hygiene import global_diagnostics_root


def permission_trends_bundle_dirs(diagnostics_dir: Path, run_id: str) -> list[Path]:
    """Return bundle artifact dirs associated with a run diagnostics tree."""
    run_root = diagnostics_dir.parent if diagnostics_dir.name == "diagnostics" else diagnostics_dir
    dirs: list[Path] = []
    bundle_root = run_root / "bundles" / "permission_trends"
    if bundle_root.is_dir():
        for sub in ("tables", "contracts", "docs", "figures"):
            path = bundle_root / sub
            if path.is_dir():
                dirs.append(path)
    # Legacy layout: output/runs/<run_id>/bundles/permission_trends
    legacy_root = run_root.parent / str(run_id or "").strip() / "bundles" / "permission_trends"
    if legacy_root.is_dir() and legacy_root != bundle_root:
        for sub in ("tables", "contracts", "docs", "figures"):
            path = legacy_root / sub
            if path.is_dir() and path not in dirs:
                dirs.append(path)
    return dirs


def _glob_bundle_match(bundle_dir: Path, stem: str, suffix: str) -> Path | None:
    """Match bundle artifacts when only a stamped filename exists (no .latest in run dir)."""
    exact = bundle_dir / f"{stem}{suffix}"
    if exact.is_file():
        return exact
    pattern = f"{stem}_*{suffix}"
    matches = sorted(bundle_dir.glob(pattern))
    if matches:
        return matches[-1]
    return None


def resolve_run_artifact_path(
    diagnostics_dir: Path,
    *,
    stem: str,
    run_id: str,
    suffix: str,
) -> Path | None:
    """Find a run artifact under diagnostics, bundles, or global latest mirrors."""
    diagnostics_dir = Path(diagnostics_dir)
    token_stem = str(stem or "").strip()
    token_suffix = str(suffix or "").strip()
    if not token_stem or not token_suffix:
        return None

    run_path = diagnostics_dir / f"{token_stem}_{run_id}{token_suffix}"
    if run_path.is_file():
        return run_path
    latest = diagnostics_dir / f"{token_stem}.latest{token_suffix}"
    if latest.is_file():
        return latest

    for bundle_dir in permission_trends_bundle_dirs(diagnostics_dir, run_id):
        bundle_run = bundle_dir / f"{token_stem}_{run_id}{token_suffix}"
        if bundle_run.is_file():
            return bundle_run
        bundle_latest = bundle_dir / f"{token_stem}.latest{token_suffix}"
        if bundle_latest.is_file():
            return bundle_latest
        glob_match = _glob_bundle_match(bundle_dir, token_stem, token_suffix)
        if glob_match is not None:
            return glob_match

    global_latest = global_diagnostics_root() / f"{token_stem}.latest{token_suffix}"
    if global_latest.is_file():
        return global_latest
    return None


def resolve_related_artifact_ref(
    diagnostics_dir: Path,
    *,
    run_id: str,
    filename: str,
) -> str:
    """Return a resolvable relative artifact ref, preferring bundle paths when present."""
    token = str(filename or "").strip()
    if not token:
        return ""
    direct = Path(diagnostics_dir) / token
    if direct.is_file():
        return token
    for suffix in (".csv", ".json", ".md"):
        if not token.endswith(suffix):
            continue
        stem = token[: -len(suffix)]
        if stem.endswith(f"_{run_id}"):
            stem = stem[: -len(f"_{run_id}")]
        elif stem.endswith(".latest"):
            stem = stem[: -len(".latest")]
        resolved = resolve_run_artifact_path(
            diagnostics_dir,
            stem=stem,
            run_id=run_id,
            suffix=suffix,
        )
        if resolved is None:
            continue
        try:
            run_root = diagnostics_dir.parent if diagnostics_dir.name == "diagnostics" else diagnostics_dir
            return str(resolved.relative_to(run_root))
        except ValueError:
            return str(resolved)
    return token


def run_artifact_exists(diagnostics_dir: Path, stem: str, run_id: str) -> bool:
    """Return True when any common suffix exists for the artifact stem."""
    for suffix in (".csv", ".json", ".md"):
        if resolve_run_artifact_path(diagnostics_dir, stem=stem, run_id=run_id, suffix=suffix) is not None:
            return True
    return False
