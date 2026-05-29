"""Report alias policy drift for Android malware family taxonomy."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.database.db_engine import database_connection


OUT_DIR = Path("output/diagnostics")
OUT_CSV = OUT_DIR / "alias_policy_drift_latest.csv"
OUT_MD = OUT_DIR / "alias_policy_drift_latest.md"


def _load_alias_rows() -> pd.DataFrame:
    query = """
        SELECT
            alias_id,
            alias_name,
            alias_type,
            trust_tier,
            review_status,
            is_preferred,
            is_active,
            family_id
        FROM android_malware_family_alias
        WHERE is_active = 1
    """
    with database_connection() as conn:
        df = pd.read_sql(query, conn)
    return df


def _expected(alias_type: str) -> tuple[str, str] | None:
    if alias_type in {"vendor_label", "public_report_name", "canonical"}:
        return ("curated_alias", "accepted")
    if alias_type == "lineage_name":
        return ("contextual_lineage", "context_only")
    if alias_type in {"variant_label", "variant_token", "misspelling"}:
        return ("contextual_variant", "context_only")
    if alias_type == "raw_alias":
        return ("raw_observed_alias", "matching_only")
    return None


def build_drift(df: pd.DataFrame) -> pd.DataFrame:
    expected = df["alias_type"].map(_expected)
    df["expected_trust_tier"] = expected.map(lambda x: x[0] if x else None)
    df["expected_review_status"] = expected.map(lambda x: x[1] if x else None)
    df["is_policy_scoped"] = df["expected_trust_tier"].notna()
    scoped = df[df["is_policy_scoped"]].copy()
    scoped["trust_tier_mismatch"] = scoped["trust_tier"] != scoped["expected_trust_tier"]
    scoped["review_status_mismatch"] = scoped["review_status"] != scoped["expected_review_status"]
    scoped["is_drift"] = scoped["trust_tier_mismatch"] | scoped["review_status_mismatch"]
    return scoped.sort_values(
        by=["is_drift", "alias_type", "alias_name", "alias_id"],
        ascending=[False, True, True, True],
    )


def write_markdown(df: pd.DataFrame) -> None:
    total = len(df)
    drift = int(df["is_drift"].sum()) if total else 0
    by_type = (
        df.groupby(["alias_type", "is_drift"], dropna=False)["alias_id"]
        .count()
        .reset_index(name="rows")
    )

    lines = [
        "# Alias Policy Drift",
        "",
        f"- Scoped active aliases: **{total}**",
        f"- Drift rows: **{drift}**",
        "",
        "## Drift by alias_type",
        "",
    ]
    if by_type.empty:
        lines.append("No scoped alias rows found.")
    else:
        lines.append("| alias_type | is_drift | rows |")
        lines.append("|---|---:|---:|")
        for _, row in by_type.iterrows():
            lines.append(
                f"| {row['alias_type']} | {1 if row['is_drift'] else 0} | {int(row['rows'])} |"
            )

    top = df[df["is_drift"]].head(50)
    lines.extend(["", "## Top Drift Rows (first 50)", ""])
    if top.empty:
        lines.append("No policy drift detected.")
    else:
        lines.append(
            "| alias_id | alias_name | alias_type | trust_tier | expected_trust_tier | review_status | expected_review_status | family_id |"
        )
        lines.append("|---:|---|---|---|---|---|---|---:|")
        for _, row in top.iterrows():
            lines.append(
                f"| {int(row['alias_id'])} | {row['alias_name']} | {row['alias_type']} | "
                f"{row['trust_tier']} | {row['expected_trust_tier']} | {row['review_status']} | "
                f"{row['expected_review_status']} | {int(row['family_id'])} |"
            )

    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = _load_alias_rows()
    drift = build_drift(base)
    drift.to_csv(OUT_CSV, index=False)
    write_markdown(drift)
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(f"Scoped aliases: {len(drift)}")
    print(f"Drift rows: {int(drift['is_drift'].sum()) if len(drift) else 0}")


if __name__ == "__main__":
    main()

