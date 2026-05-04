"""Evidence-mode resolution helpers with deterministic precedence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ENV_EVIDENCE_MODE = "SCYTALEDROID_EVIDENCE_MODE"


class EvidenceModeConfigError(ValueError):
    """Raised when evidence-mode input values are invalid."""


@dataclass(frozen=True)
class EvidenceModeResolution:
    """Resolved evidence-mode state and provenance."""

    resolved_value: bool
    source: str
    raw_inputs: dict[str, Any]


class EvidenceModeImmutableError(RuntimeError):
    """Raised when attempting to change evidence mode after it has been locked."""


def _parse_bool_like(value: Any, source: str, strict: bool) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    if strict:
        raise EvidenceModeConfigError(f"Invalid boolean value for {source}: {value!r}")
    return None


def resolve_evidence_mode(
    *,
    cli_value: bool | None,
    env_value: Any,
    profile: dict[str, Any] | None,
    default: bool = False,
    strict_env: bool = False,
) -> EvidenceModeResolution:
    """Resolve evidence mode from CLI/env/profile with fixed precedence."""
    profile_value = None
    if isinstance(profile, dict):
        profile_value = profile.get("evidence_mode")
        if profile_value is None:
            profile_value = profile.get("paper_mode")

    parsed_cli = _parse_bool_like(cli_value, "cli", strict=True)
    parsed_env = _parse_bool_like(env_value, "env", strict=strict_env)
    parsed_profile = _parse_bool_like(profile_value, "profile", strict=False)

    if parsed_cli is not None:
        source = "cli"
        resolved = parsed_cli
    elif parsed_env is not None:
        source = "env"
        resolved = parsed_env
    elif parsed_profile is not None:
        source = "profile"
        resolved = parsed_profile
    else:
        source = "default"
        resolved = bool(default)

    return EvidenceModeResolution(
        resolved_value=resolved,
        source=source,
        raw_inputs={
            "cli": cli_value,
            "env": env_value,
            "profile": profile_value,
            "default": bool(default),
        },
    )


def enforce_immutable_lock(
    *,
    locked_value: bool | None,
    requested_value: bool,
) -> bool:
    """Enforce evidence-mode immutability once a lock has been established."""
    if locked_value is None:
        return bool(requested_value)
    if bool(locked_value) != bool(requested_value):
        raise EvidenceModeImmutableError(
            "Evidence mode is immutable after startup; attempted mid-run override detected."
        )
    return bool(locked_value)
