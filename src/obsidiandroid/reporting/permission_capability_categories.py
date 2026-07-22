"""Permission capability-category contract and offline reports.

Capability categories are orthogonal to Android protection / governance lanes.
A permission may carry both ``capability_category`` and ``protection_lane``.
Static declarations do not prove runtime behavior.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from obsidiandroid.common.csv_io import write_csv
from obsidiandroid.reporting.package_balanced_permission_analysis import (
    assign_package_keys,
    family_balanced_prevalence,
    package_balanced_prevalence,
    sample_weighted_prevalence,
)
from obsidiandroid.reporting.permission_governance_lanes import (
    PROTECTION_LANE_CONTRACT_VERSION,
    classify_protection_lane,
)
from obsidiandroid.reporting.type_permission_pattern_report import resolve_git_commit, sha256_file
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID, verify_completed_run

CAPABILITY_CATEGORY_CONTRACT_VERSION = "1.0.0"
CAPABILITY_COMPOSER_VERSION = "1.0.0"
MULTI_LABEL_POLICY = "explicit_map_only"

CANONICAL_CAPABILITY_CATEGORIES: tuple[str, ...] = (
    "sms_mms",
    "phone_call_log",
    "contacts_accounts",
    "notifications",
    "accessibility",
    "overlay_screen",
    "location",
    "camera",
    "microphone_audio",
    "bluetooth_nearby",
    "wifi_network",
    "storage_media",
    "package_install_remove",
    "boot_persistence",
    "battery_background",
    "device_admin_security",
    "calendar",
    "sensors",
    "oem_platform",
    "app_defined_unknown",
)

# Explicit multi-label is allowed only here (token → one or more categories).
EXPLICIT_PERMISSION_CAPABILITY_MAP: dict[str, tuple[str, ...]] = {
    # SMS / MMS
    "android.permission.read_sms": ("sms_mms",),
    "android.permission.write_sms": ("sms_mms",),
    "android.permission.send_sms": ("sms_mms",),
    "android.permission.receive_sms": ("sms_mms",),
    "android.permission.receive_mms": ("sms_mms",),
    "android.permission.receive_wap_push": ("sms_mms",),
    "android.permission.broadcast_sms": ("sms_mms",),
    "android.permission.read_cell_broadcasts": ("sms_mms",),
    # Phone / call log
    "android.permission.read_phone_state": ("phone_call_log",),
    "android.permission.read_phone_numbers": ("phone_call_log",),
    "android.permission.read_privileged_phone_state": ("phone_call_log",),
    "android.permission.call_phone": ("phone_call_log",),
    "android.permission.read_call_log": ("phone_call_log",),
    "android.permission.write_call_log": ("phone_call_log",),
    "android.permission.process_outgoing_calls": ("phone_call_log",),
    "android.permission.modify_phone_state": ("phone_call_log",),
    "android.permission.answer_phone_calls": ("phone_call_log",),
    "android.permission.add_voicemail": ("phone_call_log",),
    "android.permission.use_sip": ("phone_call_log",),
    # Contacts / accounts
    "android.permission.read_contacts": ("contacts_accounts",),
    "android.permission.write_contacts": ("contacts_accounts",),
    "android.permission.get_accounts": ("contacts_accounts",),
    "android.permission.manage_accounts": ("contacts_accounts",),
    "android.permission.authenticate_accounts": ("contacts_accounts",),
    "android.permission.use_credentials": ("contacts_accounts",),
    "android.permission.get_accounts_privileged": ("contacts_accounts",),
    # Notifications
    "android.permission.post_notifications": ("notifications",),
    "android.permission.access_notification_policy": ("notifications",),
    "android.permission.bind_notification_listener_service": ("notifications",),
    "android.permission.status_bar_service": ("notifications",),
    "android.permission.expand_status_bar": ("notifications",),
    # Accessibility
    "android.permission.bind_accessibility_service": ("accessibility",),
    "android.permission.accessibility_service": ("accessibility",),
    # Overlay / screen
    "android.permission.system_alert_window": ("overlay_screen",),
    "android.permission.internal_system_window": ("overlay_screen",),
    "android.permission.system_overlay_window": ("overlay_screen",),
    "android.permission.action.manage.overlay.permission": ("overlay_screen",),
    "android.permission.hide.non.system.overlay.windows": ("overlay_screen",),
    "android.permission.turn_screen_on": ("overlay_screen",),
    "android.permission.disable_keyguard": ("overlay_screen", "device_admin_security"),
    "android.permission.use_full_screen_intent": ("overlay_screen", "notifications"),
    "android.permission.foreground_service_media_projection": ("overlay_screen",),
    "android.permission.capture_video_output": ("overlay_screen", "camera"),
    "android.permission.capture_secure_video_output": ("overlay_screen", "camera"),
    # Location
    "android.permission.access_fine_location": ("location",),
    "android.permission.access_coarse_location": ("location",),
    "android.permission.access_background_location": ("location",),
    "android.permission.access_location_extra_commands": ("location",),
    "android.permission.location_hardware": ("location",),
    "android.permission.access_mock_location": ("location",),
    # Camera
    "android.permission.camera": ("camera",),
    "android.permission.flashlight": ("camera",),
    # Microphone / audio
    "android.permission.record_audio": ("microphone_audio",),
    "android.permission.modify_audio_settings": ("microphone_audio",),
    "android.permission.capture_audio_output": ("microphone_audio",),
    "android.permission.foreground_service_microphone": ("microphone_audio", "battery_background"),
    # Bluetooth / nearby
    "android.permission.bluetooth": ("bluetooth_nearby",),
    "android.permission.bluetooth_admin": ("bluetooth_nearby",),
    "android.permission.bluetooth_connect": ("bluetooth_nearby",),
    "android.permission.bluetooth_scan": ("bluetooth_nearby",),
    "android.permission.bluetooth_advertise": ("bluetooth_nearby",),
    "android.permission.nearby_wifi_devices": ("bluetooth_nearby", "wifi_network"),
    "android.permission.nfc": ("bluetooth_nearby",),
    # Wi-Fi / network
    "android.permission.internet": ("wifi_network",),
    "android.permission.access_network_state": ("wifi_network",),
    "android.permission.change_network_state": ("wifi_network",),
    "android.permission.access_wifi_state": ("wifi_network",),
    "android.permission.change_wifi_state": ("wifi_network",),
    "android.permission.change_wifi_multicast_state": ("wifi_network",),
    "android.permission.write_apn_settings": ("wifi_network",),
    # Storage / media
    "android.permission.read_external_storage": ("storage_media",),
    "android.permission.write_external_storage": ("storage_media",),
    "android.permission.manage_external_storage": ("storage_media",),
    "android.permission.read_media_images": ("storage_media",),
    "android.permission.read_media_video": ("storage_media",),
    "android.permission.read_media_audio": ("storage_media",),
    "android.permission.write_media_storage": ("storage_media",),
    "android.permission.mount_unmount_filesystems": ("storage_media",),
    "android.permission.access_cache_filesystem": ("storage_media",),
    "android.permission.clear_app_cache": ("storage_media",),
    # Package install / remove
    "android.permission.request_install_packages": ("package_install_remove",),
    "android.permission.request_delete_packages": ("package_install_remove",),
    "android.permission.install.packages": ("package_install_remove",),
    "android.permission.delete_packages": ("package_install_remove",),
    "android.permission.query_all_packages": ("package_install_remove",),
    "android.permission.get_installed_apps": ("package_install_remove",),
    "android.permission.get_package_size": ("package_install_remove",),
    "android.permission.restart_packages": ("package_install_remove",),
    "android.permission.read_install_sessions": ("package_install_remove",),
    "android.permission.package_usage_stats": ("package_install_remove",),
    # Boot / persistence
    "android.permission.receive_boot_completed": ("boot_persistence",),
    "android.permission.quickboot_poweron": ("boot_persistence",),
    "android.permission.receive_user_present": ("boot_persistence",),
    "android.permission.schedule_exact_alarm": ("boot_persistence", "battery_background"),
    "android.permission.use_exact_alarm": ("boot_persistence", "battery_background"),
    # Battery / background
    "android.permission.request_ignore_battery_optimizations": ("battery_background",),
    "android.permission.foreground_service": ("battery_background",),
    "android.permission.foreground_service_data_sync": ("battery_background",),
    "android.permission.foreground_service_special_use": ("battery_background",),
    "android.permission.wake_lock": ("battery_background",),
    "android.permission.battery_stats": ("battery_background",),
    "android.permission.kill_background_processes": ("battery_background",),
    "android.permission.request_companion_run_in_background": ("battery_background",),
    "android.permission.request_companion_use_data_in_background": ("battery_background",),
    # Device admin / security
    "android.permission.bind_device_admin": ("device_admin_security",),
    "android.permission.uses_policy_force_lock": ("device_admin_security",),
    "android.permission.write_secure_settings": ("device_admin_security",),
    "android.permission.write_settings": ("device_admin_security",),
    "android.permission.use_fingerprint": ("device_admin_security",),
    "android.permission.use_biometric": ("device_admin_security",),
    "android.permission.read_logs": ("device_admin_security",),
    "android.permission.get_tasks": ("device_admin_security",),
    "android.permission.reorder_tasks": ("device_admin_security",),
    # Calendar
    "android.permission.read_calendar": ("calendar",),
    "android.permission.write_calendar": ("calendar",),
    # Sensors
    "android.permission.body_sensors": ("sensors",),
    "android.permission.activity_recognition": ("sensors",),
    "android.permission.high_sampling_rate_sensors": ("sensors",),
    "android.permission.vibrate": ("sensors",),
}

# Ordered single-label pattern fallbacks (applied only when token absent from explicit map).
# Patterns must not invent multi-label assignments.
_PATTERN_FALLBACKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:^|\.)(?:send_|receive_|read_|write_)?sms|(?:^|\.)mms|(?:^|\.)wap_push", re.I), "sms_mms"),
    (re.compile(r"(?:phone_state|phone_numbers|call_log|call_phone|outgoing_calls|sip|voicemail)", re.I), "phone_call_log"),
    (re.compile(r"(?:contacts|get_accounts|manage_accounts|authenticate_accounts|use_credentials)", re.I), "contacts_accounts"),
    (re.compile(r"(?:notification|status_bar)", re.I), "notifications"),
    (re.compile(r"accessibility", re.I), "accessibility"),
    (re.compile(r"(?:system_alert_window|overlay|draw_over|media_projection|turn_screen|keyguard|full_screen_intent)", re.I), "overlay_screen"),
    (re.compile(r"location", re.I), "location"),
    (re.compile(r"(?:^|\.)camera|(?:^|\.)flashlight", re.I), "camera"),
    (re.compile(r"(?:record_audio|capture_audio|modify_audio|microphone)", re.I), "microphone_audio"),
    (re.compile(r"(?:bluetooth|nearby_wifi|nfc)", re.I), "bluetooth_nearby"),
    (re.compile(r"(?:internet|network_state|wifi|vpn|change_network|write_apn)", re.I), "wifi_network"),
    (re.compile(r"(?:external_storage|manage_external|read_media|write_media|media_storage|mount_unmount|downloads)", re.I), "storage_media"),
    (re.compile(r"(?:install_packages|delete_packages|query_all_packages|get_installed|package_usage|restart_packages)", re.I), "package_install_remove"),
    (re.compile(r"(?:boot_completed|quickboot|receive_user_present|exact_alarm)", re.I), "boot_persistence"),
    (re.compile(r"(?:battery|foreground_service|wake_lock|kill_background|ignore_battery)", re.I), "battery_background"),
    (re.compile(r"(?:device_admin|force_lock|secure_settings|biometric|fingerprint|write_settings)", re.I), "device_admin_security"),
    (re.compile(r"calendar", re.I), "calendar"),
    (re.compile(r"(?:body_sensors|activity_recognition|high_sampling_rate_sensors|^android\.permission\.vibrate$)", re.I), "sensors"),
)


def normalize_permission_token(value: Any) -> str:
    """Normalize a permission token for contract lookup."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().lower()


