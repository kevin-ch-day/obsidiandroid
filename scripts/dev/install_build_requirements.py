"""Install declared build requirements for checks that disable build isolation."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tomllib


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    with (root / "pyproject.toml").open("rb") as handle:
        requirements = tomllib.load(handle)["build-system"]["requires"]
    subprocess.run([sys.executable, "-m", "pip", "install", *requirements], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
