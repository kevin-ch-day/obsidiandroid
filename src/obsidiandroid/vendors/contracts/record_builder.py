# Filename: model/vendor/record_builder.py
# Description: Record builder and validation logic for AV vendor classification records

from typing import List, Dict
from .record_core import VendorClassificationRecord
from .parsed_label_metadata import ParsedLabelMetadata
from .metadata_normalizer import ParsedMetadataNormalizer as Norm
from obsidiandroid.cli.ui import display as du


class VendorRecordBuilder:
    @staticmethod
    def from_metadata(sample_id: str, vendor_name: str, original_label: str,
                      metadata: ParsedLabelMetadata, known_family: str = "",
                      debug: bool = False) -> VendorClassificationRecord:
        if debug:
            du.print_section(f"[BUILD] {vendor_name} :: Building Record for Sample {sample_id}")
            du.print_debug(f"Original Label        : {original_label}")
            du.print_debug(f"Parsed Metadata Type  : {type(metadata).__name__}")
            du.print_debug(f"→ family              : {metadata.family}")
            du.print_debug(f"→ malware_type        : {metadata.malware_type}")
            du.print_debug(f"→ threat_class        : {metadata.threat_class}")
            du.print_debug(f"→ platform            : {metadata.platform}")
            du.print_debug(f"→ variant             : {metadata.variant}")
            du.print_debug(f"→ confidence          : {metadata.confidence}")
            du.print_debug(f"→ parser_quality      : {metadata.parser_quality}")
            du.print_debug(f"→ signature_type      : {metadata.signature_type}")

        # Normalize fields
        normalized_family = Norm.normalize_field(metadata.family)
        normalized_type = Norm.normalize_field(metadata.malware_type, "trojan")
        normalized_threat = Norm.normalize_field(metadata.threat_class, "generic")
        normalized_platform = Norm.normalize_field(metadata.platform, "android")
        normalized_variant = Norm.determine_variant(metadata.variant, original_label, normalized_family)

        # Validation & scoring
        match_known = (normalized_family == Norm.normalize_field(known_family)) if known_family else False
        is_generic = Norm.is_generic_family(normalized_family)
        is_weak = Norm.is_low_quality_parser(metadata.parser_quality)

        if hasattr(Norm.adjust_confidence_score, '__code__') and Norm.adjust_confidence_score.__code__.co_argcount == 4:
            adjusted_conf = Norm.adjust_confidence_score(metadata.confidence, is_generic, is_weak)
            reason = "generic_or_weak" if is_generic or is_weak else "none"
        else:
            adjusted_conf, reason = Norm.adjust_confidence_score(metadata.confidence, is_generic, is_weak, return_reason=True)

        # Construct record
        record = VendorClassificationRecord(
            sample_id=sample_id,
            vendor_name=vendor_name,
            original_label=original_label,
            family=normalized_family,
            malware_type=normalized_type,
            threat_class=normalized_threat,
            platform=normalized_platform,
            variant=normalized_variant,
            is_known_family=match_known,
            is_generic_family=metadata.is_generic_family or is_generic,
            confidence_score=adjusted_conf,
            parser_quality=Norm.normalize_field(metadata.parser_quality, "unknown"),
            signature_type=Norm.normalize_field(metadata.signature_type, "pattern")
        )
        record.confidence_reason = reason

        if debug:
            du.print_debug("[RESULT] Final Record")
            du.print_debug(f"→ family              : {record.family}")
            du.print_debug(f"→ malware_type        : {record.malware_type}")
            du.print_debug(f"→ threat_class        : {record.threat_class}")
            du.print_debug(f"→ confidence_score    : {adjusted_conf} (Reason: {reason})")
            du.print_debug(f"→ is_known_family     : {match_known}")
            du.print_debug(f"→ is_generic_family   : {record.is_generic_family}")
            du.print_debug(f"→ variant             : {record.variant}")
            # Field type introspection
            if hasattr(metadata, "family_name_candidates"):
                du.print_debug(f"→ family_name_candidates type  : {type(metadata.family_name_candidates).__name__}")
            if hasattr(metadata, "threat_class_candidates"):
                du.print_debug(f"→ threat_class_candidates type : {type(metadata.threat_class_candidates).__name__}")
            if hasattr(metadata, "variant_candidates"):
                du.print_debug(f"→ variant_candidates type      : {type(metadata.variant_candidates).__name__}")

        return record

    @staticmethod
    def validate_batch(records: List[VendorClassificationRecord]) -> Dict[str, int]:
        stats = {"total": len(records), "complete": 0, "incomplete": 0, "unknown_family": 0}
        for rec in records:
            validity = rec.validate_record_completeness()
            if validity == "complete":
                stats["complete"] += 1
            else:
                stats["incomplete"] += 1
            if rec.family.strip().lower() == "unknown":
                stats["unknown_family"] += 1
        return stats
