"""Seed stable Android permission signal catalog + mappings conservatively."""

from __future__ import annotations

from typing import Any

from obsidiandroid.database import db_engine


SIGNAL_CATALOG_ROWS: list[dict[str, Any]] = [
    {
        "signal_key": "sms",
        "display_name": "SMS",
        "description": "SMS and MMS messaging permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Declared messaging capability; candidate-only for later ATT&CK mapping.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "contacts_accounts",
        "display_name": "Contacts / Accounts",
        "description": "Address book and general account-surface permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Treat as declared data-access capability, not runtime proof.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "phone_call_state",
        "display_name": "Phone / Call State",
        "description": "Telephony, call-log, and call-state permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Useful for banker/RAT/spyware capability interpretation.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "accessibility",
        "display_name": "Accessibility",
        "description": "Accessibility-service binding permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "High-value declared capability; still candidate-only for ATT&CK use.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "overlay_window",
        "display_name": "Overlay / Window",
        "description": "Overlay, draw-over, and special window permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Candidate behavior area only; do not infer runtime abuse directly.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "location",
        "display_name": "Location",
        "description": "Foreground and background location permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Candidate-only mapping to location-tracking style behavior areas.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "camera_microphone",
        "display_name": "Camera / Microphone",
        "description": "Camera and audio capture permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Static declared sensor/media capture capability.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "storage_media",
        "display_name": "Storage / Media",
        "description": "External storage and media library access permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Can support exfiltration/storage hypotheses, but only at candidate level.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "network_connectivity",
        "display_name": "Network / Connectivity",
        "description": "Internet and network-state permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "general_capability_supporting_signal",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Very common; usable in reports but weak on its own.",
        "default_weight": 0.500,
    },
    {
        "signal_key": "foreground_service",
        "display_name": "Foreground Service",
        "description": "Foreground service permissions and related variants.",
        "authority_lane": "supporting_capability",
        "default_malware_capability_posture": "supporting_signal_not_behavioral_claim_primary",
        "include_in_model_features": True,
        "include_in_behavioral_claims": False,
        "mitre_candidate_only": True,
        "notes": "Operational persistence/execution support; not a strong behavior claim alone.",
        "default_weight": 0.500,
    },
    {
        "signal_key": "package_visibility",
        "display_name": "Package / Query Visibility",
        "description": "Permissions related to package enumeration and installed-app visibility.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Useful for software-discovery style candidate interpretation.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "notification_access",
        "display_name": "Notification Access",
        "description": "Notification listener and notification control permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Candidate notification-monitoring/control signal.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "device_admin",
        "display_name": "Device Admin",
        "description": "Device administrator binding or administration permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Strong declared administrative capability signal.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "account_credentials",
        "display_name": "Account / Credentials",
        "description": "Credential, authenticator, and account-management permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Candidate credential-access signal only.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "bluetooth_nearby_devices",
        "display_name": "Bluetooth / Nearby Devices",
        "description": "Bluetooth and nearby-device permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Candidate local-connectivity capability signal.",
        "default_weight": 0.750,
    },
    {
        "signal_key": "calendar",
        "display_name": "Calendar",
        "description": "Calendar read/write permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Declared calendar data-access capability.",
        "default_weight": 0.750,
    },
    {
        "signal_key": "install_update_package",
        "display_name": "Install / Update Package",
        "description": "Package install, delete, and update permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Candidate dropper/update capability area.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "system_settings",
        "display_name": "System Settings",
        "description": "Write/manage settings and closely related system control permissions.",
        "authority_lane": "behavior_safe_capability",
        "default_malware_capability_posture": "candidate_behavior_area_only",
        "include_in_model_features": True,
        "include_in_behavioral_claims": True,
        "mitre_candidate_only": True,
        "notes": "Strong system-control signal, but still static declared capability.",
        "default_weight": 1.000,
    },
    {
        "signal_key": "aosp_hidden_privileged",
        "display_name": "AOSP Hidden / Privileged",
        "description": "Hidden, platform, and privileged AOSP permission surface.",
        "authority_lane": "aosp_hidden_privileged",
        "default_malware_capability_posture": "review_before_behavioral_claims",
        "include_in_model_features": True,
        "include_in_behavioral_claims": False,
        "mitre_candidate_only": True,
        "notes": "Do not treat as behavioral claim-safe until metadata/backfill review is complete.",
        "default_weight": 0.750,
    },
    {
        "signal_key": "oem_vendor_ecosystem",
        "display_name": "OEM / Vendor Ecosystem",
        "description": "OEM and vendor namespace permissions.",
        "authority_lane": "oem_vendor_ecosystem",
        "default_malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": True,
        "include_in_behavioral_claims": False,
        "mitre_candidate_only": True,
        "notes": "Keep available for clustering/fingerprinting, not behavior claims.",
        "default_weight": 0.500,
    },
    {
        "signal_key": "google_gms_ecosystem",
        "display_name": "Google / GMS Ecosystem",
        "description": "Google Play services and GMS-defined permission surface.",
        "authority_lane": "google_service_ecosystem",
        "default_malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": True,
        "include_in_behavioral_claims": False,
        "mitre_candidate_only": True,
        "notes": "Keep separate from AOSP and app-defined custom permissions.",
        "default_weight": 0.500,
    },
    {
        "signal_key": "app_defined_scaffolding",
        "display_name": "App-Defined Scaffolding",
        "description": "Legacy push, AndroidX guard, ADM, AppHub, and similar app scaffolding permissions.",
        "authority_lane": "app_scaffolding",
        "default_malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": True,
        "include_in_behavioral_claims": False,
        "mitre_candidate_only": True,
        "notes": "Useful for fingerprinting/clustering, not malware capability evidence.",
        "default_weight": 0.500,
    },
    {
        "signal_key": "launcher_sdk_ecosystem_noise",
        "display_name": "Launcher / SDK Ecosystem Noise",
        "description": "Launcher badge, shortcut, and SDK ecosystem permissions.",
        "authority_lane": "ecosystem_noise",
        "default_malware_capability_posture": "exclude_from_malware_capability_claims",
        "include_in_model_features": True,
        "include_in_behavioral_claims": False,
        "mitre_candidate_only": True,
        "notes": "Fingerprinting-only lane; not suitable for behavior claims.",
        "default_weight": 0.250,
    },
]


