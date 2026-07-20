#!/usr/bin/env python3
"""Print a credential-redacted normal-runtime source configuration audit."""

from __future__ import annotations

import json

from obsidiandroid.database.runtime_config_audit import build_runtime_database_config_audit


def main() -> int:
    print(json.dumps(build_runtime_database_config_audit(check_connections=True), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
