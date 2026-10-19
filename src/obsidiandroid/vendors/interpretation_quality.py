"""Conservative, versioned explanations over immutable retained vendor claims.

Outcome labels describe interpretation evidence, not sample ground truth. Only the
Kaspersky exact-family-slot correction changes a supported family interpretation.
"""
import hashlib
from pathlib import Path
import re

from obsidiandroid.labeling import taxonomy, malware_family_constants
from obsidiandroid.vendors.parsing import kaspersky_parser, parser_defaults, parser_confidence_estimator
from obsidiandroid.vendors.contracts import parsed_label_metadata

POLICY = 'vendor-interpretation-quality-v1'
GENERIC = re.compile(
    r'(?:detected|malicious(?: \(score: \d+\))?|android[.:]malware[.:](?:trojan|spyware)|'
    r'trojan\.gen(?:\.(?:\d+|npe|[a-z]))?|android:evo-gen \[trj\]|apprisk:generisk)', re.I)
TOKENS = re.compile(r'[a-z][a-z0-9]+', re.I)


def source_identity():
    """Pin every source affecting active interpretation, separate from frozen rows."""
    modules = [Path(__file__), Path(taxonomy.__file__), Path(malware_family_constants.__file__),
               Path(kaspersky_parser.__file__), Path(parser_defaults.__file__),
               Path(parser_confidence_estimator.__file__), Path(parsed_label_metadata.__file__)]
    return dict(policy=POLICY, sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in modules})


def interpret(engine, label, frozen_family, frozen_known, catalog_names=()):
    """Explain one distinct retained label without changing taxonomy or raw text."""
    label = str(label or '')
    family = str(frozen_family) if frozen_known else None
    state, reason = 'G_INSUFFICIENT_SOURCE', 'No nonempty family-bearing detection label'
    if not label:
        return dict(state=state, reason=reason, family=None, recognized=False, corrected=False)
    if engine == 'Kaspersky':
        parsed = kaspersky_parser.parse_kaspersky_classification(label).to_dict()
        candidate = taxonomy.normalize_family_name(parsed.get('family','unknown'))
        if parsed.get('edge_case_type') == 'shared_taxonomy_family_slot' and taxonomy.is_known_family_name(candidate):
            family = candidate
            state, reason = 'E_CORRECTED_IMPLEMENTATION', 'Existing supported family in vendor-documented Android name slot; local allowlist omitted it'
    if state == 'E_CORRECTED_IMPLEMENTATION':
        pass
    elif frozen_known:
        state, reason = 'B_FROZEN_RECOGNIZED', 'Existing parser/registry recognition; not independent attribution proof'
    elif GENERIC.fullmatch(label):
        state, reason = 'A_GENERIC_DETECTION', 'Reviewed generic-only label pattern; no family assigned'
    else:
        tokens = {t.casefold() for t in TOKENS.findall(label)}
        known = {taxonomy.normalize_family_name(t) for t in tokens if taxonomy.is_known_family_name(t)}
        catalog = tokens & set(catalog_names)
        if len(known) > 1:
            state, reason = 'D_AMBIGUOUS', 'Multiple supported family tokens without an approved vendor disambiguation rule'
        elif catalog:
            state, reason = 'F_TAXONOMY_REVIEW', 'Literal catalog-name token occurs, but frozen parser recognition or registry support is absent'
        else:
            state, reason = 'C_SPECIFIC_LOOKING_UNRESOLVED', 'Nonempty label outside reviewed generic rules; family-bearing specificity is unverified'
    return dict(state=state, reason=reason, family=family, recognized=family is not None,
                corrected=state=='E_CORRECTED_IMPLEMENTATION')
