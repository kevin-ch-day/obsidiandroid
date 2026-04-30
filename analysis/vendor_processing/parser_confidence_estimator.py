# Filename: parser_confidence_estimator.py
# Description: Computes a confidence score for AV label parsing using structure, semantics, and metadata cues.

from typing import Optional, Dict, Tuple, Union
import math
import re

SIGMOID_SHARPNESS = 8.0
SIGMOID_CENTER = 0.5
MIN_SCORE = 0.0
MAX_SCORE = 1.0

ENABLE_EXPLANATION = False  # Global toggle for verbose diagnostics

def estimate_structure_score(label: str) -> float:
    if not isinstance(label, str) or not label.strip():
        return 0.35

    label = label.strip()
    colon = label.count(":")
    dash = label.count("-")
    has_brackets = bool(re.search(r"\[.*?\]", label))

    if colon and dash and has_brackets:
        return 0.97
    elif colon and dash:
        return 0.92
    elif colon:
        return 0.80
    elif dash:
        return 0.70
    return 0.55

def adjust_for_quality(score: float, quality: Optional[str]) -> Tuple[float, str]:
    q = str(quality or "").lower()
    delta = {
        "high": +0.04,
        "low": -0.08,
        "experimental": -0.12
    }.get(q, 0.0)
    return score + delta, f"quality={q} adj={delta:+.2f}"

def adjust_for_signature(score: float, sigtype: Optional[str]) -> Tuple[float, str]:
    st = str(sigtype or "").lower()
    delta = {
        "heuristic": -0.06,
        "generic": -0.05,
        "pattern": +0.01,
        "cloud": -0.02
    }.get(st, 0.0)
    return score + delta, f"signature={st} adj={delta:+.2f}"

def penalty_for_weak_family(family: str, variant: str = "") -> Tuple[float, str]:
    f = (family or "").strip().lower()
    v = (variant or "").strip().lower()

    penalty = 0.0
    reasons = []

    if not f or f in {"unknown", "generic", "test", "none"}:
        penalty -= 0.08
        reasons.append("unknown_family")
    elif len(f) <= 3:
        penalty -= 0.04
        reasons.append("short_family")
    elif f.startswith("mal") or f.endswith("gen"):
        penalty -= 0.05
        reasons.append("mal/gen_family")

    if v in {"a", "b", "c", "d", "e"}:
        penalty -= 0.02
        reasons.append("generic_variant")

    return penalty, f"family_penalty={penalty:+.2f} ({','.join(reasons) or 'none'})"

def bounded_sigmoid(score: float) -> float:
    x = (score - SIGMOID_CENTER) * SIGMOID_SHARPNESS
    return 1 / (1 + math.exp(-x))

def compute_confidence_score(
    label: str,
    parsed_result: Dict[str, str],
    metadata: Optional[Dict] = None,
    return_explanation: bool = False
) -> Union[float, Tuple[float, str]]:
    """
    Compute a normalized confidence score for parsed AV label data.
    Optionally returns an explanation string.
    """
    explanation = []

    # Prefer engine-provided confidence if present
    if metadata and "confidence_score" in metadata:
        preset = round(float(metadata["confidence_score"]), 3)
        if return_explanation or ENABLE_EXPLANATION:
            return preset, "preset confidence_score from metadata"
        return preset

    score = estimate_structure_score(label)
    explanation.append(f"structure={score:.2f}")

    if metadata:
        score, msg1 = adjust_for_quality(score, metadata.get("parser_quality"))
        explanation.append(msg1)
        score, msg2 = adjust_for_signature(score, metadata.get("signature_type"))
        explanation.append(msg2)

    penalty, pen_msg = penalty_for_weak_family(
        family=parsed_result.get("family", ""),
        variant=parsed_result.get("variant", "")
    )
    score += penalty
    explanation.append(pen_msg)

    final_score = round(min(max(bounded_sigmoid(score), MIN_SCORE), MAX_SCORE), 3)
    explanation.append(f"sigmoid_normalized={final_score:.3f}")

    if return_explanation or ENABLE_EXPLANATION:
        return final_score, " | ".join(explanation)

    return final_score

def explain_confidence(label: str, parsed_result: Dict[str, str], metadata: Optional[Dict] = None) -> str:
    score, explanation = compute_confidence_score(label, parsed_result, metadata, return_explanation=True)
    return f"Score: {score:.3f} | {explanation}"
