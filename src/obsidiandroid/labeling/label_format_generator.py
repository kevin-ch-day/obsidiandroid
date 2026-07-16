# Filename: src/obsidiandroid/labeling/label_format_generator.py
# Purpose  : Generate structured, canonical, enriched labels for malware classification records

import re
from obsidiandroid.vendors import VendorClassificationRecord
from . import label_field_normalizer
from obsidiandroid.labeling import malware_family_constants


def sanitize_variant(variant: str, family: str) -> str:
    """
    Sanitizes and filters variant names to exclude meaningless or redundant values.
    """
    if not variant or variant.lower() in {"unknown", "none", "generic", "variant", "var"}:
        return ""

    variant = variant.strip().lower()
    family = family.strip().lower()

    # Remove redundant family prefix
    if variant.startswith(family):
        variant = variant[len(family):].lstrip(".-_")

    if len(variant) < 2 or not re.match(r"^[a-z0-9]{2,}$", variant):
        return ""

    if any(known in variant for known in malware_family_constants.KNOWN_FAMILIES if known != family):
        return ""

    return variant


def generate_structured_label(fields: dict) -> str:
    """
    Generates a label in the format: type/platform[.threat_class].family[variant]
    """
    try:
        mtype = fields.get("mtype", "unknown")
        platform = fields.get("platform", "unknown")
        family = fields.get("family", "unknown")
        threat = fields.get("threat", "")
        variant = sanitize_variant(fields.get("variant", ""), family)

        base = f"{mtype}/{platform}"
        if (
            threat
            and threat.lower() != "unknown"
            and threat.lower() not in family.lower()
        ):
            base += f".{threat}"
        base += f".{family}"

        if variant:
            base += f"[{variant}]"

        return base
    except Exception:
        return "unknown/unknown.unknown"


def generate_compact_label(fields: dict) -> str:
    """
    Generates a compact label: family or fallback to platform_threat.
    """
    family = fields.get("family")
    platform = fields.get("platform", "unknown")
    threat = fields.get("threat", "unknown")
    return family if family else f"{platform}_{threat}"


def generate_tag_label(fields: dict) -> str:
    """
    Generates a semicolon-delimited tag label.
    """
    tags = [
        f"family:{fields.get('family')}",
        f"type:{fields.get('mtype')}",
        f"platform:{fields.get('platform')}",
        f"threat:{fields.get('threat')}"
    ]

    if fields.get("variant") and fields["variant"].lower() != "unknown":
        tags.append(f"variant:{fields['variant']}")
    if fields.get("is_known_family"):
        tags.append("known_family")
    if fields.get("override_source"):
        tags.append(f"override:{fields['override_source']}")

    return ";".join(tags)


def generate_vector_label(fields: dict) -> str:
    """
    Returns vector-based label as semicolon-separated string.
    """
    return ";".join(fields.get("vector", []))


def generate_enriched_label(fields: dict) -> str:
    """
    Generates a verbose, enriched label format: Type.Platform.Threat.Family[Variant].tags
    """
    mtype = fields.get("mtype", "unknown").capitalize()
    platform = fields.get("platform", "unknown")
    threat = fields.get("threat", "unknown")
    family = fields.get("family", "unknown")
    variant = sanitize_variant(fields.get("variant", ""), family)

    family_str = f"{family}[{variant}]" if variant and variant not in family else family
    enriched_parts = [mtype, platform, threat, family_str]

    if "tags" in fields:
        enriched_parts.extend(fields["tags"])

    return ".".join(enriched_parts)


def generate_label(
    recorded_family: str,
    record: VendorClassificationRecord,
    format: str = "structured",
    verbose: bool = False,
    structured_fields: dict | None = None,
) -> str:
    """
    Dispatches label formatting based on specified format.
    """
    fields = structured_fields or label_field_normalizer.generate_structured_fields(
        recorded_family, record, debug=verbose
    )

    format_map = {
        "structured": generate_structured_label,
        "compact": generate_compact_label,
        "tags": generate_tag_label,
        "vector": generate_vector_label,
        "enriched": generate_enriched_label
    }

    label_func = format_map.get(format, generate_structured_label)
    label = label_func(fields)

    if verbose:
        print(f"[LABEL OUTPUT] Format: {format}, Label: {label}")

    return label


def debug_classification_label(record: VendorClassificationRecord, format: str = "structured") -> None:
    """
    Debug utility to print full label formatting breakdown.
    """
    print("\n[LABEL DEBUG] Inspecting Label Inference")
    label = generate_label(record.family, record, format=format, verbose=True)
    print(f"[LABEL DEBUG] Generated Label: {label}\n")
