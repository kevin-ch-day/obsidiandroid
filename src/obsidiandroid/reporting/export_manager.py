# Filename: src/obsidiandroid/reporting/export_manager.py
# Purpose : Centralized export utilities for ObsidianDroid ML classification outputs

import re
import shutil
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Tuple
from time import perf_counter
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError as XMLParseError
from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.common import output_paths
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.common import export_naming as naming
from obsidiandroid.common import export_vendor_raw as vendor_raw
from obsidiandroid.common import export_workbook as workbook
from obsidiandroid.common.hash_utils import hash_payload, short_hash
from obsidiandroid.reporting.confusion_matrix_exporter import export_confusion_matrix_image
from obsidiandroid.reporting import confusion_matrix_layout as cm_layout
from obsidiandroid.observability.logging import get_logger, log_event

# === Output Paths ===
OUTPUT_ROOT = Path(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")).resolve()
_INITIAL_OUTPUT_ROOT = OUTPUT_ROOT


def _output_root() -> Path:
    """Resolve active output root for current runtime context."""
    runtime_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if runtime_root:
        root = Path(runtime_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    if Path(OUTPUT_ROOT).resolve() != Path(_INITIAL_OUTPUT_ROOT).resolve():
        root = Path(OUTPUT_ROOT).resolve()
    else:
        root = output_paths.output_root()
    root.mkdir(parents=True, exist_ok=True)
    return root

FILE_MALWARE_SAMPLES = "malware_samples.xlsx"
FILE_AV_RESULTS = "antivirus_results_summary.xlsx"
FILE_CLASSIFICATION = "final_classification_labels.xlsx"
FILE_VENDOR_RESULTS = "vendor_parser_results.xlsx"

ENABLE_CONSOLIDATED_WORKBOOK = bool(
    getattr(app_config, "ENABLE_CONSOLIDATED_EXCEL_WORKBOOK", False)
)
CONSOLIDATED_FILENAME = str(
    getattr(app_config, "CONSOLIDATED_EXCEL_FILENAME", "obsidiandroid_outputs.xlsx")
)
CONSOLIDATED_USE_PREFIX = bool(
    getattr(app_config, "CONSOLIDATED_EXCEL_INCLUDE_SOURCE_PREFIX", True)
)
CONSOLIDATED_REPLACE_SHEETS = bool(
    getattr(app_config, "CONSOLIDATED_EXCEL_REPLACE_SHEETS", True)
)
CONSOLIDATED_LOCK_TIMEOUT_SEC = float(
    getattr(app_config, "CONSOLIDATED_EXCEL_LOCK_TIMEOUT_SEC", 20.0)
)
SHEET_LOG_EVERY_N = max(
    1, safe_int_config_value(getattr(app_config, "EXPORT_SHEET_LOG_EVERY_N", 10), default=10)
)
EXPORT_VERBOSE_SHEET_LOGS = bool(getattr(app_config, "EXPORT_VERBOSE_SHEET_LOGS", False))
EXPORT_VENDOR_RAW_SHEETS_TO_EXCEL = bool(
    getattr(app_config, "EXPORT_VENDOR_RAW_SHEETS_TO_EXCEL", False)
)
EXPORT_VENDOR_RAW_ARTIFACTS = bool(
    getattr(app_config, "EXPORT_VENDOR_RAW_ARTIFACTS", True)
)
EXPORT_VENDOR_RAW_ARTIFACT_FORMATS = tuple(
    str(fmt).strip().lower()
    for fmt in getattr(app_config, "EXPORT_VENDOR_RAW_ARTIFACT_FORMATS", ["csv", "parquet"])
    if str(fmt).strip()
)
_PARQUET_BACKEND_WARNING_EMITTED = False
EXPORT_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.export",
    "export",
)
_CONSOLIDATED_RUNTIME_TARGET: Path | None = None

# === Utility: Clean and shorten Excel sheet names ===
def safe_sheet_name(name: str) -> str:
    return naming.safe_sheet_name(name)


def _alias_for_entry(logical_name: str, df: pd.DataFrame, occurrence: int, nonce: int = 0) -> str:
    """Build a deterministic, collision-safe alias for one sheet write."""
    return naming.alias_for_entry(
        logical_name=logical_name,
        df=df,
        occurrence=occurrence,
        hash_payload=hash_payload,
        short_hash=short_hash,
        nonce=nonce,
    )


def _resolve_unique_alias(
    logical_name: str,
    df: pd.DataFrame,
    occurrence: int,
    used_aliases: set[str],
) -> str:
    """Resolve alias collisions while preserving deterministic behavior."""
    return naming.resolve_unique_alias(
        logical_name=logical_name,
        df=df,
        occurrence=occurrence,
        used_aliases=used_aliases,
        hash_payload=hash_payload,
        short_hash=short_hash,
    )


def _safe_artifact_name(name: str) -> str:
    """Normalize arbitrary text into a filesystem-safe token."""
    return naming.safe_artifact_name(name)


def _get_runtime_fallback_workbook_path() -> Path:
    """Return deterministic per-run fallback workbook path."""
    run_id = _safe_artifact_name(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    fallback_name = f"{Path(CONSOLIDATED_FILENAME).stem}__{run_id}.xlsx"
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
    if run_id and run_id != "unknown":
        path = output_paths.runs_root() / run_id / fallback_name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    path = _output_root() / "reports" / fallback_name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _get_consolidated_target_path() -> Path:
    """Return active consolidated workbook target for this process."""
    if _CONSOLIDATED_RUNTIME_TARGET is not None:
        return _CONSOLIDATED_RUNTIME_TARGET
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
    runtime_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if run_id and run_id != "unknown":
        if runtime_root and Path(runtime_root).resolve().name == run_id:
            path = Path(runtime_root).resolve() / CONSOLIDATED_FILENAME
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        path = output_paths.runs_root() / run_id / CONSOLIDATED_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    path = _output_root() / "reports" / CONSOLIDATED_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _set_runtime_consolidated_fallback() -> Path:
    """Pin consolidated writes to fallback workbook for the remainder of the run."""
    global _CONSOLIDATED_RUNTIME_TARGET
    fallback_path = _get_runtime_fallback_workbook_path()
    _CONSOLIDATED_RUNTIME_TARGET = fallback_path
    return fallback_path


def _copy_workbook_to_latest(*, source_path: Path, filename: str) -> None:
    """Best-effort copy of workbook to output/latest for convenience workflows."""
    if not bool(getattr(app_config, "ENABLE_LATEST_WORKBOOK_COPY", True)):
        return
    if not source_path.exists():
        return
    latest_dir = output_paths.latest_root()
    latest_dir.mkdir(parents=True, exist_ok=True)
    target_path = latest_dir / str(filename)
    try:
        shutil.copy2(source_path, target_path)
    except Exception as exc:
        du.print_warning(f"[EXPORT] latest workbook copy skipped (non-fatal): {exc}")


def _iter_valid_frames(dataframes: dict) -> list[tuple[str, pd.DataFrame]]:
    """Return non-empty DataFrame entries from a mapping."""
    valid: list[tuple[str, pd.DataFrame]] = []
    for sheet, df in dataframes.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            valid.append((str(sheet), df))
    return valid


def _should_emit_sheet_log(position: int, total: int, every_n: int = SHEET_LOG_EVERY_N) -> bool:
    """Throttle per-sheet logs to reduce console overhead."""
    if not EXPORT_VERBOSE_SHEET_LOGS:
        return False
    if total <= 5:
        return True
    if position <= 2 or position == total:
        return True
    return position % max(1, every_n) == 0


def _build_manifest_rows(rows: list[tuple[str, str, pd.DataFrame]]) -> pd.DataFrame:
    """Build manifest rows for a batch of workbook writes."""
    return workbook.build_manifest_rows(
        rows=rows,
        run_id=str(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
        hash_payload=hash_payload,
    )


def _assert_workbook_integrity(path: Path) -> None:
    """Validate workbook ZIP structure to catch broken writes early."""
    workbook.assert_workbook_integrity(path)


def _write_consolidated_batch(path: Path, sheets: list[tuple[str, pd.DataFrame]]) -> list[tuple[str, str, int]]:
    """Write many sheets into consolidated workbook in one ExcelWriter session."""
    return workbook.write_consolidated_batch(
        path=path,
        sheets=sheets,
        consolidated_replace_sheets=CONSOLIDATED_REPLACE_SHEETS,
        lock_timeout_sec=CONSOLIDATED_LOCK_TIMEOUT_SEC,
        run_id=str(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
        hash_payload=hash_payload,
        short_hash=short_hash,
    )


def _record_manifest_row(path: Path, alias: str, logical_name: str, df: pd.DataFrame) -> None:
    """Upsert workbook manifest row for a sheet alias."""
    workbook.record_manifest_row(
        path=path,
        alias=alias,
        logical_name=logical_name,
        df=df,
        run_id=str(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
        hash_payload=hash_payload,
    )

# === Utility: Create Excel writer ===
def create_excel_writer(filename: str) -> Tuple[pd.ExcelWriter, Path]:
    path = _output_root() / filename
    writer = pd.ExcelWriter(path, engine="openpyxl", mode="w")
    return writer, path


def _sheet_name_with_context(filename: str, sheet_name: str) -> str:
    """Create a stable sheet name with optional source-file prefix."""
    return naming.sheet_name_with_context(
        filename=filename,
        sheet_name=sheet_name,
        enable_consolidated_workbook=ENABLE_CONSOLIDATED_WORKBOOK,
        consolidated_use_prefix=CONSOLIDATED_USE_PREFIX,
    )


def _write_sheet(path: Path, sheet_name: str, df: pd.DataFrame) -> str:
    """Write/append one sheet and return deterministic alias used in workbook."""
    return workbook.write_sheet(
        path=path,
        sheet_name=sheet_name,
        df=df,
        consolidated_replace_sheets=CONSOLIDATED_REPLACE_SHEETS,
        lock_timeout_sec=CONSOLIDATED_LOCK_TIMEOUT_SEC,
        run_id=str(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
        hash_payload=hash_payload,
        short_hash=short_hash,
    )


def _export_to_consolidated(
    df: pd.DataFrame,
    filename: str,
    sheet_name: str,
) -> tuple[Path, str, str]:
    """Append a DataFrame into the consolidated workbook as one contextual sheet."""
    consolidated_path = _get_consolidated_target_path()
    contextual_sheet = _sheet_name_with_context(filename, sheet_name)
    alias = _write_sheet(consolidated_path, contextual_sheet, df)
    return consolidated_path, contextual_sheet, alias


def _is_workbook_corruption_error(exc: Exception) -> bool:
    """Return True when an exception likely indicates a corrupted xlsx container."""
    if isinstance(exc, (BadZipFile, XMLParseError)):
        return True
    msg = str(exc).lower()
    return (
        "bad crc-32" in msg
        or "not well-formed" in msg
        or "zip" in msg and "file" in msg and "corrupt" in msg
    )


def _quarantine_corrupted_workbook(path: Path) -> Path | None:
    """Move a corrupted workbook aside and return its new path."""
    return workbook.quarantine_corrupted_workbook(path)

# === Generic DataFrame Export (Single Sheet) ===
def export_dataframe_to_excel(
    df: pd.DataFrame,
    filename: str,
    sheet_name: str = "Sheet1",
    preview_rows: int = 5
):
    if df is None or df.empty:
        du.print_warning(f"[EXPORT] No data to export for: {filename}")
        log_event(EXPORT_LOGGER, "export_skipped", filename=filename, reason="empty_dataframe")
        return

    writer = None
    started = perf_counter()
    path = _output_root() / filename
    exported_path = None
    try:
        if not ENABLE_CONSOLIDATED_WORKBOOK:
            writer, path = create_excel_writer(filename)
            df.to_excel(writer, sheet_name=safe_sheet_name(sheet_name), index=False)
            writer.close()
            exported_path = path

        if ENABLE_CONSOLIDATED_WORKBOOK:
            consolidated_path, logical_sheet, alias = _export_to_consolidated(df, filename, sheet_name)
            exported_path = consolidated_path if exported_path is None else exported_path
            du.print_info(
                f"[EXPORT] Added sheet alias='{alias}' logical='{logical_sheet}' "
                f"to {consolidated_path}"
            )
            log_event(
                EXPORT_LOGGER,
                "export_sheet_added",
                filename=filename,
                alias=alias,
                logical_sheet=logical_sheet,
                rows=int(df.shape[0]),
                columns=int(df.shape[1]),
            )

        if exported_path is None:
            exported_path = path
        if ENABLE_CONSOLIDATED_WORKBOOK and str(filename) == str(CONSOLIDATED_FILENAME):
            _copy_workbook_to_latest(source_path=Path(exported_path), filename=CONSOLIDATED_FILENAME)
        du.print_success(f"Exported: {exported_path}")
        log_event(
            EXPORT_LOGGER,
            "export_success",
            filename=filename,
            exported_path=str(exported_path),
            rows=int(df.shape[0]),
            columns=int(df.shape[1]),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        if preview_rows and preview_rows > 0:
            du.print_table(df.head(preview_rows), title=f"Preview: {sheet_name}", show_index=False)
        return exported_path
    except (PermissionError, TimeoutError):
        consolidated_path = _output_root() / CONSOLIDATED_FILENAME
        if ENABLE_CONSOLIDATED_WORKBOOK:
            try:
                run_id = _safe_artifact_name(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
                fallback_name = f"{Path(CONSOLIDATED_FILENAME).stem}__{run_id}.xlsx"
                fallback_path = _output_root() / fallback_name
                logical_sheet = _sheet_name_with_context(filename, sheet_name)
                alias = _write_sheet(fallback_path, logical_sheet, df)
                du.print_warning(
                    f"[EXPORT] Consolidated workbook is locked: {consolidated_path}. "
                    f"Exported '{filename}' to fallback workbook: {fallback_path.name} "
                    f"(alias='{alias}')."
                )
                log_event(
                    EXPORT_LOGGER,
                    "export_locked_fallback_success",
                    filename=filename,
                    consolidated_path=str(consolidated_path),
                    fallback_path=str(fallback_path),
                    alias=alias,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                return fallback_path
            except Exception as fallback_exc:
                du.print_warning(
                    f"[EXPORT] Consolidated workbook is locked and fallback failed for '{filename}': {fallback_exc}"
                )
                log_event(
                    EXPORT_LOGGER,
                    "export_locked_skipped",
                    filename=filename,
                    consolidated_path=str(consolidated_path),
                    error=str(fallback_exc),
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                return ""
        try:
            fallback = naming.timestamped_filename(filename)
            fallback_path = _output_root() / fallback
            logical_sheet = safe_sheet_name(sheet_name)
            alias = _write_sheet(fallback_path, logical_sheet, df)
            du.print_warning(
                f"[EXPORT] File locked: {filename}. Exported to fallback file: "
                f"{fallback_path.name} (alias='{alias}', logical='{logical_sheet}')."
            )
            log_event(
                EXPORT_LOGGER,
                "export_fallback_success",
                filename=filename,
                fallback_path=str(fallback_path),
                alias=alias,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            if preview_rows and preview_rows > 0:
                du.print_table(df.head(preview_rows), title=f"Preview: {sheet_name}", show_index=False)
            return fallback_path
        except Exception as e:
            du.print_error(f"[EXPORT FAILED] {filename}: {e}")
            EXPORT_LOGGER.error("export_failed filename=%r error=%r", filename, e, exc_info=True)
            return ""
    except Exception as e:
        if ENABLE_CONSOLIDATED_WORKBOOK:
            consolidated_path = _output_root() / CONSOLIDATED_FILENAME
            if _is_workbook_corruption_error(e):
                quarantined = _quarantine_corrupted_workbook(consolidated_path)
                if quarantined is not None:
                    du.print_warning(
                        f"[EXPORT] Corrupted workbook detected. Moved to: {quarantined.name}. "
                        "A fresh consolidated workbook will be created."
                    )
                    log_event(
                        EXPORT_LOGGER,
                        "export_workbook_quarantined",
                        filename=filename,
                        corrupted_path=str(consolidated_path),
                        quarantine_path=str(quarantined),
                        duration_ms=round((perf_counter() - started) * 1000, 2),
                    )
                    try:
                        consolidated_path, logical_sheet, alias = _export_to_consolidated(df, filename, sheet_name)
                        du.print_info(
                            f"[EXPORT] Recovered sheet alias='{alias}' logical='{logical_sheet}' "
                            f"to {consolidated_path}"
                        )
                        log_event(
                            EXPORT_LOGGER,
                            "export_recovered_after_quarantine",
                            filename=filename,
                            alias=alias,
                            logical_sheet=logical_sheet,
                            exported_path=str(consolidated_path),
                            duration_ms=round((perf_counter() - started) * 1000, 2),
                        )
                        return consolidated_path
                    except Exception as inner_exc:
                        du.print_error(f"[EXPORT FAILED] {filename}: {inner_exc}")
                        EXPORT_LOGGER.error(
                            "export_recovery_failed filename=%r error=%r",
                            filename,
                            inner_exc,
                            exc_info=True,
                        )
                        return ""
                else:
                    try:
                        run_id = _safe_artifact_name(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
                        fallback_name = f"{Path(CONSOLIDATED_FILENAME).stem}__{run_id}.xlsx"
                        fallback_path = _output_root() / fallback_name
                        logical_sheet = _sheet_name_with_context(filename, sheet_name)
                        alias = _write_sheet(fallback_path, logical_sheet, df)
                        du.print_warning(
                            "[EXPORT] Corrupted consolidated workbook is locked; "
                            f"exported '{filename}' to fallback workbook: {fallback_path.name} "
                            f"(alias='{alias}')."
                        )
                        log_event(
                            EXPORT_LOGGER,
                            "export_corruption_fallback_success",
                            filename=filename,
                            corrupted_path=str(consolidated_path),
                            fallback_path=str(fallback_path),
                            alias=alias,
                            duration_ms=round((perf_counter() - started) * 1000, 2),
                        )
                        return fallback_path
                    except Exception as inner_fallback_exc:
                        du.print_error(f"[EXPORT FAILED] {filename}: {inner_fallback_exc}")
                        EXPORT_LOGGER.error(
                            "export_corruption_fallback_failed filename=%r error=%r",
                            filename,
                            inner_fallback_exc,
                            exc_info=True,
                        )
                        return ""
        du.print_error(f"[EXPORT FAILED] {filename}: {e}")
        EXPORT_LOGGER.error("export_failed filename=%r error=%r", filename, e, exc_info=True)
        return ""
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass

# === Multi-Sheet Export for Dict of DataFrames ===
def write_excel_file(dataframes: dict, filename: str):
    writer = None
    started = perf_counter()
    path = _output_root() / filename
    valid_frames = _iter_valid_frames(dataframes)
    total_sheets = len(valid_frames)
    if total_sheets == 0:
        du.print_warning(f"[EXPORT] No non-empty DataFrames to export for: {filename}")
        log_event(EXPORT_LOGGER, "export_skipped", filename=filename, reason="no_valid_sheets")
        return ""
    try:
        if not ENABLE_CONSOLIDATED_WORKBOOK:
            writer, path = create_excel_writer(filename)
            for index, (sheet, df) in enumerate(valid_frames, start=1):
                df.to_excel(writer, sheet_name=safe_sheet_name(sheet), index=False)
                if _should_emit_sheet_log(index, total_sheets):
                    du.print_info(f"[SHEET] {index}/{total_sheets} '{sheet}' ({df.shape[0]} rows)")
            writer.close()
            du.print_success(f"Excel file saved: {path}")
            log_event(
                EXPORT_LOGGER,
                "export_workbook_saved",
                filename=filename,
                path=str(path),
                sheet_count=total_sheets,
            )

        consolidated_path = _output_root() / CONSOLIDATED_FILENAME
        if ENABLE_CONSOLIDATED_WORKBOOK:
            contextual_frames = [
                (_sheet_name_with_context(filename, sheet), df)
                for sheet, df in valid_frames
            ]
            written_rows = _write_consolidated_batch(consolidated_path, contextual_frames)
            for index, (alias, logical, rows) in enumerate(written_rows, start=1):
                if _should_emit_sheet_log(index, total_sheets):
                    du.print_info(
                        f"[SHEET] {index}/{total_sheets} alias='{alias}' logical='{logical}' "
                        f"({rows} rows)"
                    )
            if total_sheets > 5:
                du.print_info(
                    f"[SHEET] Exported {total_sheets} sheet(s) to consolidated workbook "
                    f"(log interval={SHEET_LOG_EVERY_N})."
                )
            du.print_success(f"Consolidated workbook updated: {consolidated_path}")
            if str(filename) == str(CONSOLIDATED_FILENAME):
                _copy_workbook_to_latest(
                    source_path=Path(consolidated_path),
                    filename=CONSOLIDATED_FILENAME,
                )
            log_event(
                EXPORT_LOGGER,
                "export_consolidated_saved",
                filename=filename,
                path=str(consolidated_path),
                sheet_count=total_sheets,
                writer_sessions=1,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            return consolidated_path

        return path
    except (PermissionError, TimeoutError):
        consolidated_path = _output_root() / CONSOLIDATED_FILENAME
        if ENABLE_CONSOLIDATED_WORKBOOK:
            try:
                run_id = _safe_artifact_name(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
                fallback_name = f"{Path(CONSOLIDATED_FILENAME).stem}__{run_id}.xlsx"
                fallback_path = _output_root() / fallback_name
                contextual_frames = [
                    (_sheet_name_with_context(filename, sheet), df)
                    for sheet, df in valid_frames
                ]
                _write_consolidated_batch(fallback_path, contextual_frames)
                du.print_warning(
                    f"[EXPORT] Consolidated workbook is locked: {consolidated_path}. "
                    f"Exported '{filename}' to fallback workbook: {fallback_path.name}"
                )
                log_event(
                    EXPORT_LOGGER,
                    "export_workbook_locked_fallback_success",
                    filename=filename,
                    consolidated_path=str(consolidated_path),
                    fallback_path=str(fallback_path),
                    sheet_count=total_sheets,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                return fallback_path
            except Exception as fallback_exc:
                du.print_warning(
                    f"[EXPORT] Consolidated workbook is locked and fallback failed for '{filename}': {fallback_exc}"
                )
                log_event(
                    EXPORT_LOGGER,
                    "export_workbook_locked_skipped",
                    filename=filename,
                    consolidated_path=str(consolidated_path),
                    error=str(fallback_exc),
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                return ""
        try:
            fallback = naming.timestamped_filename(filename)
            writer, path = create_excel_writer(fallback)
            for sheet, df in valid_frames:
                df.to_excel(writer, sheet_name=safe_sheet_name(sheet), index=False)
            writer.close()
            du.print_warning(
                f"[EXPORT] File locked: {filename}. Exported to fallback file: {path.name}"
            )
            log_event(
                EXPORT_LOGGER,
                "export_workbook_fallback_success",
                filename=filename,
                fallback_path=str(path),
                sheet_count=total_sheets,
            )
            return path
        except Exception as e:
            du.print_error(f"[EXPORT] Failed to write Excel file '{filename}': {e}")
            EXPORT_LOGGER.error("export_workbook_failed filename=%r error=%r", filename, e, exc_info=True)
            return ""
    except Exception as e:
        consolidated_path = _output_root() / CONSOLIDATED_FILENAME
        if ENABLE_CONSOLIDATED_WORKBOOK and _is_workbook_corruption_error(e):
            quarantined = _quarantine_corrupted_workbook(consolidated_path)
            if quarantined is not None:
                du.print_warning(
                    f"[EXPORT] Corrupted workbook detected. Moved to: {quarantined.name}. "
                    "Retrying export into a new consolidated workbook."
                )
                log_event(
                    EXPORT_LOGGER,
                    "export_workbook_quarantined",
                    filename=filename,
                    corrupted_path=str(consolidated_path),
                    quarantine_path=str(quarantined),
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                try:
                    contextual_frames = [
                        (_sheet_name_with_context(filename, sheet), df)
                        for sheet, df in valid_frames
                    ]
                    written_rows = _write_consolidated_batch(consolidated_path, contextual_frames)
                    for index, (alias, logical, rows) in enumerate(written_rows, start=1):
                        if _should_emit_sheet_log(index, total_sheets):
                            du.print_info(
                                f"[SHEET] {index}/{total_sheets} alias='{alias}' logical='{logical}' "
                                f"({rows} rows)"
                            )
                    du.print_success(f"Consolidated workbook updated: {consolidated_path}")
                    log_event(
                        EXPORT_LOGGER,
                        "export_recovered_after_quarantine",
                        filename=filename,
                        exported_path=str(consolidated_path),
                        sheet_count=total_sheets,
                        duration_ms=round((perf_counter() - started) * 1000, 2),
                    )
                    return consolidated_path
                except Exception as inner_exc:
                    du.print_error(f"[EXPORT] Failed to write Excel file '{filename}': {inner_exc}")
                    EXPORT_LOGGER.error(
                        "export_workbook_recovery_failed filename=%r error=%r",
                        filename,
                        inner_exc,
                        exc_info=True,
                    )
                    return ""
            else:
                try:
                    run_id = _safe_artifact_name(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
                    fallback_name = f"{Path(CONSOLIDATED_FILENAME).stem}__{run_id}.xlsx"
                    fallback_path = _output_root() / fallback_name
                    contextual_frames = [
                        (_sheet_name_with_context(filename, sheet), df)
                        for sheet, df in valid_frames
                    ]
                    _write_consolidated_batch(fallback_path, contextual_frames)
                    du.print_warning(
                        "[EXPORT] Corrupted consolidated workbook is locked; "
                        f"exported '{filename}' to fallback workbook: {fallback_path.name}"
                    )
                    log_event(
                        EXPORT_LOGGER,
                        "export_workbook_corruption_fallback_success",
                        filename=filename,
                        corrupted_path=str(consolidated_path),
                        fallback_path=str(fallback_path),
                        sheet_count=total_sheets,
                        duration_ms=round((perf_counter() - started) * 1000, 2),
                    )
                    return fallback_path
                except Exception as inner_fallback_exc:
                    du.print_error(f"[EXPORT] Failed to write Excel file '{filename}': {inner_fallback_exc}")
                    EXPORT_LOGGER.error(
                        "export_workbook_corruption_fallback_failed filename=%r error=%r",
                        filename,
                        inner_fallback_exc,
                        exc_info=True,
                    )
                    return ""
        du.print_error(f"[EXPORT] Failed to write Excel file '{filename}': {e}")
        EXPORT_LOGGER.error("export_workbook_failed filename=%r error=%r", filename, e, exc_info=True)
        return ""
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass

# === Confusion Matrix Export Wrapper ===
def export_confusion_matrix(
    cm: np.ndarray,
    class_labels: List[str],
    model_name: str,
    mode: str = "color",
) -> str:
    """Export confusion matrix using run-scoped, reviewable folder layout."""
    def _cm_token(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
        return cleaned.strip("_") or "unknown"

    run_id = _cm_token(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    experiment_raw = str(getattr(app_config, "RUNTIME_EXPERIMENT_ID", "") or "")
    experiment = _cm_token(experiment_raw) if experiment_raw.strip() else ""
    model_token = _cm_token(model_name)

    if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)) and not cm_layout.should_export_confusion_matrix(
        experiment_id=experiment_raw
    ):
        if not bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False)) and ml_console.is_debug():
            du.print_debug(
                f"[EXPORT] Skipping confusion matrix (export_mode={cm_layout.export_mode()}): "
                f"{experiment_raw!r} / {model_token}"
            )
        return ""

    run_scoped_root = _output_root()
    if run_id and run_id != "unknown":
        if Path(OUTPUT_ROOT).resolve() != Path(_INITIAL_OUTPUT_ROOT).resolve():
            base_root = Path(OUTPUT_ROOT).resolve()
        else:
            base_root = output_paths.output_root()
        runtime_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
        if runtime_root:
            runtime_root_path = Path(runtime_root).resolve()
            if runtime_root_path.name == run_id:
                run_scoped_root = runtime_root_path
            else:
                run_scoped_root = base_root / "runs" / run_id
        else:
            run_scoped_root = base_root / "runs" / run_id

    cm_dir = run_scoped_root / "conf_matrices"
    output_path = cm_layout.resolve_confusion_matrix_png_path(
        conf_matrices_dir=cm_dir,
        model_name=model_name,
        experiment_id=experiment_raw,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    exported_path = export_confusion_matrix_image(
        cm=cm,
        class_labels=class_labels,
        model_name=model_name,
        output_path=output_path,
        color_mode=mode,
        title=f"Confusion Matrix - {model_name.upper()}",
        dpi=300,
        verbose=bool(not quiet and not ml_console.is_minimal()),
    )
    headline_ctx = not bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False))
    flat_cm = cm_dir
    canon_rf = flat_cm / "confusion_matrix_random_forest.png"
    headline_rf = cm_dir / "headline" / "random_forest.png"
    if headline_ctx and model_token == "random_forest":
        try:
            src_path = Path(str(exported_path)).resolve()
            for dst in (headline_rf, canon_rf):
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.resolve() != src_path:
                    shutil.copyfile(src_path, dst)
            exported_path = str(canon_rf.resolve())
        except Exception:
            pass
    elif not headline_ctx and model_token == "random_forest" and experiment_raw:
        try:
            src_path = Path(str(exported_path)).resolve()
            if canon_rf.resolve() != src_path and src_path.is_file():
                shutil.copyfile(src_path, canon_rf)
        except Exception:
            pass
    return exported_path

# === Specialized Export Functions ===

def export_sample_metadata(df: pd.DataFrame):
    export_dataframe_to_excel(df, FILE_MALWARE_SAMPLES, sheet_name="Malware Samples")

def export_av_analysis(av_summary: pd.DataFrame, matrix: pd.DataFrame, scores: pd.DataFrame):
    return write_excel_file({
        "AV Summary Results": av_summary,
        "AV Detection Matrix": matrix,
        "AV Engine Performance": scores
    }, FILE_AV_RESULTS)

def export_classification_labels(df: pd.DataFrame):
    export_dataframe_to_excel(df, FILE_CLASSIFICATION, sheet_name="Classification_Labels")

def save_structured_classification_report(
    df: pd.DataFrame,
    filename: str = FILE_CLASSIFICATION,
    sheet_name: str = "Classification_Labels",
    preview_rows: int = 5
):
    return export_dataframe_to_excel(df, filename, sheet_name, preview_rows)


def _export_vendor_raw_artifacts(parsed_data: dict) -> dict[str, int]:
    """Persist raw vendor parser outputs to lightweight artifacts."""
    export_formats = list(EXPORT_VENDOR_RAW_ARTIFACT_FORMATS)
    global _PARQUET_BACKEND_WARNING_EMITTED
    if "parquet" in export_formats and not _is_parquet_supported():
        export_formats = [fmt for fmt in export_formats if fmt != "parquet"]
        if not _PARQUET_BACKEND_WARNING_EMITTED:
            du.print_warning(
                "[EXPORT] Parquet backend unavailable (install 'pyarrow' or 'fastparquet'). "
                "Continuing with CSV vendor raw artifacts."
            )
            _PARQUET_BACKEND_WARNING_EMITTED = True
    return vendor_raw.export_vendor_raw_artifacts(
        parsed_data=parsed_data,
        export_enabled=EXPORT_VENDOR_RAW_ARTIFACTS,
        export_formats=tuple(export_formats),
        output_root=_output_root(),
        run_id=_safe_artifact_name(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
        safe_artifact_name=_safe_artifact_name,
        log_event=log_event,
        logger=EXPORT_LOGGER,
    )


def _is_parquet_supported() -> bool:
    """Return True when a parquet engine is installed."""
    return vendor_raw.is_parquet_supported()


def export_vendor_results(parsed_data: dict, summary_df: pd.DataFrame):
    if not parsed_data or summary_df is None:
        du.print_warning("Vendor parser results or summary is missing.")
        return ""
    combined = {"Vendor_Summary": summary_df}
    non_empty_raw = {
        vendor: df for vendor, df in parsed_data.items() if isinstance(df, pd.DataFrame) and not df.empty
    }
    if EXPORT_VENDOR_RAW_SHEETS_TO_EXCEL:
        combined.update(non_empty_raw)

    exported_path = write_excel_file(combined, FILE_VENDOR_RESULTS)
    raw_metrics = _export_vendor_raw_artifacts(non_empty_raw)
    if raw_metrics["vendors"] > 0:
        du.print_info(
            "[EXPORT] Vendor raw artifacts saved: "
            f"vendors={raw_metrics['vendors']}, csv={raw_metrics['csv']}, "
            f"parquet={raw_metrics['parquet']}, errors={raw_metrics['errors']}"
        )
        log_event(
            EXPORT_LOGGER,
            "export_vendor_raw_complete",
            vendors=raw_metrics["vendors"],
            csv_count=raw_metrics["csv"],
            parquet_count=raw_metrics["parquet"],
            error_count=raw_metrics["errors"],
            output_dir=str(_output_root() / "vendor_raw"),
            run_id=getattr(app_config, "RUNTIME_RUN_ID", "unknown"),
        )
    return exported_path


__all__ = [
    "safe_sheet_name",
    "create_excel_writer",
    "export_dataframe_to_excel",
    "write_excel_file",
    "export_confusion_matrix",
    "export_sample_metadata",
    "export_av_analysis",
    "export_classification_labels",
    "save_structured_classification_report",
    "export_vendor_results",
]
