"""Naming utilities for export workbook sheets and artifacts."""

from datetime import datetime
from pathlib import Path
import re
from typing import Callable

import pandas as pd


HashPayload = Callable[[dict], str]
ShortHash = Callable[[str, int], str]


def safe_sheet_name(name: str) -> str:
    """Sanitize text for Excel sheet names.

    Args:
        name: Candidate sheet name.

    Returns:
        Sanitized sheet name capped to Excel's 31-character limit.
    """
    return str(name).strip().replace("/", "_").replace("\\", "_")[:31]


def alias_for_entry(
    logical_name: str,
    df: pd.DataFrame,
    occurrence: int,
    hash_payload: HashPayload,
    short_hash: ShortHash,
    nonce: int = 0,
) -> str:
    """Build a deterministic alias for one sheet entry.

    Args:
        logical_name: Logical sheet identifier.
        df: DataFrame payload.
        occurrence: Sequential occurrence count for this logical sheet.
        hash_payload: Hash function used for stable payload hashing.
        short_hash: Hash shortener function.
        nonce: Extra counter used only when collision resolution is needed.

    Returns:
        Collision-resistant sheet alias.
    """
    clean = str(logical_name).strip().replace("/", "_").replace("\\", "_")
    base = "".join(ch for ch in clean.lower() if ch.isalnum() or ch == "_").strip("_")
    if not base:
        base = "sheet"

    digest = short_hash(
        hash_payload(
            {
                "logical_name": logical_name,
                "occurrence": int(occurrence),
                "nonce": int(nonce),
                "columns": list(df.columns),
                "head": df.head(25).to_dict(orient="records"),
            }
        ),
        6,
    )
    head = base[: max(1, 31 - (2 + len(digest)))]
    return f"{head}__{digest}"


def resolve_unique_alias(
    logical_name: str,
    df: pd.DataFrame,
    occurrence: int,
    used_aliases: set[str],
    hash_payload: HashPayload,
    short_hash: ShortHash,
) -> str:
    """Resolve alias collisions while preserving deterministic behavior.

    Args:
        logical_name: Logical sheet identifier.
        df: DataFrame payload.
        occurrence: Sequential occurrence count for this logical sheet.
        used_aliases: Existing aliases already written to a workbook.
        hash_payload: Hash function used for stable payload hashing.
        short_hash: Hash shortener function.

    Returns:
        A unique alias not present in ``used_aliases``.
    """
    nonce = 0
    while True:
        alias = alias_for_entry(
            logical_name=logical_name,
            df=df,
            occurrence=occurrence,
            hash_payload=hash_payload,
            short_hash=short_hash,
            nonce=nonce,
        )
        if alias not in used_aliases:
            used_aliases.add(alias)
            return alias
        nonce += 1


def safe_artifact_name(name: str) -> str:
    """Normalize text into a filesystem-safe token.

    Args:
        name: Arbitrary artifact identifier.

    Returns:
        A safe filename token.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name).strip())
    return cleaned.strip("._") or "artifact"


def sheet_name_with_context(
    filename: str,
    sheet_name: str,
    enable_consolidated_workbook: bool,
    consolidated_use_prefix: bool,
) -> str:
    """Create a stable sheet name with optional source-file prefix.

    Args:
        filename: Source filename that produced the sheet.
        sheet_name: Logical sheet name.
        enable_consolidated_workbook: Whether consolidated workbook mode is active.
        consolidated_use_prefix: Whether source filename prefixes are enabled.

    Returns:
        Contextualized sheet name that stays within Excel limits.
    """
    base = safe_sheet_name(sheet_name)
    if not enable_consolidated_workbook or not consolidated_use_prefix:
        return base
    prefix = safe_sheet_name(Path(filename).stem)
    if not prefix:
        return base
    return safe_sheet_name(f"{prefix}__{base}")


def timestamped_filename(filename: str) -> str:
    """Append a timestamp to a file stem while preserving extension.

    Args:
        filename: Source filename.

    Returns:
        Timestamp-suffixed filename.
    """
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".xlsx"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stem}_{ts}{suffix}"
