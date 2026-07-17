"""Static contract checks for the live Permission Intel concept view asset."""

from pathlib import Path


_VIEW_SQL = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "sql"
    / "permission_intel_concept_view.sql"
)


def test_concept_view_keeps_exact_match_without_wrapping_indexed_token() -> None:
    """The view must retain binary matching while leaving the indexed key bare."""
    text = _VIEW_SQL.read_text(encoding="utf-8")
    compact = " ".join(text.lower().split())

    assert "ct.token_value = binary v.permission_string" in compact
    assert "cast(ct.token_value as char charset binary)" not in compact