def classify_capability_categories(permission: Any) -> tuple[str, ...]:
    """Map one permission token to one or more capability categories.

    Multi-label results occur only from ``EXPLICIT_PERMISSION_CAPABILITY_MAP``.
    Pattern fallbacks and OEM/app-defined defaults are single-label.
    """
    token = normalize_permission_token(permission)
    if not token:
        return ("app_defined_unknown",)
    if token in EXPLICIT_PERMISSION_CAPABILITY_MAP:
        cats = EXPLICIT_PERMISSION_CAPABILITY_MAP[token]
        unknown = [c for c in cats if c not in CANONICAL_CAPABILITY_CATEGORIES]
        if unknown:
            raise ValueError(f"Non-canonical capability categories for {token}: {unknown}")
        return cats
    for pattern, category in _PATTERN_FALLBACKS:
        if pattern.search(token):
            return (category,)
    if token.startswith("com.") or token.startswith("android.permission.com."):
        # Vendor / app-namespace tokens: OEM platform when clearly vendor-ish; else app-defined.
        if any(part in token for part in (".samsung.", ".huawei.", ".oppo.", ".xiaomi.", ".meizu.", ".sec.", ".htc.", ".sony", ".oneplus.")):
            return ("oem_platform",)
        if token.startswith("com.google.") or token.startswith("com.android."):
            return ("oem_platform",)
        return ("app_defined_unknown",)
    if token.startswith("android.permission."):
        return ("app_defined_unknown",)
    return ("app_defined_unknown",)


