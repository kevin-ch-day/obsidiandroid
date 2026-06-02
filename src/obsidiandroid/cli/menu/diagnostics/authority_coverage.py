"""Authority coverage diagnostic view for the Data Diagnostics menu."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.common import ml_console
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
    du.print_stat("Markdown report", du.format_console_path(bundle.get("md_path")) if bundle.get("md_path") else "missing")
    du.print_stat("Missing-family CSV", du.format_console_path(bundle.get("missing_out")) if bundle.get("missing_out") else "missing")
    du.print_stat("Unknown-type CSV", du.format_console_path(bundle.get("unknown_type_out")) if bundle.get("unknown_type_out") else "missing")
    du.print_stat("Year/type CSV", du.format_console_path(bundle.get("year_type_out")) if bundle.get("year_type_out") else "missing")
    print("")

    missing_df = bundle.get("missing_df")
    plausible = None
    generic = None
    if missing_df is not None and not missing_df.empty:
        plausible = missing_df[missing_df["candidate_kind"] == "plausible_real_family_candidate"]
        generic = missing_df[missing_df["candidate_kind"] == "generic_or_coarse_label"]
    unknown_type_df = bundle.get("unknown_type_df")
    top_conflicts_df = bundle.get("top_conflicts_df")
    concentration_df = bundle.get("concentration_df")

    bucket_df = bundle.get("bucket_df")
    conflict_summary_df = bundle.get("conflict_summary_df")
    year_bucket_df = bundle.get("year_bucket_df")

    authority_family_typed_rows = 0
    authority_family_typed_pct = "—"
    generic_rows = 0
    unknown_rows = 0
    if bucket_df is not None and not bucket_df.empty:
        typed_rows = bucket_df.loc[bucket_df["authority_bucket"].astype(str) == "authority_family_typed"]
        if not typed_rows.empty:
            authority_family_typed_rows = int(typed_rows["row_count"].iloc[0])
            authority_family_typed_pct = f"{float(typed_rows['row_pct'].iloc[0]):.2f}%"
        generic_rows = int(
            bucket_df.loc[bucket_df["authority_bucket"].astype(str) == "generic_label_candidate", "row_count"].sum()
        )
        unknown_rows = int(
            bucket_df.loc[bucket_df["authority_bucket"].astype(str) == "resolved_unknown", "row_count"].sum()
        )

    du.print_subheader("Coverage summary")
    du.print_stat("Authority-covered rows", f"{authority_family_typed_rows} ({authority_family_typed_pct})")
    du.print_stat("Generic / coarse residue", generic_rows)
    du.print_stat("Unknown-family residue", unknown_rows)
    du.print_stat(
        "Unknown-type families",
        len(unknown_type_df) if unknown_type_df is not None and not unknown_type_df.empty else 0,
    )

    du.print_subheader("Raw vs authority")
    if conflict_summary_df is not None and not conflict_summary_df.empty:
        for _, row in conflict_summary_df.head(5).iterrows():
            print(f"{str(row.get('raw_vs_authority_status', 'status')):<34} : {row.get('row_count', 0)}")
    else:
        print("No raw-vs-authority summary available.")

    du.print_subheader("Review next")
    if plausible is not None and not plausible.empty:
        print("Missing authority-family candidates:")
        for _, row in plausible.head(5).iterrows():
            print(f"- {row.get('resolved_family_lc', ''):<22} : {row.get('row_count', 0)} rows")
    if generic is not None and not generic.empty:
        print("Generic / coarse label candidates:")
        for _, row in generic.head(5).iterrows():
            print(
                f"- {row.get('resolved_family_lc', ''):<22} : {row.get('row_count', 0)} rows | "
                f"{row.get('authority_gap_reason', '')}"
            )
    if unknown_type_df is not None and not unknown_type_df.empty:
        print("Unknown-type families:")
        for _, row in unknown_type_df.head(5).iterrows():
            print(f"- {row.get('family_slug', ''):<22} : {row.get('row_count', 0)} rows")

    du.print_subheader("Top conflicts")
    if top_conflicts_df is not None and not top_conflicts_df.empty:
        for _, row in top_conflicts_df.head(5).iterrows():
            print(
                f"- {row.get('family_slug', '')} ({row.get('type_slug', '')}) : "
                f"{row.get('raw_classification_primary', '')} / {row.get('raw_classification_subtype', '')} | "
                f"{row.get('row_count', 0)} rows"
            )
    else:
        print("No top raw-vs-authority conflicts.")

    du.print_subheader("Temporal concentration")
    if concentration_df is not None and not concentration_df.empty:
        for _, row in concentration_df.head(5).iterrows():
            print(
                f"- {row.get('family_slug', '')} ({row.get('type_slug', '')}) : "
                f"{row.get('row_count', 0)} rows | {row.get('active_years', 0)} years | "
                f"{row.get('temporal_feasibility', '')}"
            )
    else:
        print("No temporal concentration summary available.")
    print("")
    print("Temporal split caveats:")
    print("1. Use an authority-covered temporal benchmark, not the whole catalog.")
    print("2. Add a type-stratified temporal benchmark because year/type concentration is high.")
    print("3. Add a family-persistence-only benchmark for families with multi-year support.")

    du.print_subheader("Diagnostics")
    du.print_stat("Start here", du.format_console_path(bundle.get("md_path")) if bundle.get("md_path") else "missing")
    du.print_stat("Missing-family CSV", du.format_console_path(bundle.get("missing_out")) if bundle.get("missing_out") else "missing")
    du.print_stat("Unknown-type CSV", du.format_console_path(bundle.get("unknown_type_out")) if bundle.get("unknown_type_out") else "missing")
    du.print_stat("Year/type CSV", du.format_console_path(bundle.get("year_type_out")) if bundle.get("year_type_out") else "missing")

    if ml_console.show_debug_tables(default=False):
        du.print_table(bucket_df, title="Authority bucket summary", show_index=False)
        du.print_table(conflict_summary_df, title="Raw-vs-authority status summary", show_index=False)
        du.print_table(year_bucket_df, title="Authority coverage by year", show_index=False, max_rows=20)
        if plausible is not None and not plausible.empty:
            du.print_table(plausible.head(15), title="Missing authority-family candidates", show_index=False)
        if generic is not None and not generic.empty:
            du.print_table(generic.head(15), title="Generic / coarse label candidates", show_index=False)
        if unknown_type_df is not None and not unknown_type_df.empty:
            du.print_table(unknown_type_df.head(15), title="Authority families with unknown type", show_index=False)
        if top_conflicts_df is not None and not top_conflicts_df.empty:
            du.print_table(top_conflicts_df.head(15), title="Top raw-vs-authority conflicts", show_index=False)
        if concentration_df is not None and not concentration_df.empty:
            du.print_table(concentration_df.head(15), title="Temporal / year-type concentration", show_index=False)
    return 0


__all__ = ["launch_family_type_authority_coverage_menu"]
