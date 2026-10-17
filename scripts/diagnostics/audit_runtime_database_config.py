#!/usr/bin/env python3
"""Print a credential-redacted normal-runtime source configuration audit."""

from __future__ import annotations

import json

from obsidiandroid.database.runtime_config_audit import build_runtime_database_config_audit


def main() -> int:
    report = build_runtime_database_config_audit(check_connections=True)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("audit_ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
