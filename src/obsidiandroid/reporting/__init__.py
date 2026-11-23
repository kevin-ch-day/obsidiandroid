"""Reporting and figure export helpers, loaded on demand."""

from importlib import import_module

__all__ = [
    "export_confusion_matrix_image",
    "export_manager",
    "preview_confusion_matrix_inline",
]


def __getattr__(name: str):
    if name == "export_manager":
        return import_module(".export_manager", __name__)
    if name in __all__:
        return getattr(import_module(".confusion_matrix_exporter", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
