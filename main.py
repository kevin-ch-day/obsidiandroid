"""Source-checkout pipeline entrypoint and compatibility module."""

from __future__ import annotations

import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent / "src"
if (_SOURCE_ROOT / "obsidiandroid" / "__init__.py").is_file():
    source_path = str(_SOURCE_ROOT)
    sys.path[:] = [source_path, *(path for path in sys.path if path != source_path)]

from obsidiandroid.cli import main as _pipeline_cli  # noqa: E402

main = _pipeline_cli.main
__all__ = _pipeline_cli.__all__


def __getattr__(name: str):
    if name in __all__:
        return getattr(_pipeline_cli, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


if __name__ == "__main__":
    raise SystemExit(_pipeline_cli.pipeline_exit_code())