SIGNAL_MAPPING_ROWS: list[dict[str, Any]] = [
    # Behavioral capability signals
    {"signal_key": "sms", "perm_name": "android.permission.read_sms", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "messaging_access", "mitre_candidate_tactic": "collection", "notes": "Exact SMS read permission."},
    {"signal_key": "sms", "perm_name": "android.permission.receive_sms", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "messaging_access", "mitre_candidate_tactic": "collection", "notes": "Exact SMS receive permission."},
    {"signal_key": "sms", "perm_name": "android.permission.send_sms", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "messaging_control", "mitre_candidate_tactic": "collection", "notes": "Exact SMS send permission."},
    {"signal_key": "sms", "perm_name": "android.permission.write_sms", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "messaging_control", "mitre_candidate_tactic": "collection", "notes": "Exact SMS write permission."},
    {"signal_key": "contacts_accounts", "perm_name": "android.permission.read_contacts", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "contact_access", "mitre_candidate_tactic": "collection", "notes": "Exact contacts read permission."},
    {"signal_key": "contacts_accounts", "perm_name": "android.permission.write_contacts", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "contact_access", "mitre_candidate_tactic": "collection", "notes": "Exact contacts write permission."},
    {"signal_key": "contacts_accounts", "perm_name": "android.permission.get_accounts", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "account_inventory", "mitre_candidate_tactic": "collection", "notes": "Legacy account access permission."},
    {"signal_key": "phone_call_state", "perm_name": "android.permission.read_phone_state", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "telephony_state", "mitre_candidate_tactic": "collection", "notes": "Exact phone-state permission."},
    {"signal_key": "phone_call_state", "perm_name": "android.permission.read_call_log", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "call_log_access", "mitre_candidate_tactic": "collection", "notes": "Exact call log read permission."},
    {"signal_key": "phone_call_state", "perm_name": "android.permission.write_call_log", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "call_log_access", "mitre_candidate_tactic": "collection", "notes": "Exact call log write permission."},
    {"signal_key": "phone_call_state", "perm_name": "android.permission.process_outgoing_calls", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "call_control", "mitre_candidate_tactic": "collection", "notes": "Outgoing call processing signal."},
    {"signal_key": "accessibility", "perm_name": "android.permission.bind_accessibility_service", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "accessibility_control", "mitre_candidate_tactic": "privilege-escalation", "notes": "Accessibility binding permission."},
    {"signal_key": "overlay_window", "perm_name": "android.permission.system_alert_window", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "overlay_control", "mitre_candidate_tactic": "credential-access", "notes": "Overlay window permission."},
    {"signal_key": "location", "perm_name": "android.permission.access_fine_location", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "location_access", "mitre_candidate_tactic": "collection", "notes": "Fine location permission."},
    {"signal_key": "location", "perm_name": "android.permission.access_coarse_location", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "location_access", "mitre_candidate_tactic": "collection", "notes": "Coarse location permission."},
    {"signal_key": "location", "perm_name": "android.permission.access_background_location", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "background_location_access", "mitre_candidate_tactic": "collection", "notes": "Background location permission."},
    {"signal_key": "camera_microphone", "perm_name": "android.permission.camera", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "camera_access", "mitre_candidate_tactic": "collection", "notes": "Camera permission."},
    {"signal_key": "camera_microphone", "perm_name": "android.permission.record_audio", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "audio_capture", "mitre_candidate_tactic": "collection", "notes": "Audio record permission."},
    {"signal_key": "storage_media", "perm_name": "android.permission.read_external_storage", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "external_storage_access", "mitre_candidate_tactic": "collection", "notes": "External storage read permission."},
    {"signal_key": "storage_media", "perm_name": "android.permission.write_external_storage", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "external_storage_access", "mitre_candidate_tactic": "collection", "notes": "External storage write permission."},
    {"signal_key": "storage_media", "perm_name": "android.permission.read_media_images", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "media_access", "mitre_candidate_tactic": "collection", "notes": "Media images permission."},
    {"signal_key": "storage_media", "perm_name": "android.permission.read_media_video", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "media_access", "mitre_candidate_tactic": "collection", "notes": "Media video permission."},
    {"signal_key": "network_connectivity", "perm_name": "android.permission.internet", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "network_access", "mitre_candidate_tactic": "command-and-control", "notes": "Internet permission."},
    {"signal_key": "network_connectivity", "perm_name": "android.permission.access_network_state", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "network_access", "mitre_candidate_tactic": "command-and-control", "notes": "Network-state permission."},
    {"signal_key": "network_connectivity", "perm_name": "android.permission.access_wifi_state", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "network_access", "mitre_candidate_tactic": "command-and-control", "notes": "Wi-Fi state permission."},
    {"signal_key": "foreground_service", "perm_name": "android.permission.foreground_service", "namespace": "android.permission", "mapping_basis": "prefix_pattern", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "foreground_execution_support", "mitre_candidate_tactic": "execution", "notes": "Prefix match for foreground service family."},
    {"signal_key": "package_visibility", "perm_name": "android.permission.query_all_packages", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "package_inventory", "mitre_candidate_tactic": "discovery", "notes": "Package visibility permission."},
    {"signal_key": "notification_access", "perm_name": "android.permission.bind_notification_listener_service", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "notification_access", "mitre_candidate_tactic": "collection", "notes": "Notification listener permission."},
    {"signal_key": "notification_access", "perm_name": "android.permission.post_notifications", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "notification_access", "mitre_candidate_tactic": "collection", "notes": "Notification posting permission."},
    {"signal_key": "device_admin", "perm_name": "android.permission.bind_device_admin", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "device_admin_control", "mitre_candidate_tactic": "persistence", "notes": "Device admin binding permission."},
    {"signal_key": "account_credentials", "perm_name": "android.permission.manage_accounts", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "account_management", "mitre_candidate_tactic": "credential-access", "notes": "Manage accounts permission."},
    {"signal_key": "account_credentials", "perm_name": "android.permission.use_credentials", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "credential_use", "mitre_candidate_tactic": "credential-access", "notes": "Use credentials permission."},
    {"signal_key": "account_credentials", "perm_name": "android.permission.authenticate_accounts", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "credential_use", "mitre_candidate_tactic": "credential-access", "notes": "Authenticate accounts permission."},
    {"signal_key": "bluetooth_nearby_devices", "perm_name": "android.permission.bluetooth_connect", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "nearby_device_access", "mitre_candidate_tactic": "collection", "notes": "Bluetooth connect permission."},
    {"signal_key": "bluetooth_nearby_devices", "perm_name": "android.permission.bluetooth_scan", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "nearby_device_access", "mitre_candidate_tactic": "discovery", "notes": "Bluetooth scan permission."},
    {"signal_key": "bluetooth_nearby_devices", "perm_name": "android.permission.nearby_wifi_devices", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "nearby_device_access", "mitre_candidate_tactic": "discovery", "notes": "Nearby Wi-Fi devices permission."},
    {"signal_key": "calendar", "perm_name": "android.permission.read_calendar", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "calendar_access", "mitre_candidate_tactic": "collection", "notes": "Read calendar permission."},
    {"signal_key": "calendar", "perm_name": "android.permission.write_calendar", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "calendar_access", "mitre_candidate_tactic": "collection", "notes": "Write calendar permission."},
    {"signal_key": "install_update_package", "perm_name": "android.permission.request_install_packages", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "package_installation", "mitre_candidate_tactic": "execution", "notes": "Request install packages permission."},
    {"signal_key": "install_update_package", "perm_name": "android.permission.request_delete_packages", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "package_installation", "mitre_candidate_tactic": "execution", "notes": "Delete packages permission."},
    {"signal_key": "install_update_package", "perm_name": "android.permission.install_package_updates", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "package_installation", "mitre_candidate_tactic": "execution", "notes": "Install package updates permission."},
    {"signal_key": "system_settings", "perm_name": "android.permission.write_settings", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "settings_control", "mitre_candidate_tactic": "defense-evasion", "notes": "Write settings permission."},
    {"signal_key": "system_settings", "perm_name": "android.permission.write_secure_settings", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "high", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "settings_control", "mitre_candidate_tactic": "defense-evasion", "notes": "Write secure settings permission."},
    {"signal_key": "system_settings", "perm_name": "android.permission.request_ignore_battery_optimizations", "namespace": "android.permission", "mapping_basis": "exact_permission", "confidence": "medium", "source_family_key": None, "include_in_model_features": True, "include_in_behavioral_claims": True, "candidate_behavior_area": "settings_control", "mitre_candidate_tactic": "persistence", "notes": "Battery optimization bypass request."},
    # Candidate-only ecosystem/scaffolding lanes
    {"signal_key": "oem_vendor_ecosystem", "perm_name": "oem_vendor_permission", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "oem_vendor_permission", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "vendor_ecosystem_noise", "mitre_candidate_tactic": None, "notes": "Route all OEM/vendor namespace remediation-lane tokens here."},
    {"signal_key": "google_gms_ecosystem", "perm_name": "google_service_permission", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "google_service_permission", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "google_service_ecosystem", "mitre_candidate_tactic": None, "notes": "Route GMS/Google service ecosystem tokens here."},
    {"signal_key": "app_defined_scaffolding", "perm_name": "app_defined_legacy_push_permission", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "app_defined_legacy_push_permission", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "app_scaffolding", "mitre_candidate_tactic": None, "notes": "Legacy push scaffolding lane."},
    {"signal_key": "app_defined_scaffolding", "perm_name": "app_defined_dynamic_receiver_guard", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "app_defined_dynamic_receiver_guard", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "app_scaffolding", "mitre_candidate_tactic": None, "notes": "AndroidX dynamic receiver guard lane."},
    {"signal_key": "app_defined_scaffolding", "perm_name": "app_defined_maps_receive_permission", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "app_defined_maps_receive_permission", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "app_scaffolding", "mitre_candidate_tactic": None, "notes": "Legacy maps receive scaffolding lane."},
    {"signal_key": "app_defined_scaffolding", "perm_name": "app_defined_adm_permission", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "app_defined_adm_permission", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "app_scaffolding", "mitre_candidate_tactic": None, "notes": "Amazon Device Messaging scaffolding lane."},
    {"signal_key": "app_defined_scaffolding", "perm_name": "app_defined_apphub_permission", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "app_defined_apphub_permission", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "app_scaffolding", "mitre_candidate_tactic": None, "notes": "AppHub binding scaffolding lane."},
    {"signal_key": "launcher_sdk_ecosystem_noise", "perm_name": "third_party_sdk_or_launcher", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "third_party_sdk_or_launcher", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "launcher_sdk_noise", "mitre_candidate_tactic": None, "notes": "Launcher/badge ecosystem lane."},
    {"signal_key": "launcher_sdk_ecosystem_noise", "perm_name": "third_party_push_sdk_permission", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "high", "source_family_key": "third_party_push_sdk_permission", "include_in_model_features": True, "include_in_behavioral_claims": False, "candidate_behavior_area": "launcher_sdk_noise", "mitre_candidate_tactic": None, "notes": "Third-party push SDK scaffolding lane."},
    {"signal_key": "aosp_hidden_privileged", "perm_name": "needs_source_validation", "namespace": "remediation_lane", "mapping_basis": "remediation_lane", "confidence": "medium", "source_family_key": "needs_source_validation", "include_in_model_features": False, "include_in_behavioral_claims": False, "candidate_behavior_area": "aosp_hidden_privileged_review", "mitre_candidate_tactic": None, "notes": "Do not use for behavior claims until source validation completes."},
]


