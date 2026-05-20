"""Authority coverage diagnostic view for the Data Diagnostics menu."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.cli.ui import display as du
from obsidiandroid.diagnostics.family_type_authority_coverage import (
    DEFAULT_MD,
    DEFAULT_MISSING,
    DEFAULT_UNKNOWN_TYPE,
    DEFAULT_YEAR_TYPE,
    generate_authority_coverage_artifacts,
)


def launch_family_type_authority_coverage_menu(*, output_root: Path) -> int:
    """Render family/type authority coverage using the live Erebus authority view."""
    du.print_section("Family/type authority coverage")
    bundle = generate_authority_coverage_artifacts(
        md_path=output_root / "diagnostics" / DEFAULT_MD.name,
        missing_out=output_root / "diagnostics" / DEFAULT_MISSING.name,
        unknown_type_out=output_root / "diagnostics" / DEFAULT_UNKNOWN_TYPE.name,
        year_type_out=output_root / "diagnostics" / DEFAULT_YEAR_TYPE.name,
        require_live_view=True,
    )
    if not bundle.get("ok", False):
        du.print_warning(str(bundle.get("warning") or "Authority coverage diagnostic unavailable."))
        return 1

    df = bundle.get("df")
    row_count = len(df) if hasattr(df, "__len__") else 0
    du.print_stat("Source mode", str(bundle.get("source_mode") or "unknown"))
    du.print_stat("Android APK rows evaluated", str(row_count))
    du.print_stat("Markdown report", str(bundle.get("md_path")))
    du.print_stat("Missing-family CSV", str(bundle.get("missing_out")))
    du.print_stat("Unknown-type CSV", str(bundle.get("unknown_type_out")))
    du.print_stat("Year/type CSV", str(bundle.get("year_type_out")))
    print("")

    du.print_table(bundle.get("bucket_df"), title="Authority bucket summary", show_index=False)
    du.print_table(bundle.get("conflict_summary_df"), title="Raw-vs-authority status summary", show_index=False)
    du.print_table(bundle.get("year_bucket_df"), title="Authority coverage by year", show_index=False, max_rows=20)

    missing_df = bundle.get("missing_df")
    if missing_df is not None and not missing_df.empty:
        plausible = missing_df[missing_df["candidate_kind"] == "plausible_real_family_candidate"]
        generic = missing_df[missing_df["candidate_kind"] == "generic_or_coarse_label"]
        if not plausible.empty:
            du.print_table(
                plausible.head(15),
                title="Missing authority-family candidates",
                show_index=False,
            )
        if not generic.empty:
            du.print_table(
                generic.head(15),
                title="Generic / coarse label candidates",
                show_index=False,
            )

    unknown_type_df = bundle.get("unknown_type_df")
    if unknown_type_df is not None and not unknown_type_df.empty:
        du.print_table(
            unknown_type_df.head(15),
            title="Authority families with unknown type",
            show_index=False,
        )

    top_conflicts_df = bundle.get("top_conflicts_df")
    if top_conflicts_df is not None and not top_conflicts_df.empty:
        du.print_table(
            top_conflicts_df.head(15),
            title="Top raw-vs-authority conflicts",
            show_index=False,
        )

    concentration_df = bundle.get("concentration_df")
    if concentration_df is not None and not concentration_df.empty:
        du.print_table(
            concentration_df.head(15),
            title="Temporal / year-type concentration",
            show_index=False,
        )

    du.print_note("Temporal split caveats:")
    du.print_note("1) Use an authority-covered temporal benchmark, not the whole catalog.")
    du.print_note("2) Add a type-stratified temporal benchmark because year/type concentration is high.")
    du.print_note("3) Add a family-persistence-only benchmark for families with multi-year support.")
    return 0


__all__ = ["launch_family_type_authority_coverage_menu"]
