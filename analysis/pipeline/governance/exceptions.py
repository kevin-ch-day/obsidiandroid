"""Typed governance exceptions used by pipeline control flow."""


class IntegrityStop(RuntimeError):
    """Raised when run integrity requirements are violated."""


class EvidenceStop(RuntimeError):
    """Raised when evidence-readiness requirements are violated."""


class ConfigStop(ValueError):
    """Raised when profile or runtime configuration is invalid."""

