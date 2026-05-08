"""Pass 58: ``obsidiandroid.labeling.taxonomy`` wrapper contract (not a ``sys.modules`` alias)."""

from __future__ import annotations

from pathlib import Path

import obsidiandroid.labeling.malware_family_constants as canon_constants
import obsidiandroid.labeling.taxonomy as taxonomy


def test_taxonomy_module_is_canonical_src_file() -> None:
    path = Path(taxonomy.__file__).resolve()
    assert path.name == "taxonomy.py"
    assert path.parts[-3:-1] == ("obsidiandroid", "labeling")


def test_taxonomy_public_functions_match_canonical_constants() -> None:
    for raw in ("HQWar", "Flu-Bot", 15, "Cabassous", "", None):
        assert taxonomy.normalize_family_name(raw) == canon_constants.normalize_family_name(raw)

    assert taxonomy.is_known_family_name("hqwar") == canon_constants.is_known_family_name("hqwar")
    assert taxonomy.is_known_family_name("TrickMo") == canon_constants.is_known_family_name("TrickMo")
    assert taxonomy.canonicalize_family_label("Cabassous") == canon_constants.canonicalize_family_label("Cabassous")


def test_taxonomy_functions_are_not_constants_object_identity() -> None:
    """Wrappers deliberately do not re-export underlying function objects (room for future boundary)."""
    assert taxonomy.normalize_family_name is not canon_constants.normalize_family_name
    assert taxonomy.is_known_family_name is not canon_constants.is_known_family_name
    assert taxonomy.canonicalize_family_label is not canon_constants.canonicalize_family_label
