#!/usr/bin/env python3
"""Read-only static audit: filesystem write call-sites that may target ``output/`` trees.

Scans Python sources with :mod:`ast` and emits CSV rows for writes whose path
expressions (unparsed) match output/diagnostics/run/bundle/latest heuristics.

This does **not** execute pipeline code or touch ``output/`` on disk. Run from
repo root::

    python scripts/dev/output_writer_audit.py --out artifacts/baselines/output_writer_audit.csv
    python scripts/dev/output_writer_audit.py   # writes CSV to stdout

**Limitations:** path arguments built across statements, or plain names like
``out_path.write_text(...)`` where ``out_path`` is not unparsed with output
hints, are **not** reported (static false negatives). Treat the CSV as a
prioritized map, not a completeness proof.

See ``make output-writer-audit`` (Makefile).
"""

from __future__ import annotations

import argparse
import ast
import csv
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]


# Path / naming hints suggesting repo output layout (not exhaustive).
_INTERESTING = re.compile(
    r"(?:"
    r"output\s*/|['\"]output['\"]|output_paths|DEFAULT_OUTPUT|"
    r"diagnostics|RUNTIME_|runs?\s*/|/runs|run_root|run_id|"
    r"bundle|paper2|promoted|conf_matrices|permission_trends|"
    r"\.latest|latest/|diagnostics_root|cohort_filter|engine_lifecycle|"
    r"model_config_snapshot|experiment_registry|run_manifest|run_summary"
    r")",
    re.IGNORECASE,
)


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _safe_unparse(node: ast.AST | None, *, limit: int = 220) -> str:
    if node is None:
        return ""
    try:
        s = ast.unparse(node).replace("\n", " ").strip()
    except (AttributeError, TypeError):
        return ""
    if len(s) > limit:
        return s[: limit - 3] + "..."
    return s


def _open_write_mode(node: ast.Call) -> bool:
    """True if ``open(...)`` appears to open for writing."""
    mode = "r"
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        if isinstance(node.args[1].value, str):
            mode = node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            mode = kw.value.value
    m = mode.lower()
    if any(x in m for x in ("w", "a", "x")):
        return True
    if "+" in m and ("w" in m or "a" in m or "x" in m):
        return True
    return False


def _hygiene_public_call(func: ast.AST) -> bool:
    """Call to ``output_hygiene`` mirror / global-latest helpers (blessed at site)."""
    try:
        s = ast.unparse(func)
    except (AttributeError, TypeError):
        return False
    if "mirror_csv_text_run_then_global" in s:
        return True
    if "write_global_latest_text" in s or "write_global_latest_bytes" in s:
        return True
    if re.search(r"\boh\.(mirror_|write_global)", s):
        return True
    if "output_hygiene." in s and ("mirror_" in s or "write_global" in s):
        return True
    return False


def _family_guess(expr: str) -> str:
    lower = expr.lower()
    if "confusion" in lower or "conf_mat" in lower:
        return "confusion_matrix"
    if "split_freeze" in lower or "split_ledger" in lower:
        return "split_ledger"
    if "ablation" in lower:
        return "ablation"
    if "vendor" in lower or "parser" in lower:
        return "vendor_parser"
    if "feature_" in lower or "feature." in lower or "lineage" in lower:
        return "feature_diagnostics"
    if "taxonomy" in lower or "label" in lower:
        return "labeling_taxonomy"
    if "bundle" in lower or "paper2" in lower or "permission_trend" in lower:
        return "bundle_or_paper_export"
    if "manifest" in lower or "run_summary" in lower:
        return "run_manifest"
    if "engine" in lower or "lifecycle" in lower:
        return "engine_av"
    if "cohort" in lower or "sample" in lower:
        return "cohort_samples"
    return "other"


def _role_guess(expr: str, *, has_latest: bool) -> str:
    lower = expr.lower()
    if has_latest and ("runs" in lower or "run_id" in lower or "runtime" in lower):
        return "operator_mirror_candidate_in_run_tree"
    if has_latest:
        return "operator_mirror_candidate"
    if "bundle" in lower or "paper2" in lower:
        return "paper_or_portable_bundle"
    if "debug" in lower or "gate_debug" in lower:
        return "debug_or_gate"
    if "run_id" in lower or "/runs/" in lower or "runs/" in lower:
        return "canonical_run_evidence"
    if "output/diagnostics" in lower or "diagnostics" in lower:
        return "diagnostics_or_global_operator"
    return "unknown_or_mixed"


def _recommend(
    *,
    hygiene_call: bool,
    in_hygiene_module: bool,
    in_export_manager: bool,
    in_artifact_registry: bool,
    has_latest: bool,
    role: str,
) -> str:
    if hygiene_call or in_hygiene_module:
        return "keep_internal_hygiene"
    if in_export_manager:
        return "keep_export_manager_orchestration"
    if in_artifact_registry:
        return "keep_registry_helpers_or_route_callers"
    if has_latest and "run" in role:
        return "route_through_mirror_suppress_local_latest"
    if has_latest:
        return "confirm_global_latest_only_or_mirror_helper"
    if "bundle" in role or "paper" in role:
        return "align_bundle_policy_with_run_capsule"
    return "review_path_policy"


