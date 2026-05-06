"""Typed schema helpers for run manifest payloads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManifestWriteConfig:
    """Manifest writing configuration.

    Attributes:
        float_format: Float formatting for canonical outputs.
        lineterminator: Newline contract.
        encoding: Text encoding.
    """

    float_format: str = "%.6f"
    lineterminator: str = "\n"
    encoding: str = "utf-8"