def seed_permission_signal_catalog_and_mappings() -> dict[str, int]:
    """Upsert conservative signal catalog rows and mappings into Permission Intel."""
    catalog_insert = """
        INSERT INTO permission_signal_catalog (
            signal_key,
            display_name,
            description,
            authority_lane,
            default_malware_capability_posture,
            include_in_model_features,
            include_in_behavioral_claims,
            mitre_candidate_only,
            notes,
            default_weight
        ) VALUES (
            %(signal_key)s,
            %(display_name)s,
            %(description)s,
            %(authority_lane)s,
            %(default_malware_capability_posture)s,
            %(include_in_model_features)s,
            %(include_in_behavioral_claims)s,
            %(mitre_candidate_only)s,
            %(notes)s,
            %(default_weight)s
        )
        ON DUPLICATE KEY UPDATE
            display_name = VALUES(display_name),
            description = VALUES(description),
            authority_lane = VALUES(authority_lane),
            default_malware_capability_posture = VALUES(default_malware_capability_posture),
            include_in_model_features = VALUES(include_in_model_features),
            include_in_behavioral_claims = VALUES(include_in_behavioral_claims),
            mitre_candidate_only = VALUES(mitre_candidate_only),
            notes = VALUES(notes),
            default_weight = VALUES(default_weight)
    """
    mapping_insert = """
        INSERT INTO permission_signal_mappings (
            signal_key,
            perm_name,
            namespace,
            mapping_basis,
            source_family_key,
            include_in_model_features,
            include_in_behavioral_claims,
            candidate_behavior_area,
            mitre_candidate_tactic,
            confidence,
            notes
        ) VALUES (
            %(signal_key)s,
            %(perm_name)s,
            %(namespace)s,
            %(mapping_basis)s,
            %(source_family_key)s,
            %(include_in_model_features)s,
            %(include_in_behavioral_claims)s,
            %(candidate_behavior_area)s,
            %(mitre_candidate_tactic)s,
            %(confidence)s,
            %(notes)s
        )
        ON DUPLICATE KEY UPDATE
            mapping_basis = VALUES(mapping_basis),
            source_family_key = VALUES(source_family_key),
            include_in_model_features = VALUES(include_in_model_features),
            include_in_behavioral_claims = VALUES(include_in_behavioral_claims),
            candidate_behavior_area = VALUES(candidate_behavior_area),
            mitre_candidate_tactic = VALUES(mitre_candidate_tactic),
            confidence = VALUES(confidence),
            notes = VALUES(notes)
    """
    with db_engine.permission_intel_database_connection() as conn:
        cur = conn.cursor()
        for row in SIGNAL_CATALOG_ROWS:
            cur.execute(catalog_insert, row)
        for row in SIGNAL_MAPPING_ROWS:
            cur.execute(mapping_insert, row)
        conn.commit()
    return {
        "signal_catalog_rows": len(SIGNAL_CATALOG_ROWS),
        "signal_mapping_rows": len(SIGNAL_MAPPING_ROWS),
    }