def _module_flags(source: str) -> tuple[bool, bool, bool]:
    """Heuristic: does this file mention blessed layers (imports or qualified names)."""
    has_oh = bool(re.search(r"\boutput_hygiene\b|obsidiandroid\.common\.output_hygiene", source))
    has_em = bool(re.search(r"\bexport_manager\b|obsidiandroid\.reporting\.export_manager", source))
    has_ar = bool(re.search(r"\bArtifactRegistry\b|pipeline\.artifacts\.registry", source))
    return has_oh, has_em, has_ar


@dataclass(frozen=True)
class _WriteHit:
    rel_path: str
    function: str
    write_pattern: str
    target_expr: str
    line: int
    artifact_family_guess: str
    hygiene_call_site: bool
    in_hygiene_module: bool
    in_export_manager_module: bool
    in_artifact_registry_module: bool
    mod_imports_hygiene: bool
    mod_imports_export_manager: bool
    mod_imports_artifact_registry: bool
    contains_latest: bool
    likely_role: str
    recommended_action: str


def _iter_py_files(roots: Sequence[Path]) -> Iterator[Path]:
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
        elif root.is_dir():
            yield from sorted(root.rglob("*.py"))


def _classify_write_call(node: ast.Call) -> tuple[str, ast.AST | None] | None:
    """Return (pattern, path_like_arg) for interesting write APIs."""
    func = node.func
    if isinstance(func, ast.Name) and func.id == "open":
        if not node.args or not _open_write_mode(node):
            return None
        return "open", node.args[0]

    if isinstance(func, ast.Attribute):
        attr = func.attr
        if attr in ("write_text", "write_bytes"):
            return f"pathlib_{attr}", func.value
        if attr == "to_csv":
            if node.args:
                return "pandas_to_csv", node.args[0]
            for kw in node.keywords:
                if kw.arg == "path_or_buf":
                    return "pandas_to_csv", kw.value
            return "pandas_to_csv", None
        if attr == "to_json":
            if node.args:
                return "pandas_to_json", node.args[0]
            for kw in node.keywords:
                if kw.arg == "path_or_buf":
                    return "pandas_to_json", kw.value
            return "pandas_to_json", None
        if attr == "to_excel":
            if node.args:
                return "pandas_to_excel", node.args[0]
            for kw in node.keywords:
                if kw.arg == "excel_writer":
                    return "pandas_to_excel", kw.value
            return "pandas_to_excel", None
        if attr == "savefig":
            if node.args:
                return "savefig", node.args[0]
            for kw in node.keywords:
                if kw.arg == "fname":
                    return "savefig", kw.value
            return "savefig", None
        if (
            attr == "dump"
            and isinstance(func.value, ast.Name)
            and func.value.id == "json"
            and len(node.args) >= 2
        ):
            return "json_dump", node.args[1]

    return None


