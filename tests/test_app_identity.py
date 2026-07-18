"""Release identity consistency checks."""

from pathlib import Path
import tomllib

from config.settings.app_identity import APP_VERSION


def test_runtime_version_matches_package_metadata() -> None:
    """Keep the displayed application version aligned with package metadata."""
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert APP_VERSION.removeprefix("v") == metadata["project"]["version"]