def load_permission_signal_catalog_rows() -> list[dict[str, Any]]:
    """Load signal catalog rows from Permission Intel, falling back to bundled seed rows."""
    query = """
        SELECT
            signal_key,
            display_name,
            description,
            authority_lane,
            default_malware_capability_posture,
            include_in_model_features,
            include_in_behavioral_claims,
            mitre_candidate_only,
            notes,
            default_weight
        FROM permission_signal_catalog
        ORDER BY signal_key
    """
    try:
        frame = db_engine.execute_permission_query(query, fetch=True, as_dataframe=True)
    except Exception:
        return [dict(row) for row in SIGNAL_CATALOG_ROWS]
    if frame is None or frame.empty:
        return [dict(row) for row in SIGNAL_CATALOG_ROWS]
    return frame.to_dict(orient="records")


def load_permission_signal_mapping_rows() -> list[dict[str, Any]]:
    """Load signal mappings from Permission Intel, falling back to bundled seed rows."""
    query = """
        SELECT
            signal_key,
            perm_name,
            namespace,
            mapping_basis,
            source_family_key,
            include_in_model_features,
            include_in_behavioral_claims,
            candidate_behavior_area,
            mitre_candidate_tactic,
            confidence,
            notes
        FROM permission_signal_mappings
        ORDER BY signal_key, mapping_basis, perm_name
    """
    try:
        frame = db_engine.execute_permission_query(query, fetch=True, as_dataframe=True)
    except Exception:
        return [dict(row) for row in SIGNAL_MAPPING_ROWS]
    if frame is None or frame.empty:
        return [dict(row) for row in SIGNAL_MAPPING_ROWS]
    return frame.to_dict(orient="records")


__all__ = [
    "SIGNAL_CATALOG_ROWS",
    "SIGNAL_MAPPING_ROWS",
    "load_permission_signal_catalog_rows",
    "load_permission_signal_mapping_rows",
    "seed_permission_signal_catalog_and_mappings",
]
