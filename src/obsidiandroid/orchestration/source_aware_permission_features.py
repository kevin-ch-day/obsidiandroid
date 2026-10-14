"""Versioned, fail-closed permission evidence features for research runs.

The caller supplies independently verified receipt bindings. PI observation
source and dictionary authority are different fields; neither substitutes for
the other's evidence. This module never reads or writes source databases.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import json
from pathlib import Path
from collections.abc import Iterable, Mapping

import pandas as pd
import numpy as np


CONTRACT_VERSION = "obsidiandroid-permission-evidence-features-v1"
_ACCEPTED = {"ACCEPTED_EXACT", "ACCEPTED_ALIAS"}
_FRAME_SEAL_KEY = secrets.token_bytes(32)


def _hash_evidence_file(path: Path) -> str:
    """Hash retained evidence without reading a large source bundle into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_payload(frame: pd.DataFrame) -> bytes:
    """Canonicalize the actual frame, including status masks and row order."""
    return frame.to_json(orient="split", index=False, date_format="iso").encode("utf-8")


def _policy_digest(
    accepted_aliases: Mapping[tuple[str, str], str] | None,
    training_sample_ids: Iterable[int], min_support: int,
) -> str:
    rows = sorted((raw, canonical, digest) for (raw, canonical), digest
                  in (accepted_aliases or {}).items())
    policy = {"aliases": rows, "training_sample_ids": sorted(set(training_sample_ids)),
              "min_support": min_support}
    return hashlib.sha256(json.dumps(policy, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _sample_digest(samples: pd.DataFrame) -> str:
    if not {"sample_id", "sha256"} <= set(samples.columns):
        raise ValueError("source-aware sample identity is incomplete")
    pairs = sorted((int(sample_id), str(sha)) for sample_id, sha in
                   samples[["sample_id", "sha256"]].itertuples(index=False, name=None))
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()


def _seal_frame(
    frame: pd.DataFrame, *, source_snapshot_digest: str,
    accepted_aliases: Mapping[tuple[str, str], str] | None,
    source_file_bindings: tuple[tuple[str, str], ...],
    source_directory_memberships: tuple[tuple[str, tuple[str, ...]], ...],
    sample_digest: str,
    training_sample_ids: tuple[int, ...],
    min_support: int,
) -> None:
    if len(source_snapshot_digest) != 64 or any(c not in "0123456789abcdef" for c in source_snapshot_digest):
        raise ValueError("verified source snapshot digest is required")
    frame.attrs["permission_source_snapshot_digest"] = source_snapshot_digest
    frame.attrs["permission_policy_digest"] = _policy_digest(
        accepted_aliases, training_sample_ids, min_support)
    frame.attrs["permission_sample_identity_digest"] = sample_digest
    frame.attrs["permission_training_sample_ids"] = training_sample_ids
    frame.attrs["permission_min_support"] = min_support
    frame.attrs["permission_feature_content_digest"] = hashlib.sha256(_frame_payload(frame)).hexdigest()
    frame.attrs["permission_source_file_bindings"] = source_file_bindings
    frame.attrs["permission_source_directory_memberships"] = source_directory_memberships
    identity = "|".join((CONTRACT_VERSION, source_snapshot_digest,
                         frame.attrs["permission_policy_digest"],
                         frame.attrs["permission_feature_content_digest"],
                         json.dumps(source_file_bindings),
                         json.dumps(source_directory_memberships), sample_digest))
    frame.attrs["permission_feature_seal"] = hmac.new(
        _FRAME_SEAL_KEY, identity.encode(), hashlib.sha256
    ).hexdigest()


def assert_verified_source_aware_frame(
    frame: pd.DataFrame, *, accepted_aliases: Mapping[tuple[str, str], str] | None,
    samples: pd.DataFrame | None = None,
    training_sample_ids: Iterable[int] | None = None,
    min_support: int | None = None,
) -> None:
    """Reject forged or changed cached frames before permission fusion.

    The in-process seal intentionally cannot survive a restart. A later run
    must reload and verify its source files; serialized pandas attrs are not
    research authority. The caller must also recheck the live research gate.
    """
    if frame.attrs.get("permission_feature_contract_version") != CONTRACT_VERSION:
        raise ValueError("source-aware feature contract is missing or incompatible")
    source = frame.attrs.get("permission_source_snapshot_digest")
    if not isinstance(source, str) or len(source) != 64:
        raise ValueError("source-aware feature snapshot identity is missing")
    training = (tuple(sorted(set(training_sample_ids))) if training_sample_ids is not None
                else frame.attrs.get("permission_training_sample_ids"))
    support = min_support if min_support is not None else frame.attrs.get("permission_min_support")
    if not isinstance(training, tuple) or not isinstance(support, int):
        raise ValueError("source-aware feature policy identity is missing")
    if frame.attrs.get("permission_policy_digest") != _policy_digest(
        accepted_aliases, training, support):
        raise ValueError("source-aware feature policy changed")
    sample_digest = frame.attrs.get("permission_sample_identity_digest")
    if samples is not None and sample_digest != _sample_digest(samples):
        raise ValueError("source-aware sample identity changed")
    content = hashlib.sha256(_frame_payload(frame)).hexdigest()
    if frame.attrs.get("permission_feature_content_digest") != content:
        raise ValueError("source-aware feature content changed")
    bindings = frame.attrs.get("permission_source_file_bindings")
    if not isinstance(bindings, tuple) or not bindings:
        raise ValueError("source-aware feature file binding is missing")
    for path, digest in bindings:
        try:
            actual = _hash_evidence_file(Path(path))
        except OSError as exc:
            raise ValueError("source-aware evidence file is unavailable") from exc
        if not hmac.compare_digest(actual, digest):
            raise ValueError("source-aware evidence file changed")
    directories = frame.attrs.get("permission_source_directory_memberships")
    if not isinstance(directories, tuple):
        raise ValueError("source-aware evidence directory binding is missing")
    for directory, expected_names in directories:
        if tuple(sorted(path.name for path in Path(directory).glob(
            "pi-production-sample-*.json"))) != expected_names:
            raise ValueError("source-aware evidence directory membership changed")
    identity = "|".join((CONTRACT_VERSION, source, frame.attrs["permission_policy_digest"],
                         content, json.dumps(bindings), json.dumps(directories),
                         str(sample_digest)))
    expected = hmac.new(_FRAME_SEAL_KEY, identity.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(frame.attrs.get("permission_feature_seal", "")), expected):
        raise ValueError("source-aware feature verification seal is invalid")


def _token_feature(token: str, origin: str) -> str:
    # A digest preserves exact-token identity even when punctuation sanitization
    # would collide; feature names cannot disclose family or raw source labels.
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"perm_{origin}__{digest}"


def _build_from_verified_evidence(
    samples: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    training_sample_ids: Iterable[int],
    min_support: int = 1,
    vocabulary: Iterable[str] | None = None,
    accepted_aliases: Mapping[tuple[str, str], str] | None = None,
    source_snapshot_digest: str,
    source_file_bindings: tuple[tuple[str, str], ...],
    source_directory_memberships: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> pd.DataFrame:
    """Build v1 features from adapter-verified rows with training-only vocabulary.

    ``source_verified`` must mean the immutable provider action/receipt chain or
    independent APK byte/parse receipt was checked by the upstream adapter.
    A PI ``source`` string alone cannot set it. Unknown rows affect status masks,
    never positive permission features or confirmed negatives.
    """
    if min_support < 1:
        raise ValueError("minimum support must be positive")
    required_samples = {"sample_id", "sha256"}
    required_evidence = {
        "sample_id", "sha256", "raw_token", "projected_token", "observation_origin",
        "source_verified", "source_receipt_digest", "event_verified",
        "identity_status", "canonical_token",
    }
    if not required_samples <= set(samples) or not required_evidence <= set(evidence):
        raise ValueError("source-aware sample/evidence contract is incomplete")
    if samples["sample_id"].isna().any() or samples["sample_id"].duplicated().any():
        raise ValueError("sample identity is missing or duplicated")
    if samples["sha256"].isna().any() or samples["sha256"].duplicated().any():
        raise ValueError("sample SHA identity is missing or duplicated")
    if any(
        not isinstance(sha, str)
        or len(sha) != 64
        or any(char not in "0123456789abcdef" for char in sha)
        for sha in samples["sha256"]
    ):
        raise ValueError("sample SHA identity is invalid")
    sample_sha = dict(zip(samples["sample_id"], samples["sha256"], strict=True))
    train_ids = set(training_sample_ids)
    if not train_ids or not train_ids <= set(sample_sha):
        raise ValueError("training membership is missing or outside the cohort")

    rows: list[tuple[int, str, str, tuple[int, str, str]]] = []
    # Status counts describe projected PI facts, not raw source spellings.
    # Keep origin in the identity so manifest and provider evidence never merge.
    unresolved_facts: set[tuple[int, str, str]] = set()
    conflict_facts: set[tuple[int, str, str]] = set()
    alias_review_facts: set[tuple[int, str, str]] = set()
    provider_seen: set[int] = set()
    manifest_seen: set[int] = set()
    for row_index, item in enumerate(evidence.itertuples(index=False)):
        sample_id = getattr(item, "sample_id")
        if sample_id not in sample_sha or sample_sha[sample_id] != getattr(item, "sha256"):
            raise ValueError("permission evidence sample/SHA binding differs")
        origin = str(getattr(item, "observation_origin") or "").lower()
        raw_token = str(getattr(item, "raw_token") or "")
        projected_token = str(getattr(item, "projected_token") or "")
        # Malformed rows without a projected identity remain distinct rather
        # than silently collapsing unrelated missing evidence.
        fact_key = (sample_id, origin, projected_token or f"<missing:{row_index}>")
        identity = str(getattr(item, "identity_status") or "").upper()
        canonical = str(getattr(item, "canonical_token") or "")
        source_checked = getattr(item, "source_verified")
        verified = isinstance(source_checked, (bool, np.bool_)) and bool(source_checked)
        receipt_digest = str(getattr(item, "source_receipt_digest") or "")
        verified = verified and len(receipt_digest) == 64 and all(
            char in "0123456789abcdef" for char in receipt_digest
        )
        if origin == "provider":
            event_checked = getattr(item, "event_verified")
            verified = verified and isinstance(event_checked, (bool, np.bool_)) and bool(event_checked)
        if identity == "VERIFIED_EMPTY":
            if (origin != "manifest" or not verified or raw_token or projected_token
                    or canonical or getattr(item, "event_verified") is not False):
                raise ValueError("verified-empty manifest evidence is malformed")
            manifest_seen.add(sample_id)
            continue
        if origin not in {"provider", "manifest"} or not raw_token or not projected_token:
            unresolved_facts.add(fact_key)
            continue
        if verified:
            if origin == "provider":
                provider_seen.add(sample_id)
            else:
                manifest_seen.add(sample_id)
        if not verified or identity not in _ACCEPTED or not canonical:
            unresolved_facts.add(fact_key)
            if identity in {"CONFLICT", "CASE_CONFLICT"}:
                conflict_facts.add(fact_key)
            elif identity == "UNRESOLVED_ALIAS":
                alias_review_facts.add(fact_key)
            continue
        if identity == "ACCEPTED_EXACT" and projected_token != canonical:
            unresolved_facts.add(fact_key)
            continue
        if identity == "ACCEPTED_ALIAS":
            alias_digest = str(getattr(item, "alias_release_digest", "") or "")
            if (
                len(alias_digest) != 64
                or any(c not in "0123456789abcdef" for c in alias_digest)
                or (accepted_aliases or {}).get((projected_token, canonical)) != alias_digest
            ):
                unresolved_facts.add(fact_key)
                continue
        rows.append((sample_id, origin, canonical, fact_key))

    # A projected fact has one canonical identity. Even individually reviewed
    # alias rows must abstain if they disagree about that identity.
    canonicals_by_fact: dict[tuple[int, str, str], set[str]] = {}
    for _sample_id, _origin, canonical, key in rows:
        canonicals_by_fact.setdefault(key, set()).add(canonical)
    for key, canonicals in canonicals_by_fact.items():
        if len(canonicals) > 1:
            unresolved_facts.add(key)
            conflict_facts.add(key)

    # Contradictory evidence for the same projected fact must not create both
    # a positive feature and an unresolved status.
    positive_rows = [
        (sample_id, origin, canonical)
        for sample_id, origin, canonical, key in rows
        if key not in unresolved_facts
    ]
    facts = pd.DataFrame(positive_rows, columns=["sample_id", "origin", "token"])
    if vocabulary is None:
        train_facts = facts[facts["sample_id"].isin(train_ids)]
        support = train_facts.groupby(["origin", "token"])["sample_id"].nunique()
        selected = sorted(
            _token_feature(token, origin)
            for (origin, token), count in support.items() if count >= min_support
        )
    else:
        selected = sorted(set(vocabulary))
        if any(
            not (name.startswith("perm_provider__") or name.startswith("perm_manifest__"))
            or len(name.rsplit("__", 1)[-1]) != 64
            for name in selected
        ):
            raise ValueError("source-aware vocabulary is invalid")
    out = samples[["sample_id"]].copy().reset_index(drop=True)
    for name in selected:
        out[name] = 0
    for sample_id, origin, token in positive_rows:
        name = _token_feature(token, origin)
        if name in out.columns:
            out.loc[out["sample_id"] == sample_id, name] = 1
    def _count_by_sample(facts: set[tuple[int, str, str]]) -> dict[int, int]:
        counts: dict[int, int] = {}
        for sample_id, _, _ in facts:
            counts[sample_id] = counts.get(sample_id, 0) + 1
        return counts

    unresolved_count = _count_by_sample(unresolved_facts)
    conflict_count = _count_by_sample(conflict_facts)
    alias_review_count = _count_by_sample(alias_review_facts)
    out["perm_status__has_provider_report"] = out["sample_id"].isin(provider_seen).astype(int)
    out["perm_status__has_manifest_parse"] = out["sample_id"].isin(manifest_seen).astype(int)
    out["perm_status__provider_missing"] = (~out["sample_id"].isin(provider_seen)).astype(int)
    out["perm_status__manifest_missing"] = (~out["sample_id"].isin(manifest_seen)).astype(int)
    out["perm_status__unresolved_count"] = out["sample_id"].map(
        unresolved_count
    ).fillna(0).astype(int)
    out["perm_status__governance_conflict_count"] = out["sample_id"].map(
        conflict_count
    ).fillna(0).astype(int)
    out["perm_status__alias_review_count"] = out["sample_id"].map(
        alias_review_count
    ).fillna(0).astype(int)
    out.attrs["permission_feature_contract_version"] = CONTRACT_VERSION
    out.attrs["permission_vocabulary"] = selected
    out.attrs["permission_vocabulary_digest"] = hashlib.sha256(
        "\n".join(selected).encode("utf-8")
    ).hexdigest()
    _seal_frame(out, source_snapshot_digest=source_snapshot_digest,
                accepted_aliases=accepted_aliases,
                source_file_bindings=source_file_bindings,
                source_directory_memberships=source_directory_memberships,
                sample_digest=_sample_digest(samples),
                training_sample_ids=tuple(sorted(train_ids)),
                min_support=min_support)
    return out


def build_source_aware_permission_features(*args: object, **kwargs: object) -> pd.DataFrame:
    """Fail closed on a caller-supplied DataFrame, regardless of its claims."""
    raise ValueError(
        "direct source-aware DataFrames are untrusted; use the verified receipt or static loader"
    )
