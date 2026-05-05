"""Pass 58: ``obsidiandroid.labeling.taxonomy`` wrapper contract (not a ``sys.modules`` alias)."""

from __future__ import annotations

from pathlib import Path

import ml_classification.common.malware_family_constants as legacy_mfc
import obsidiandroid.labeling.taxonomy as taxonomy


def test_taxonomy_module_is_canonical_src_file() -> None:
    path = Path(taxonomy.__file__).resolve()
    assert path.name == "taxonomy.py"
    assert path.parts[-3:-1] == ("obsidiandroid", "labeling")


def test_taxonomy_public_functions_match_legacy_behavior() -> None:
    for raw in ("HQWar", "Flu-Bot", 15, "Cabassous", "", None):
        assert taxonomy.normalize_family_name(raw) == legacy_mfc.normalize_family_name(raw)

    assert taxonomy.is_known_family_name("hqwar") == legacy_mfc.is_known_family_name("hqwar")
    assert taxonomy.is_known_family_name("TrickMo") == legacy_mfc.is_known_family_name("TrickMo")
    assert taxonomy.canonicalize_family_label("Cabassous") == legacy_mfc.canonicalize_family_label("Cabassous")


def test_taxonomy_functions_are_not_legacy_object_identity() -> None:
    """Wrappers deliberately do not re-export legacy function objects (room for future boundary)."""
    assert taxonomy.normalize_family_name is not legacy_mfc.normalize_family_name
    assert taxonomy.is_known_family_name is not legacy_mfc.is_known_family_name
    assert taxonomy.canonicalize_family_label is not legacy_mfc.canonicalize_family_label
