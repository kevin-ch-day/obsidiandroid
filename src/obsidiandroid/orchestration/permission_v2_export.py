"""Independently anchored PI V2 export consumer candidate.

Only a root-controlled local approval anchor can authorize an export. The
unpublished candidate has no installed anchor; ordinary research callers may
choose an export path but cannot supply an approval path or trusted digest.
Provider occurrences remain unresolved even when the export is approved.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import stat
from collections.abc import Iterable
from numbers import Integral
from pathlib import Path

import pandas as pd

CONTRACT_VERSION = "obsidiandroid-permission-exact-v2-unresolved-v1"
EXPORT_FORMAT = "erebus-pi-exact-v2-export-v1"
ANCHOR_FORMAT = "obsidiandroid-pi-v2-export-approval-v1"
FROZEN_MANIFEST_SHA256 = "7eea4260d985107f5c9e8a0f692adadda79922cebd6f59761943939e469a7238"
FROZEN_SAMPLE_COUNT = 1813
_ANCHOR_PATH = Path("/etc/obsidiandroid/pi-v2-export-approval.json")
_FRAME_KEY = secrets.token_bytes(32)
_BOUND_FIELDS = (
    "manifest_sha256", "source_commit", "source_authority_digest",
    "projection_policy_version", "interpretation_release", "feature_contract",
    "completeness",
)


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and all(
        char in "0123456789abcdef" for char in value)


def _trusted_anchor_bytes() -> bytes:
    """Read the separately installed root-owned approval; never accept a path from a run."""
    info = _ANCHOR_PATH.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
        or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
        raise ValueError("PI V2 export approval is not root-controlled")
    parent = _ANCHOR_PATH.parent
    for directory in (parent, parent.parent):
        directory_info = directory.lstat()
        if (not stat.S_ISDIR(directory_info.st_mode)
            or directory_info.st_uid != 0
            or directory_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
            raise ValueError("PI V2 export approval directory is not root-controlled")
    with _ANCHOR_PATH.open("rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("PI V2 export approval is oversized")
    return data


def _parse_exact_json(data: bytes) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate PI V2 JSON key")
            result[key] = value
        return result
    result = json.loads(data, object_pairs_hook=unique_pairs)
    if not isinstance(result, dict):
        raise TypeError("PI V2 document is not an object")
    return result


def _checked_export(export_path: Path) -> tuple[bytes, bytes, dict]:
    anchor_bytes = _trusted_anchor_bytes()
    anchor = _parse_exact_json(anchor_bytes)
    if (anchor.get("format") != ANCHOR_FORMAT
        or not _hex(anchor.get("approved_export_sha256"))):
        raise ValueError("PI V2 approval anchor is malformed")
    if export_path.is_symlink() or not export_path.is_file():
        raise ValueError("PI V2 export is not a regular file")
    with export_path.open("rb") as stream:
        export_bytes = stream.read(64 * 1024 * 1024 + 1)
    if len(export_bytes) > 64 * 1024 * 1024:
        raise ValueError("PI V2 export exceeds reviewed size bound")
    digest = hashlib.sha256(export_bytes).hexdigest()
    if not hmac.compare_digest(digest, anchor["approved_export_sha256"]):
        raise ValueError("PI V2 export bytes differ from independent approval")
    export = _parse_exact_json(export_bytes)
    if export.get("format") != EXPORT_FORMAT:
        raise ValueError("PI V2 export format is unsupported")
    for field in _BOUND_FIELDS:
        if field not in anchor or anchor[field] != export.get(field):
            raise ValueError(f"PI V2 export approval differs at {field}")
    if (export["feature_contract"] != CONTRACT_VERSION
        or export["completeness"] != "COMPLETE"
        or export["manifest_sha256"] != FROZEN_MANIFEST_SHA256
        or not _hex(export["source_authority_digest"])
        or not _hex(export["source_commit"], 40)
        or not isinstance(export.get("samples"), list)
        or len(export["samples"]) != FROZEN_SAMPLE_COUNT
        or not isinstance(export["projection_policy_version"], str)
        or not export["projection_policy_version"]
        or not isinstance(export["interpretation_release"], str)
        or not export["interpretation_release"]):
        raise ValueError("PI V2 export identity or completeness is invalid")
    if _trusted_anchor_bytes() != anchor_bytes:
        raise ValueError("PI V2 export approval changed during loading")
    return export_bytes, anchor_bytes, export


def _sample_identity(samples: pd.DataFrame) -> list[tuple[int, str]]:
    if not {"sample_id", "sha256"} <= set(samples.columns):
        raise ValueError("PI V2 sample identity is incomplete")
    rows = []
    for sample_id, sha in samples[["sample_id", "sha256"]].itertuples(
        index=False, name=None
    ):
        if (not isinstance(sample_id, Integral) or isinstance(sample_id, bool)
            or sample_id <= 0 or not isinstance(sha, str)):
            raise TypeError("PI V2 sample identity is not an exact positive integer/SHA")
        rows.append((int(sample_id), sha))
    if (len(rows) != len(set(rows)) or len({row[0] for row in rows}) != len(rows)
        or len({row[1] for row in rows}) != len(rows)
        or any(not _hex(sha) for _, sha in rows)):
        raise ValueError("PI V2 sample identity is duplicated or invalid")
    return sorted(rows)


def _training_identity(values: Iterable[int]) -> tuple[int, ...]:
    members = list(values)
    if any(not isinstance(value, Integral) or isinstance(value, bool)
           or value <= 0 for value in members):
        raise ValueError("PI V2 training identity is not an exact positive integer")
    return tuple(sorted({int(value) for value in members}))


def _digest_frame(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_json(orient="split", index=False).encode()).hexdigest()


def _seal(frame: pd.DataFrame, *, export_path: Path, export_sha: str,
          anchor_sha: str, samples: pd.DataFrame, training: tuple[int, ...],
          min_support: int) -> None:
    frame.attrs.update({
        "permission_feature_contract_version": CONTRACT_VERSION,
        "permission_v2_export_path": str(export_path.resolve(strict=True)),
        "permission_v2_export_sha256": export_sha,
        "permission_v2_anchor_sha256": anchor_sha,
        "permission_v2_sample_identity": _sample_identity(samples),
        "permission_training_sample_ids": training,
        "permission_min_support": min_support,
        "permission_feature_content_digest": _digest_frame(frame),
    })
    identity = json.dumps({key: frame.attrs[key] for key in sorted(frame.attrs)
                           if key.startswith("permission_") and key != "permission_v2_seal"},
                          sort_keys=True, separators=(",", ":"))
    frame.attrs["permission_v2_seal"] = hmac.new(
        _FRAME_KEY, identity.encode(), hashlib.sha256).hexdigest()


def assert_verified_v2_frame(frame: pd.DataFrame, *, samples: pd.DataFrame,
                             training_sample_ids: Iterable[int], min_support: int) -> None:
    """Recheck the anchor and exact export bytes before cache fusion or ablation."""
    if not isinstance(min_support, Integral) or isinstance(min_support, bool) or min_support < 1:
        raise ValueError("PI V2 feature support must be a positive integer")
    if frame.attrs.get("permission_feature_contract_version") != CONTRACT_VERSION:
        raise ValueError("PI V2 feature contract differs")
    if (frame.attrs.get("permission_v2_sample_identity") != _sample_identity(samples)
        or frame.attrs.get("permission_training_sample_ids") != _training_identity(training_sample_ids)
        or frame.attrs.get("permission_min_support") != min_support
        or frame.attrs.get("permission_feature_content_digest") != _digest_frame(frame)):
        raise ValueError("PI V2 cached frame content or policy changed")
    identity = json.dumps({key: frame.attrs[key] for key in sorted(frame.attrs)
                           if key.startswith("permission_") and key != "permission_v2_seal"},
                          sort_keys=True, separators=(",", ":"))
    if not hmac.compare_digest(str(frame.attrs.get("permission_v2_seal", "")),
                               hmac.new(_FRAME_KEY, identity.encode(), hashlib.sha256).hexdigest()):
        raise ValueError("PI V2 cached frame seal differs")
    path = Path(str(frame.attrs.get("permission_v2_export_path", "")))
    export_bytes, anchor_bytes, _ = _checked_export(path)
    if (hashlib.sha256(export_bytes).hexdigest() != frame.attrs["permission_v2_export_sha256"]
        or hashlib.sha256(anchor_bytes).hexdigest() != frame.attrs["permission_v2_anchor_sha256"]):
        raise ValueError("PI V2 cached frame source or approval changed")


def build_v2_unresolved_features(samples: pd.DataFrame, export_path: Path, *,
                                 training_sample_ids: Iterable[int],
                                 min_support: int = 1) -> pd.DataFrame:
    """Build occurrence features only under an exact independently approved export."""
    if not isinstance(min_support, Integral) or isinstance(min_support, bool) or min_support < 1:
        raise ValueError("PI V2 feature support must be a positive integer")
    export_bytes, anchor_bytes, export = _checked_export(export_path)
    expected = _sample_identity(samples)
    training = _training_identity(training_sample_ids)
    if not training or not set(training) <= {sample_id for sample_id, _ in expected}:
        raise ValueError("PI V2 training membership is invalid")
    records = export.get("samples")
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("PI V2 export sample membership is incomplete")
    observed = []
    projected_by_sample: dict[int, set[str]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise TypeError("PI V2 export sample is malformed")
        sample_id, sha = record.get("sample_id"), record.get("sha256")
        if (not isinstance(sample_id, int) or isinstance(sample_id, bool)
            or not _hex(sha) or not _hex(record.get("source_snapshot_digest"))
            or record.get("evidence_state") != "PROVIDER_REPORTED_UNRESOLVED"
            or not isinstance(record.get("members"), list)
            or not record["members"]):
            raise ValueError("PI V2 export sample provenance is incomplete")
        observed.append((sample_id, sha))
        pairs = set()
        projected = set()
        for member in record["members"]:
            if (not isinstance(member, dict)
                or not isinstance(member.get("raw_token"), str)
                or not isinstance(member.get("projected_token"), str)
                or not member["raw_token"] or not member["projected_token"]):
                raise ValueError("PI V2 exact token is malformed")
            pair = (member["raw_token"], member["projected_token"])
            if pair in pairs:
                raise ValueError("PI V2 exact source member is duplicated")
            pairs.add(pair)
            projected.add(pair[1])
        projected_by_sample[sample_id] = projected
    if sorted(observed) != expected:
        raise ValueError("PI V2 export sample identity differs")
    support: dict[str, int] = {}
    for sample_id in training:
        for token in projected_by_sample[sample_id]:
            support[token] = support.get(token, 0) + 1
    selected = sorted(token for token, count in support.items() if count >= min_support)
    frame = samples[["sample_id"]].copy().reset_index(drop=True)
    for token in selected:
        name = "perm_provider_unresolved__" + hashlib.sha256(token.encode()).hexdigest()
        frame[name] = frame["sample_id"].map(
            lambda sample_id, token=token: int(token in projected_by_sample[int(sample_id)]))
    frame["perm_status__provider_reported_unresolved_count"] = frame["sample_id"].map(
        lambda sample_id: len(projected_by_sample[int(sample_id)]))
    frame["perm_status__manifest_verified"] = 0
    frame.attrs["permission_vocabulary_digest"] = hashlib.sha256(
        "\n".join(selected).encode()).hexdigest()
    _seal(frame, export_path=export_path,
          export_sha=hashlib.sha256(export_bytes).hexdigest(),
          anchor_sha=hashlib.sha256(anchor_bytes).hexdigest(),
          samples=samples, training=training, min_support=min_support)
    assert_verified_v2_frame(frame, samples=samples, training_sample_ids=training,
                             min_support=min_support)
    return frame
