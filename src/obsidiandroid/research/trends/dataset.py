"""Frozen-dataset loading with digest refusal and typed accessors.

The Parquet is read only through ``load_dataset``; a digest mismatch raises before any bytes are parsed. Masks follow the
dataset's own denominators.json predicates: DETECTED_V2 = det_malicious >= floor AND source_class_state != 'BENIGN_0'
(unknown source class retained, NULL-safe); BENIGN_SOURCE_V2 = label_v2_provenance == 'BENIGN_SOURCE_LABELED'.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

REQUIRED_COLUMNS: tuple[str, ...] = (
    "id_sample_id", "id_sha256", "time_first_submission_year", "trend_year_eligible", "corpus_resigned_2017",
    "det_malicious", "det_engines_present", "source_class_state", "label_v2_provenance", "label_v2_type_v2",
    "label_v2_family_v2", "label_has_family_v2", "label_has_type_v2", "label_v1_1_type_v1_1", "label_v2_avclass_class_tokens",
    "pay_permission_names_raw", "perm_profile_hash", "signer_thumbprint_raw", "signer_is_aosp_test_key",
    "signer_is_marco_test2014", "report_age_days", "batch_source_label", "sdk_catalog_target", "sdk_catalog_min",
    "det_report_state", "group_detected_v2", "group_benign_source_v2", "attack_status", "attack_assessments",
)
DEFAULT_DETECTION_FLOOR = 4


class DigestMismatch(RuntimeError):
    """The file on disk is not the frozen dataset named by the caller."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _default_reader(path: Path, columns: list[str]) -> pd.DataFrame:
    import pyarrow.parquet as pq  # lazy: pyarrow is only needed to read the real dataset

    return pq.read_table(path, columns=columns).to_pandas()


def parse_permission_cell(value) -> list[str] | None:
    """Typed JSON cell -> list of exact permission strings; None when the dictionary is absent."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        if value in ("", "null"):
            return None
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else None
    return None


@dataclass
class TrendDataset:
    frame: pd.DataFrame
    digest: str
    source: str
    detection_floor: int = DEFAULT_DETECTION_FLOOR
    notes: dict = field(default_factory=dict)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame, digest: str = "synthetic", source: str = "frame", detection_floor: int = DEFAULT_DETECTION_FLOOR) -> "TrendDataset":
        missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
        if missing:
            raise ValueError(f"missing required columns: {missing}")
        frame = frame.copy()
        frame["perms"] = frame["pay_permission_names_raw"].apply(parse_permission_cell)
        frame["has_dict"] = frame["perms"].notna()
        frame["year"] = pd.to_numeric(frame["time_first_submission_year"], errors="coerce").astype("Int64")
        frame["batch"] = frame["batch_source_label"].fillna("(null)").replace("", "(null)")
        frame["test_key"] = frame["signer_is_aosp_test_key"].fillna(False).astype(bool) | frame["signer_is_marco_test2014"].fillna(False).astype(bool)
        return cls(frame=frame, digest=digest, source=source, detection_floor=detection_floor)

    # --- masks (denominators.json predicates) -------------------------------------------------------------
    def detected_mask(self, floor: int | None = None) -> pd.Series:
        floor = self.detection_floor if floor is None else floor
        malicious = pd.to_numeric(self.frame["det_malicious"], errors="coerce")
        return (malicious >= floor).fillna(False) & (self.frame["source_class_state"] != "BENIGN_0")

    def benign_source_mask(self) -> pd.Series:
        return self.frame["label_v2_provenance"] == "BENIGN_SOURCE_LABELED"

    def eligible_mask(self) -> pd.Series:
        return self.frame["trend_year_eligible"].fillna(False).astype(bool)

    def detected(self, floor: int | None = None, eligible_only: bool = True) -> pd.DataFrame:
        mask = self.detected_mask(floor)
        if eligible_only:
            mask &= self.eligible_mask()
        return self.frame[mask]

    def benign(self) -> pd.DataFrame:
        return self.frame[self.benign_source_mask()]

    def check_stored_groups(self) -> dict:
        """Cross-check recomputed DETECTED_V2 / BENIGN_SOURCE_V2 against the stored group columns (floor 4 only)."""
        det = self.detected_mask(DEFAULT_DETECTION_FLOOR); ben = self.benign_source_mask()
        return {"detected_recomputed": int(det.sum()), "detected_stored": int(self.frame["group_detected_v2"].fillna(False).astype(bool).sum()),
                "detected_agree": bool((det == self.frame["group_detected_v2"].fillna(False).astype(bool)).all()),
                "benign_recomputed": int(ben.sum()), "benign_stored": int(self.frame["group_benign_source_v2"].fillna(False).astype(bool).sum()),
                "benign_agree": bool((ben == self.frame["group_benign_source_v2"].fillna(False).astype(bool)).all())}


def load_dataset(path: str | Path, expected_sha256: str, reader: Callable[[Path, list[str]], pd.DataFrame] | None = None,
                 extra_columns: tuple[str, ...] = ()) -> TrendDataset:
    """Verify the digest FIRST; refuse to read anything on mismatch."""
    path = Path(path)
    if not expected_sha256 or len(expected_sha256) != 64:
        raise ValueError("expected_sha256 must be a 64-hex digest")
    actual = sha256_file(path)
    if actual != expected_sha256.lower():
        raise DigestMismatch(f"{path.name}: sha256 {actual} != expected {expected_sha256}")
    frame = (reader or _default_reader)(path, list(dict.fromkeys(REQUIRED_COLUMNS + tuple(extra_columns))))
    return TrendDataset.from_frame(frame, digest=actual, source=str(path))
