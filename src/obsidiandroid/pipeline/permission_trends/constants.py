"""Constants and artifact typing for permission trends reporting."""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMON_PERMISSIONS = (
    "android.permission.internet",
    "android.permission.access_network_state",
)

PERMISSION_ALIAS_MAP_VERSION = "perm_alias_v1"
PERMISSION_ALIAS_MAP = {
    "android.permission.system_overlay_window": "android.permission.system_alert_window",
    "android.permission.install_packages": "android.permission.request_install_packages",
}

PRIMARY_PERMISSION_VIEW = "aosp_only"
PERMISSION_PREFIX = "android.permission."
RUN_SUFFIX_PNG_PATTERN = re.compile(
    r".*_\d{8}T\d{6}Z__[a-z0-9]+\.png$", re.IGNORECASE
)
ARTIFACT_GROUP_FIGURES = "figures"
ARTIFACT_GROUP_TABLES = "tables"
ARTIFACT_GROUP_CONTRACTS = "contracts"
ARTIFACT_GROUP_DOCS = "docs"
BUNDLE_CONTRACT_NAME = "permission_trends"
BUNDLE_CONTRACT_VERSION = "v1"


@dataclass(frozen=True)
class ReportArtifacts:
    """Container for report artifact paths."""

    coverage_csv: str
    anomaly_csv: str
    family_support_csv: str
    dangerous_type_csv: str
    consensus_csv: str
    generic_audit_csv: str
    confusion_summary_csv: str
    confusion_summary_png: str | None
    per_family_perf_csv: str
    dangerous_stats_csv: str
    consensus_correlation_csv: str
    consensus_correlation_txt: str
    banker_clusters_csv: str
    banker_cluster_profiles_csv: str
    temporal_trends_csv: str
    temporal_trends_png: str | None
    bundle_metadata_json: str
    bundle_zip: str