class _WriteCallVisitor(ast.NodeVisitor):
    def __init__(self, *, rel_path: str, source: str) -> None:
        self.rel_path = rel_path
        self.source = source
        self._stack: list[str] = []
        self.hits: list[_WriteHit] = []

        mod_oh, mod_em, mod_ar = _module_flags(source)
        self._mod_oh, self._mod_em, self._mod_ar = mod_oh, mod_em, mod_ar
        self._in_hygiene = rel_path.endswith("obsidiandroid/common/output_hygiene.py")
        self._in_export_mgr = rel_path.endswith("obsidiandroid/reporting/export_manager.py")
        self._in_art_reg = rel_path.endswith("obsidiandroid/pipeline/artifacts/registry.py")

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_Call(self, node: ast.Call) -> Any:
        if _hygiene_public_call(node.func):
            self._maybe_record_hygiene_mirror(node)
        else:
            classified = _classify_write_call(node)
            if classified is not None:
                pattern, path_ast = classified
                self._maybe_record_path_write(node, pattern, path_ast)
        self.generic_visit(node)

    def _function_label(self) -> str:
        if not self._stack:
            return "<module>"
        return ".".join(self._stack)

    def _maybe_record_hygiene_mirror(self, node: ast.Call) -> None:
        """Record public hygiene mirror / global-latest entry points."""
        expr = _safe_unparse(node)
        if not _INTERESTING.search(expr):
            return
        has_latest = ".latest" in expr or bool(
            re.search(r"['\"][^'\"]*\\.latest[^'\"]*['\"]", expr)
        )
        role = _role_guess(expr, has_latest=has_latest)
        rec = _recommend(
            hygiene_call=True,
            in_hygiene_module=self._in_hygiene,
            in_export_manager=self._in_export_mgr,
            in_artifact_registry=self._in_art_reg,
            has_latest=has_latest,
            role=role,
        )
        self.hits.append(
            _WriteHit(
                rel_path=self.rel_path,
                function=self._function_label(),
                write_pattern="output_hygiene_public_api",
                target_expr=expr,
                line=getattr(node, "lineno", 0) or 0,
                artifact_family_guess=_family_guess(expr),
                hygiene_call_site=True,
                in_hygiene_module=self._in_hygiene,
                in_export_manager_module=self._in_export_mgr,
                in_artifact_registry_module=self._in_art_reg,
                mod_imports_hygiene=self._mod_oh,
                mod_imports_export_manager=self._mod_em,
                mod_imports_artifact_registry=self._mod_ar,
                contains_latest=has_latest,
                likely_role=role,
                recommended_action=rec,
            )
        )

    def _maybe_record_path_write(self, node: ast.Call, pattern: str, path_ast: ast.AST | None) -> None:
        expr = _safe_unparse(path_ast)
        if not expr or not _INTERESTING.search(expr):
            return
        has_latest = ".latest" in expr or bool(
            re.search(r"['\"][^'\"]*\\.latest[^'\"]*['\"]", expr)
        )
        role = _role_guess(expr, has_latest=has_latest)
        rec = _recommend(
            hygiene_call=False,
            in_hygiene_module=self._in_hygiene,
            in_export_manager=self._in_export_mgr,
            in_artifact_registry=self._in_art_reg,
            has_latest=has_latest,
            role=role,
        )
        self.hits.append(
            _WriteHit(
                rel_path=self.rel_path,
                function=self._function_label(),
                write_pattern=pattern,
                target_expr=expr,
                line=getattr(node, "lineno", 0) or 0,
                artifact_family_guess=_family_guess(expr),
                hygiene_call_site=False,
                in_hygiene_module=self._in_hygiene,
                in_export_manager_module=self._in_export_mgr,
                in_artifact_registry_module=self._in_art_reg,
                mod_imports_hygiene=self._mod_oh,
                mod_imports_export_manager=self._mod_em,
                mod_imports_artifact_registry=self._mod_ar,
                contains_latest=has_latest,
                likely_role=role,
                recommended_action=rec,
            )
        )


def collect_hits(roots: Sequence[Path]) -> list[_WriteHit]:
    hits: list[_WriteHit] = []
    for py_path in _iter_py_files(roots):
        if "venv" in py_path.parts or "__pycache__" in py_path.parts:
            continue
        try:
            source = py_path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = _repo_relative(py_path)
        try:
            tree = ast.parse(source, filename=str(py_path))
        except SyntaxError:
            continue
        visitor = _WriteCallVisitor(rel_path=rel, source=source)
        visitor.visit(tree)
        hits.extend(visitor.hits)
    hits.sort(key=lambda h: (h.rel_path, h.line, h.write_pattern))
    return hits


def emit_csv(hits: Sequence[_WriteHit], out: Any) -> None:
    fieldnames = [
        "module",
        "function",
        "write_pattern",
        "target_expr",
        "line",
        "artifact_family_guess",
        "hygiene_call_site",
        "in_output_hygiene_module",
        "in_export_manager_module",
        "in_artifact_registry_module",
        "module_imports_output_hygiene",
        "module_imports_export_manager",
        "module_imports_artifact_registry",
        "contains_latest",
        "likely_role",
        "recommended_action",
    ]
    w = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
    w.writeheader()
    for h in hits:
        w.writerow(
            {
                "module": h.rel_path,
                "function": h.function,
                "write_pattern": h.write_pattern,
                "target_expr": h.target_expr,
                "line": h.line,
                "artifact_family_guess": h.artifact_family_guess,
                "hygiene_call_site": "Y" if h.hygiene_call_site else "N",
                "in_output_hygiene_module": "Y" if h.in_hygiene_module else "N",
                "in_export_manager_module": "Y" if h.in_export_manager_module else "N",
                "in_artifact_registry_module": "Y" if h.in_artifact_registry_module else "N",
                "module_imports_output_hygiene": "Y" if h.mod_imports_hygiene else "N",
                "module_imports_export_manager": "Y" if h.mod_imports_export_manager else "N",
                "module_imports_artifact_registry": "Y" if h.mod_imports_artifact_registry else "N",
                "contains_latest": "Y" if h.contains_latest else "N",
                "likely_role": h.likely_role,
                "recommended_action": h.recommended_action,
            }
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--roots",
        nargs="*",
        default=[str(_REPO_ROOT / "src" / "obsidiandroid")],
        help="Directories to scan (default: src/obsidiandroid).",
    )
    parser.add_argument(
        "--out",
        default="-",
        help="CSV path, or '-' for stdout (default: -).",
    )
    args = parser.parse_args(argv)
    roots = [Path(p).resolve() for p in args.roots]
    hits = collect_hits(roots)
    if args.out == "-":
        emit_csv(hits, sys.stdout)
    else:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            emit_csv(hits, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