def capability_category_contract_metadata() -> dict[str, Any]:
    """Return durable contract metadata for manifests and docs."""
    return {
        "capability_category_contract_version": CAPABILITY_CATEGORY_CONTRACT_VERSION,
        "composer_version": CAPABILITY_COMPOSER_VERSION,
        "canonical_categories": list(CANONICAL_CAPABILITY_CATEGORIES),
        "multi_label_policy": MULTI_LABEL_POLICY,
        "protection_lane_contract_version": PROTECTION_LANE_CONTRACT_VERSION,
        "orthogonal_to_protection_lanes": True,
        "runtime_behavior_inferred": False,
        "notes": (
            "Capability categories describe declared static permission capability groups. "
            "They do not assert runtime use. Protection lanes remain a separate dimension."
        ),
    }


def build_permission_capability_inventory(
    permissions: Iterable[Any],
    *,
    pi_bucket_source: Mapping[str, Any] | None = None,
    dangerous_bucket: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build token-level capability + protection-lane inventory."""
    rows: list[dict[str, Any]] = []
    for raw in permissions:
        token = normalize_permission_token(raw)
        if not token:
            continue
        cats = classify_capability_categories(token)
        lane = classify_protection_lane(
            pi_bucket_source=(pi_bucket_source or {}).get(token, ""),
            dangerous_bucket=(dangerous_bucket or {}).get(token, ""),
            permission_string=token,
        )
        mapping_kind = "explicit" if token in EXPLICIT_PERMISSION_CAPABILITY_MAP else "fallback_or_default"
        for cat in cats:
            rows.append(
                {
                    "permission_name": token,
                    "capability_category": cat,
                    "protection_lane": lane,
                    "mapping_kind": mapping_kind,
                    "multi_label": len(cats) > 1,
                    "category_count_for_token": len(cats),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "permission_name",
                "capability_category",
                "protection_lane",
                "mapping_kind",
                "multi_label",
                "category_count_for_token",
            ]
        )
    return frame.sort_values(["permission_name", "capability_category"]).reset_index(drop=True)


def _load_labels(run_root: Path, run_id: str) -> pd.DataFrame:
    path = run_root / "diagnostics" / f"aligned_labels_{run_id}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Missing aligned labels: {path}")
    return pd.read_csv(path)


def _load_permission_long(run_root: Path, run_id: str) -> pd.DataFrame:
    path = run_root / "diagnostics" / f"ml_sample_permission_feature_{run_id}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Missing permission feature long table: {path}")
    cols = ["sample_id", "permission_name", "permission_present"]
    frame = pd.read_csv(path, usecols=lambda c: c in cols or True)
    keep = [c for c in cols if c in frame.columns]
    frame = frame[keep].copy()
    frame["permission_name"] = frame["permission_name"].map(normalize_permission_token)
    frame["permission_present"] = pd.to_numeric(frame["permission_present"], errors="coerce").fillna(0).astype(int)
    frame = frame[frame["permission_present"] > 0]
    return frame


def _load_audit_lane_maps(run_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    path = run_root / "diagnostics" / "permission_feature_audit.csv"
    if not path.is_file():
        return {}, {}
    audit = pd.read_csv(path)
    if "permission_string" not in audit.columns:
        return {}, {}
    audit = audit.copy()
    audit["permission_name"] = audit["permission_string"].map(normalize_permission_token)
    pi = {
        str(r.permission_name): str(getattr(r, "pi_bucket_source", "") or "")
        for r in audit.itertuples(index=False)
        if r.permission_name
    }
    danger = {
        str(r.permission_name): str(getattr(r, "dangerous_bucket", "") or "")
        for r in audit.itertuples(index=False)
        if r.permission_name
    }
    return pi, danger


def build_sample_category_matrix(
    labels: pd.DataFrame,
    permission_long: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row per sample with binary capability-category indicators."""
    out = labels[["sample_id", "family_canonical", "type_slug"]].copy()
    if "package_name" in labels.columns:
        out["package_name"] = labels["package_name"]
    if "android_package_name" in labels.columns:
        out["android_package_name"] = labels["android_package_name"]
    out = assign_package_keys(out)

    present = permission_long[permission_long["permission_present"] > 0].copy()
    if present.empty:
        for cat in CANONICAL_CAPABILITY_CATEGORIES:
            out[cat] = 0
        return out

    exploded_rows: list[dict[str, Any]] = []
    for row in present.itertuples(index=False):
        for cat in classify_capability_categories(row.permission_name):
            exploded_rows.append({"sample_id": row.sample_id, "capability_category": cat})
    if not exploded_rows:
        for cat in CANONICAL_CAPABILITY_CATEGORIES:
            out[cat] = 0
        return out
    exploded = pd.DataFrame(exploded_rows).drop_duplicates()
    wide = (
        exploded.assign(flag=1)
        .pivot_table(index="sample_id", columns="capability_category", values="flag", aggfunc="max", fill_value=0)
        .reset_index()
    )
    merged = out.merge(wide, on="sample_id", how="left")
    for cat in CANONICAL_CAPABILITY_CATEGORIES:
        if cat not in merged.columns:
            merged[cat] = 0
        merged[cat] = pd.to_numeric(merged[cat], errors="coerce").fillna(0).astype(int)
    return merged


def _prevalence_rows_for_group(
    frame: pd.DataFrame,
    *,
    group_col: str,
    min_samples: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_value, part in frame.groupby(group_col, dropna=False):
        n = len(part)
        suppressed = n < min_samples
        for cat in CANONICAL_CAPABILITY_CATEGORIES:
            sw = sample_weighted_prevalence(part, cat) if not suppressed else float("nan")
            fb = family_balanced_prevalence(part, cat) if not suppressed else float("nan")
            pb = package_balanced_prevalence(part, cat) if not suppressed else float("nan")
            positives = int(part[cat].sum()) if cat in part.columns and not suppressed else 0
            rows.append(
                {
                    group_col: group_value,
                    "capability_category": cat,
                    "sample_count": n,
                    "positive_sample_count": positives,
                    "sample_weighted_prevalence": sw,
                    "family_balanced_prevalence": fb,
                    "package_balanced_prevalence": pb,
                    "support_suppressed": suppressed,
                    "suppression_reason": f"n<{min_samples}" if suppressed else "",
                    "weighting_schemes": "sample_weighted|family_balanced|package_balanced",
                }
            )
    return pd.DataFrame(rows)


def build_category_by_protection_lane(
    inventory: pd.DataFrame,
    permission_long: pd.DataFrame,
) -> pd.DataFrame:
    """Token-support and sample-support of categories within each protection lane."""
    if inventory.empty or permission_long.empty:
        return pd.DataFrame(
            columns=[
                "capability_category",
                "protection_lane",
                "distinct_permission_tokens",
                "positive_permission_observations",
            ]
        )
    token_lane = inventory.drop_duplicates(["permission_name", "capability_category", "protection_lane"])
    obs = permission_long.merge(
        token_lane[["permission_name", "capability_category", "protection_lane"]],
        on="permission_name",
        how="inner",
    )
    grouped = (
        obs.groupby(["capability_category", "protection_lane"], as_index=False)
        .agg(
            distinct_permission_tokens=("permission_name", "nunique"),
            positive_permission_observations=("permission_present", "sum"),
        )
        .sort_values(["capability_category", "protection_lane"])
    )
    return grouped


def build_category_cooccurrence(sample_matrix: pd.DataFrame, *, min_samples: int = 30) -> pd.DataFrame:
    """Pairwise category co-occurrence on samples (Jaccard + joint prevalence)."""
    n = len(sample_matrix)
    rows: list[dict[str, Any]] = []
    cats = list(CANONICAL_CAPABILITY_CATEGORIES)
    suppressed = n < min_samples
    for i, a in enumerate(cats):
        for b in cats[i:]:
            if suppressed:
                rows.append(
                    {
                        "category_a": a,
                        "category_b": b,
                        "sample_count": n,
                        "both_count": 0,
                        "jaccard": float("nan"),
                        "joint_prevalence": float("nan"),
                        "support_suppressed": True,
                    }
                )
                continue
            va = sample_matrix[a].astype(int)
            vb = sample_matrix[b].astype(int)
            both = int((va & vb).sum())
            union = int((va | vb).sum())
            jaccard = (both / union) if union else float("nan")
            rows.append(
                {
                    "category_a": a,
                    "category_b": b,
                    "sample_count": n,
                    "both_count": both,
                    "jaccard": jaccard,
                    "joint_prevalence": both / n if n else float("nan"),
                    "support_suppressed": False,
                }
            )
    return pd.DataFrame(rows)


def build_dominant_family_category_sensitivity(
    sample_matrix: pd.DataFrame,
    *,
    min_type_samples: int = 30,
    min_type_families: int = 3,
) -> pd.DataFrame:
    """Leave-largest-family shift for category prevalence by type."""
    rows: list[dict[str, Any]] = []
    for type_slug, part in sample_matrix.groupby("type_slug", dropna=False):
        families = part["family_canonical"].fillna("").astype(str)
        family_counts = families[families.ne("")].value_counts()
        if len(part) < min_type_samples or family_counts.size < min_type_families:
            for cat in CANONICAL_CAPABILITY_CATEGORIES:
                rows.append(
                    {
                        "type_slug": type_slug,
                        "capability_category": cat,
                        "sample_count": len(part),
                        "family_count": int(family_counts.size),
                        "largest_family": "",
                        "full_sample_prevalence": float("nan"),
                        "leave_largest_prevalence": float("nan"),
                        "delta_pp": float("nan"),
                        "support_suppressed": True,
                        "suppression_reason": "insufficient_type_support",
                    }
                )
            continue
        largest = str(family_counts.index[0])
        rest = part[families.ne(largest)]
        for cat in CANONICAL_CAPABILITY_CATEGORIES:
            full = float(part[cat].mean())
            leave = float(rest[cat].mean()) if len(rest) else float("nan")
            delta = (leave - full) * 100.0 if pd.notna(leave) else float("nan")
            rows.append(
                {
                    "type_slug": type_slug,
                    "capability_category": cat,
                    "sample_count": len(part),
                    "family_count": int(family_counts.size),
                    "largest_family": largest,
                    "full_sample_prevalence": full,
                    "leave_largest_prevalence": leave,
                    "delta_pp": delta,
                    "support_suppressed": False,
                    "suppression_reason": "",
                }
            )
    return pd.DataFrame(rows)


def _write_heatmap(
    matrix: pd.DataFrame,
    *,
    out_path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    run_id: str,
    weighting: str,
    denominator: int,
    date_semantics: str,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(max(8, matrix.shape[1] * 0.45), max(4, matrix.shape[0] * 0.35)))
    data = matrix.to_numpy(dtype=float)
    im = ax.imshow(data, aspect="auto", vmin=0.0, vmax=1.0, cmap="viridis")
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(list(matrix.columns), rotation=90, fontsize=7)
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(list(matrix.index), fontsize=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.text(
        0.01,
        0.01,
        f"run={run_id}; weighting={weighting}; n={denominator}; "
        f"{date_semantics}; static declarations only; suppressed cells may be NaN",
        fontsize=7,
        wrap=True,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", dpi=140)
    plt.close(fig)


def _pivot_prevalence(df: pd.DataFrame, index: str, value: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work.loc[work["support_suppressed"], value] = np.nan
    return work.pivot_table(index=index, columns="capability_category", values=value, aggfunc="first")


def compose_permission_capability_category_report(
    *,
    run_root: Path,
    run_id: str = EXPECTED_RUN_ID,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
    min_samples: int = 30,
) -> dict[str, Any]:
    """Compose offline capability-category reports from a completed run root."""
    run_root = Path(run_root).resolve()
    verify_completed_run(run_root, expected_run_id=run_id)
    out_dir = Path(output_dir) if output_dir else run_root / "diagnostics" / "permission_capability_categories"
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = _load_labels(run_root, run_id)
    permission_long = _load_permission_long(run_root, run_id)
    pi_map, danger_map = _load_audit_lane_maps(run_root)
    tokens = sorted(set(permission_long["permission_name"].tolist()))
    inventory = build_permission_capability_inventory(tokens, pi_bucket_source=pi_map, dangerous_bucket=danger_map)
    sample_matrix = build_sample_category_matrix(labels, permission_long)

    by_type = _prevalence_rows_for_group(sample_matrix, group_col="type_slug", min_samples=min_samples)
    # Global (all samples) family/package-balanced headline rows
    global_rows = []
    for cat in CANONICAL_CAPABILITY_CATEGORIES:
        global_rows.append(
            {
                "scope": "all_samples",
                "capability_category": cat,
                "sample_count": len(sample_matrix),
                "positive_sample_count": int(sample_matrix[cat].sum()),
                "sample_weighted_prevalence": sample_weighted_prevalence(sample_matrix, cat),
                "family_balanced_prevalence": family_balanced_prevalence(sample_matrix, cat),
                "package_balanced_prevalence": package_balanced_prevalence(sample_matrix, cat),
            }
        )
    global_prev = pd.DataFrame(global_rows)
    lane_prev = build_category_by_protection_lane(inventory, permission_long)
    cooccur = build_category_cooccurrence(sample_matrix, min_samples=min_samples)
    dominant = build_dominant_family_category_sensitivity(sample_matrix)

    unmapped = inventory[inventory["capability_category"] == "app_defined_unknown"].copy()
    unmapped_diag = (
        unmapped.groupby(["permission_name", "protection_lane", "mapping_kind"], as_index=False)
        .size()
        .rename(columns={"size": "inventory_rows"})
        .sort_values("permission_name")
    )

    write_csv(out_dir / "permission_capability_inventory.csv", inventory)
    write_csv(out_dir / "category_prevalence_by_type.csv", by_type)
    write_csv(out_dir / "category_prevalence_global_weightings.csv", global_prev)
    write_csv(out_dir / "category_prevalence_by_protection_lane.csv", lane_prev)
    write_csv(out_dir / "category_cooccurrence_summary.csv", cooccur)
    write_csv(out_dir / "dominant_family_category_sensitivity.csv", dominant)
    write_csv(out_dir / "unknown_unmapped_category_diagnostics.csv", unmapped_diag)
    write_csv(
        out_dir / "sample_capability_matrix.csv",
        sample_matrix[["sample_id", "type_slug", "family_canonical", *CANONICAL_CAPABILITY_CATEGORIES]],
    )

    # Figures
    fig_dir = out_dir / "figures"
    sw_mat = _pivot_prevalence(by_type, "type_slug", "sample_weighted_prevalence")
    fb_mat = _pivot_prevalence(by_type, "type_slug", "family_balanced_prevalence")
    pb_mat = _pivot_prevalence(by_type, "type_slug", "package_balanced_prevalence")
    _write_heatmap(
        sw_mat,
        out_path=fig_dir / "type_by_capability_sample_weighted.png",
        title="Type × capability (sample-weighted)",
        xlabel="capability_category",
        ylabel="type_slug",
        run_id=run_id,
        weighting="sample_weighted",
        denominator=len(sample_matrix),
        date_semantics="not_temporal",
    )
    _write_heatmap(
        fb_mat,
        out_path=fig_dir / "type_by_capability_family_balanced.png",
        title="Type × capability (family-balanced)",
        xlabel="capability_category",
        ylabel="type_slug",
        run_id=run_id,
        weighting="family_balanced",
        denominator=len(sample_matrix),
        date_semantics="not_temporal",
    )
    _write_heatmap(
        pb_mat,
        out_path=fig_dir / "type_by_capability_package_balanced.png",
        title="Type × capability (package-balanced)",
        xlabel="capability_category",
        ylabel="type_slug",
        run_id=run_id,
        weighting="package_balanced",
        denominator=int((~sample_matrix["is_missing_package"]).sum()),
        date_semantics="not_temporal",
    )
    # Sample vs family-balanced delta for main types
    compare_rows = []
    for _, row in by_type.iterrows():
        if row["support_suppressed"]:
            continue
        compare_rows.append(
            {
                "type_slug": row["type_slug"],
                "capability_category": row["capability_category"],
                "sample_weighted_prevalence": row["sample_weighted_prevalence"],
                "family_balanced_prevalence": row["family_balanced_prevalence"],
                "delta_pp": (
                    (float(row["family_balanced_prevalence"]) - float(row["sample_weighted_prevalence"])) * 100.0
                    if pd.notna(row["family_balanced_prevalence"]) and pd.notna(row["sample_weighted_prevalence"])
                    else float("nan")
                ),
            }
        )
    compare = pd.DataFrame(compare_rows)
    write_csv(out_dir / "sample_vs_family_balanced_comparison.csv", compare)
    if not compare.empty:
        delta_mat = compare.pivot_table(
            index="type_slug", columns="capability_category", values="delta_pp", aggfunc="first"
        )
        # rescale to 0-1 for display of absolute? keep raw signed via diverging — use clipped abs for simple viridis
        _write_heatmap(
            (delta_mat.abs() / 100.0).clip(0, 1),
            out_path=fig_dir / "sample_vs_family_balanced_abs_delta.png",
            title="|family-balanced − sample-weighted| (fraction)",
            xlabel="capability_category",
            ylabel="type_slug",
            run_id=run_id,
            weighting="abs_delta_pp/100",
            denominator=len(sample_matrix),
            date_semantics="not_temporal",
        )

    # Co-occurrence matrix figure
    if not cooccur.empty:
        jac = cooccur.pivot_table(index="category_a", columns="category_b", values="jaccard", aggfunc="first")
        # symmetrize for display
        jac = jac.reindex(index=list(CANONICAL_CAPABILITY_CATEGORIES), columns=list(CANONICAL_CAPABILITY_CATEGORIES))
        for a in CANONICAL_CAPABILITY_CATEGORIES:
            for b in CANONICAL_CAPABILITY_CATEGORIES:
                if pd.isna(jac.loc[a, b]) and pd.notna(jac.loc[b, a]):
                    jac.loc[a, b] = jac.loc[b, a]
        _write_heatmap(
            jac.fillna(0.0),
            out_path=fig_dir / "capability_category_cooccurrence_jaccard.png",
            title="Capability co-occurrence (Jaccard)",
            xlabel="category_b",
            ylabel="category_a",
            run_id=run_id,
            weighting="jaccard_on_samples",
            denominator=len(sample_matrix),
            date_semantics="not_temporal",
        )

    # Dominant-family sensitivity plot (mean |delta_pp| by type)
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        sens = dominant[~dominant["support_suppressed"]].copy()
        if not sens.empty:
            summary = sens.groupby("type_slug")["delta_pp"].apply(lambda s: float(np.nanmean(np.abs(s)))).sort_values(ascending=False)
            fig, ax = plt.subplots(figsize=(8, 4))
            summary.plot(kind="bar", ax=ax, color="#2a6f97")
            ax.set_ylabel("mean |delta_pp|")
            ax.set_title("Dominant-family category sensitivity")
            fig.text(0.01, 0.01, f"run={run_id}; n_types={len(summary)}; static declarations only", fontsize=7)
            fig.savefig(fig_dir / "dominant_family_category_sensitivity.png", bbox_inches="tight", dpi=140)
            plt.close(fig)
    except ImportError:
        pass

    artifact_paths = sorted(p for p in out_dir.rglob("*") if p.is_file())
    checksums = {str(p.relative_to(out_dir)): sha256_file(p) for p in artifact_paths}
    manifest = {
        **capability_category_contract_metadata(),
        "run_id": run_id,
        "run_root": str(run_root),
        "output_dir": str(out_dir),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": resolve_git_commit(repo_root),
        "sample_count": int(len(sample_matrix)),
        "permission_observation_count": int(len(permission_long)),
        "distinct_permission_tokens": int(len(tokens)),
        "min_samples": min_samples,
        "checksums": checksums,
        "disclaimer": (
            "Offline static-declaration analysis only. Does not query databases or Core. "
            "Does not infer runtime permission use."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # refresh checksum for manifest itself
    manifest["checksums"]["manifest.json"] = sha256_file(out_dir / "manifest.json")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


__all__ = [
    "CANONICAL_CAPABILITY_CATEGORIES",
    "CAPABILITY_CATEGORY_CONTRACT_VERSION",
    "EXPLICIT_PERMISSION_CAPABILITY_MAP",
    "build_permission_capability_inventory",
    "build_sample_category_matrix",
    "capability_category_contract_metadata",
    "classify_capability_categories",
    "compose_permission_capability_category_report",
    "normalize_permission_token",
]
