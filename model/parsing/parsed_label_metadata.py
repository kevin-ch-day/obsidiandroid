# Filename: parsed_label_metadata.py
# Description: Structured metadata container for AV label parsing and classification.

from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class ParsedLabelMetadata:
    family: str
    malware_type: str
    threat_class: str
    platform: str
    variant: str

    confidence: float
    parser_quality: str
    signature_type: str

    ability: Optional[str] = None
    edge_case_type: Optional[str] = None

    is_generic_family: bool = field(init=False)
    is_android_target: bool = field(init=False)
    has_family: bool = field(init=False)
    is_valid: bool = field(init=False)

    CORE_FIELDS = {
        "family", "malware_type", "threat_class", "platform", "variant",
        "confidence", "parser_quality", "signature_type"
    }

    OPTIONAL_FIELDS = {"ability", "edge_case_type"}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParsedLabelMetadata":
        def clean_str(x, default="unknown"):
            return str(x).strip().lower() if isinstance(x, str) and x.strip() else default

        clean = {
            "family": clean_str(data.get("family")),
            "malware_type": clean_str(data.get("malware_type")),
            "threat_class": clean_str(data.get("threat_class")),
            "platform": clean_str(data.get("platform")),
            "variant": clean_str(data.get("variant")),
            "parser_quality": clean_str(data.get("parser_quality")),
            "signature_type": clean_str(data.get("signature_type")),
            "ability": clean_str(data.get("ability", ""), "") or None,
            "edge_case_type": clean_str(data.get("edge_case_type", ""), "") or None,
        }

        try:
            clean["confidence"] = float(data.get("confidence", 0.0)) or 0.0
        except (TypeError, ValueError):
            clean["confidence"] = 0.0

        return cls(**clean)

    def __post_init__(self):
        for attr in ["family", "malware_type", "threat_class", "platform", "variant", "parser_quality", "signature_type"]:
            setattr(self, attr, getattr(self, attr).strip().lower())

        self.is_generic_family = self.family in {"generic", "agent", "unknown"}
        self.is_android_target = self.platform == "android"
        self.has_family = self.family not in {"", "unknown", "generic"}
        self.is_valid = self.has_family and self.has_threat_class()

    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.7 and not self.is_generic_family

    def has_threat_class(self) -> bool:
        return self.threat_class not in {"", "unknown"}

    def is_structurally_complete(self) -> bool:
        return all([
            self.family not in {"", "unknown"},
            self.threat_class not in {"", "unknown"},
            self.platform not in {"", "unknown"},
            self.malware_type not in {"", "unknown"},
        ])

    def signal_score(self) -> float:
        penalty = 0.25 if self.is_generic_family else 0.0
        return round(max(0.0, self.confidence - penalty), 4)

    def summary(self) -> str:
        parts = [
            f"Family: {self.family}",
            f"Type: {self.malware_type}",
            f"Threat: {self.threat_class}",
            f"Platform: {self.platform}",
            f"Confidence: {self.confidence:.2f}",
            f"SigType: {self.signature_type}",
            f"ParserQ: {self.parser_quality}",
        ]
        if self.ability:
            parts.append(f"Ability: {self.ability}")
        if self.edge_case_type:
            parts.append(f"Edge: {self.edge_case_type}")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "malware_type": self.malware_type,
            "threat_class": self.threat_class,
            "platform": self.platform,
            "variant": self.variant,
            "confidence": self.confidence,
            "parser_quality": self.parser_quality,
            "signature_type": self.signature_type,
            "is_generic_family": self.is_generic_family,
            "is_android_target": self.is_android_target,
            "has_family": self.has_family,
            "is_valid": self.is_valid,
            "signal_score": self.signal_score(),
            **({"ability": self.ability} if self.ability else {}),
            **({"edge_case_type": self.edge_case_type} if self.edge_case_type else {})
        }

    def to_classification_kwargs(self) -> dict:
        return {
            "family": self.family,
            "malware_type": self.malware_type,
            "threat_class": self.threat_class,
            "platform": self.platform,
            "variant": self.variant,
            "is_generic_family": self.is_generic_family,
            "confidence_score": self.confidence,
            "parser_quality": self.parser_quality,
            "signature_type": self.signature_type,
            **({"ability": self.ability} if self.ability else {}),
            **({"edge_case_type": self.edge_case_type} if self.edge_case_type else {})
        }
