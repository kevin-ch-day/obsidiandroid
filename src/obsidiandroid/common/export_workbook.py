"""Workbook I/O helpers used by export manager."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from zipfile import BadZipFile, ZipFile

import pandas as pd

from obsidiandroid.common.export_naming import resolve_unique_alias, safe_sheet_name


HashPayload = Callable[[dict], str]
ShortHash = Callable[[str, int], str]


class WorkbookLock:
    """Cross-process lock for workbook writes."""

    def __init__(self, workbook_path: Path, timeout_sec: float):
        """Initialize lock parameters.

        Args:
            workbook_path: Workbook file path being protected.
            timeout_sec: Maximum lock wait time in seconds.
        """
        self.workbook_path = workbook_path
        self.timeout_sec = max(0.1, float(timeout_sec))
        self.lock_path = workbook_path.with_suffix(f"{workbook_path.suffix}.lock")
        self.fd: int | None = None

    def __enter__(self) -> "WorkbookLock":
        deadline = time.monotonic() + self.timeout_sec
        while True:
            try:
                self.fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self.fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for workbook lock: {self.lock_path}")
                time.sleep(0.2)

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        try:
            if self.fd is not None:
                os.close(self.fd)
        finally:
            self.fd = None
            try:
                self.lock_path.unlink(missing_ok=True)
            except Exception:  # pragma: no cover - best effort cleanup
                pass


def build_manifest_rows(
    rows: list[tuple[str, str, pd.DataFrame]],
    run_id: str,
    hash_payload: HashPayload,
) -> pd.DataFrame:
    """Build manifest rows for a batch of workbook writes.

    Args:
        rows: Tuples of alias, logical name, and DataFrame.
        run_id: Current runtime identifier.
        hash_payload: Hash function used for schema/data hashing.

    Returns:
        DataFrame ready to write as ``__manifest__``.
    """
    records = []
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for alias, logical_name, df in rows:
        records.append(
            {
                "sheet_alias": alias,
                "logical_name": logical_name,
                "stage": logical_name.split("__")[0] if "__" in logical_name else logical_name,
                "row_count": int(df.shape[0]),
                "column_count": int(df.shape[1]),
                "schema_hash": hash_payload({"columns": list(df.columns)}),
                "data_hash": hash_payload({"head": df.head(100).to_dict(orient="records")}),
                "run_id": run_id,
                "timestamp": ts,
            }
        )
    return pd.DataFrame(records)


def assert_workbook_integrity(path: Path) -> None:
    """Validate workbook ZIP structure to catch broken writes early.

    Args:
        path: Workbook path.

    Raises:
        BadZipFile: When ZIP CRC validation fails.
    """
    if not path.exists():
        return
    with ZipFile(path, "r") as archive:
        bad_member = archive.testzip()
    if bad_member is not None:
        raise BadZipFile(f"Workbook CRC check failed for member '{bad_member}'")


def write_consolidated_batch(
    path: Path,
    sheets: list[tuple[str, pd.DataFrame]],
    consolidated_replace_sheets: bool,
    lock_timeout_sec: float,
    run_id: str,
    hash_payload: HashPayload,
    short_hash: ShortHash,
) -> list[tuple[str, str, int]]:
    """Write many sheets into a consolidated workbook in one session.

    Args:
        path: Consolidated workbook path.
        sheets: Logical sheet name and DataFrame tuples.
        consolidated_replace_sheets: Whether existing sheets are replaced.
        lock_timeout_sec: Lock wait timeout in seconds.
        run_id: Current runtime identifier.
        hash_payload: Hash function used for manifest and aliasing.
        short_hash: Hash shortener function used for aliasing.

    Returns:
        Tuples of alias, logical sheet name, and row count.
    """
    if not sheets:
        return []

    manifest_alias = "__manifest__"
    existing_manifest = pd.DataFrame()
    with WorkbookLock(path, timeout_sec=lock_timeout_sec):
        mode = "a" if path.exists() else "w"
        if mode == "a":
            try:
                existing_manifest = pd.read_excel(path, sheet_name=manifest_alias)
            except Exception:
                existing_manifest = pd.DataFrame()

        used_aliases = set()
        prior_counts: dict[str, int] = {}
        if not existing_manifest.empty:
            if "sheet_alias" in existing_manifest.columns:
                used_aliases = {
                    str(alias).strip()
                    for alias in existing_manifest["sheet_alias"].tolist()
                    if str(alias).strip()
                }
            if "logical_name" in existing_manifest.columns:
                logical_counts = existing_manifest["logical_name"].astype(str).value_counts()
                prior_counts = {name: int(count) for name, count in logical_counts.items()}

        writer_kwargs = {"engine": "openpyxl", "mode": mode}
        if mode == "a":
            writer_kwargs["if_sheet_exists"] = "replace" if consolidated_replace_sheets else "new"

        written: list[tuple[str, str, int]] = []
        manifest_source: list[tuple[str, str, pd.DataFrame]] = []
        with pd.ExcelWriter(path, **writer_kwargs) as writer:
            for logical_name, df in sheets:
                occurrence = prior_counts.get(logical_name, 0) + 1
                prior_counts[logical_name] = occurrence
                alias = resolve_unique_alias(
                    logical_name=logical_name,
                    df=df,
                    occurrence=occurrence,
                    used_aliases=used_aliases,
                    hash_payload=hash_payload,
                    short_hash=short_hash,
                )
                df.to_excel(writer, sheet_name=safe_sheet_name(alias), index=False)
                written.append((alias, logical_name, int(df.shape[0])))
                manifest_source.append((alias, logical_name, df))

            manifest_updates = build_manifest_rows(
                rows=manifest_source,
                run_id=run_id,
                hash_payload=hash_payload,
            )
            merged = pd.concat([existing_manifest, manifest_updates], ignore_index=True)
            merged = merged.drop_duplicates(subset=["sheet_alias"], keep="last")
            merged.to_excel(writer, sheet_name=manifest_alias, index=False)

    assert_workbook_integrity(path)
    return written


def record_manifest_row(
    path: Path,
    alias: str,
    logical_name: str,
    df: pd.DataFrame,
    run_id: str,
    hash_payload: HashPayload,
) -> None:
    """Upsert workbook manifest row for a sheet alias.

    Args:
        path: Workbook path.
        alias: Actual alias used in workbook.
        logical_name: Logical name for source sheet.
        df: DataFrame payload.
        run_id: Runtime identifier.
        hash_payload: Hash function used for schema/data hashing.
    """
    manifest_alias = "__manifest__"
    if manifest_alias == alias:
        return

    row = {
        "sheet_alias": alias,
        "logical_name": logical_name,
        "stage": logical_name.split("__")[0] if "__" in logical_name else logical_name,
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "schema_hash": hash_payload({"columns": list(df.columns)}),
        "data_hash": hash_payload({"head": df.head(100).to_dict(orient="records")}),
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    mode = "a" if path.exists() else "w"
    writer_kwargs = {"engine": "openpyxl", "mode": mode}
    if mode == "a":
        writer_kwargs["if_sheet_exists"] = "replace"

    existing = pd.DataFrame()
    if mode == "a":
        try:
            existing = pd.read_excel(path, sheet_name=manifest_alias)
        except Exception:
            existing = pd.DataFrame()

    merged = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    merged = merged.drop_duplicates(subset=["sheet_alias"], keep="last")

    with pd.ExcelWriter(path, **writer_kwargs) as writer:
        merged.to_excel(writer, sheet_name=manifest_alias, index=False)


def write_sheet(
    path: Path,
    sheet_name: str,
    df: pd.DataFrame,
    consolidated_replace_sheets: bool,
    lock_timeout_sec: float,
    run_id: str,
    hash_payload: HashPayload,
    short_hash: ShortHash,
) -> str:
    """Write one sheet and return its deterministic alias.

    Args:
        path: Workbook path.
        sheet_name: Logical sheet name.
        df: DataFrame payload.
        consolidated_replace_sheets: Whether existing sheets are replaced.
        lock_timeout_sec: Lock wait timeout in seconds.
        run_id: Runtime identifier.
        hash_payload: Hash function used for manifest and aliasing.
        short_hash: Hash shortener function used for aliasing.

    Returns:
        Alias used for sheet write.
    """
    with WorkbookLock(path, timeout_sec=lock_timeout_sec):
        manifest_alias = "__manifest__"
        mode = "a" if path.exists() else "w"
        writer_kwargs = {"engine": "openpyxl", "mode": mode}
        if mode == "a":
            writer_kwargs["if_sheet_exists"] = "replace" if consolidated_replace_sheets else "new"

        existing_manifest = pd.DataFrame()
        if mode == "a":
            try:
                existing_manifest = pd.read_excel(path, sheet_name=manifest_alias)
            except Exception:
                existing_manifest = pd.DataFrame()

        used_aliases = set()
        prior_count = 0
        if not existing_manifest.empty:
            if "sheet_alias" in existing_manifest.columns:
                used_aliases = {
                    str(alias).strip()
                    for alias in existing_manifest["sheet_alias"].tolist()
                    if str(alias).strip()
                }
            if "logical_name" in existing_manifest.columns:
                prior_count = int((existing_manifest["logical_name"].astype(str) == str(sheet_name)).sum())

        alias = resolve_unique_alias(
            logical_name=sheet_name,
            df=df,
            occurrence=prior_count + 1,
            used_aliases=used_aliases,
            hash_payload=hash_payload,
            short_hash=short_hash,
        )
        with pd.ExcelWriter(path, **writer_kwargs) as writer:
            df.to_excel(writer, sheet_name=safe_sheet_name(alias), index=False)

    record_manifest_row(
        path=path,
        alias=alias,
        logical_name=sheet_name,
        df=df,
        run_id=run_id,
        hash_payload=hash_payload,
    )
    assert_workbook_integrity(path)
    return alias


def quarantine_corrupted_workbook(path: Path) -> Path | None:
    """Move a corrupted workbook aside and return the new path.

    Args:
        path: Workbook path.

    Returns:
        New quarantine path when rename succeeds, otherwise ``None``.
    """
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine = path.with_name(f"{path.stem}.corrupt_{ts}{path.suffix}")
    try:
        path.rename(quarantine)
        return quarantine
    except OSError:
        return None


__all__ = [
    "HashPayload",
    "ShortHash",
    "WorkbookLock",
    "assert_workbook_integrity",
    "build_manifest_rows",
    "quarantine_corrupted_workbook",
    "record_manifest_row",
    "write_consolidated_batch",
    "write_sheet",
]
