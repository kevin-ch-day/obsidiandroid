"""Profile vendor verdict debt and export family/generic/provenance signal views.

This diagnostic is read-only. It works from the long-form
``virustotal_sample_vendor_verdicts`` table and classifies each malicious vendor
verdict into debt-analysis buckets so operators can see:

- which vendors emit family-ready evidence
- which vendors mostly emit generic or provenance/noise labels
- which samples are dominated by overlapping/generic signals
- which tokens are driving the current taxonomy debt
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.database import authority_contracts, db_engine
from obsidiandroid.database.verdict_semantics import (
    classify_verdict_noise_bucket,
    normalize_verdict_token,
    tokenize_verdict_label,
)


OUTPUT_DIR = Path("output") / "diagnostics"
SUMMARY_CSV = OUTPUT_DIR / "vendor_verdict_debt_summary_latest.csv"
TOKEN_CSV = OUTPUT_DIR / "vendor_verdict_debt_tokens_latest.csv"
SAMPLE_CSV = OUTPUT_DIR / "vendor_verdict_debt_samples_latest.csv"
DETAIL_CSV = OUTPUT_DIR / "vendor_verdict_debt_detail_latest.csv"
SUMMARY_MD = OUTPUT_DIR / "vendor_verdict_debt_summary_latest.md"

DETAIL_LIMIT = 5000
TOKEN_MIN_SUPPORT = 3


def _fetch_verdict_rows() -> pd.DataFrame:
    """Load malicious Android APK vendor verdict rows with catalog context."""
    query = """
        SELECT
            vv.sample_id,
            LOWER(TRIM(COALESCE(eng.vendor_key, ''))) AS vendor_name,
            vv.verdict_label,
            LOWER(TRIM(COALESCE(msc.family_label, ''))) AS family_label_lc,
            LOWER(TRIM(COALESCE(msc.classification_primary, ''))) AS classification_primary_lc,
            LOWER(TRIM(COALESCE(msc.classification_subtype, ''))) AS classification_subtype_lc,
            LOWER(TRIM(COALESCE(msc.vt_family_token, ''))) AS vt_family_token_lc,
            LOWER(TRIM(COALESCE(msc.vt_suggested_label, ''))) AS vt_suggested_label_lc,
            LOWER(TRIM(COALESCE(msc.android_package_name, ''))) AS android_package_name_lc,
            COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
            COALESCE(vs.confidence_score, 0) AS confidence_score,
            COALESCE(vs.vt_malicious_count, 0) AS vt_malicious_count
        FROM virustotal_sample_vendor_verdicts AS vv
        JOIN virustotal_vendor_engines AS eng
          ON eng.vendor_engine_id = vv.vendor_engine_id
        JOIN malware_sample_catalog AS msc
          ON msc.sample_id = vv.sample_id
        LEFT JOIN vt_sample_verdict_confidence_current AS vs
          ON vs.sample_id = vv.sample_id
        WHERE vv.verdict_category = 'malicious'
          AND COALESCE(TRIM(vv.verdict_label), '') <> ''
          AND LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
          AND LOWER(TRIM(COALESCE(msc.file_extension, ''))) = 'apk'
    """
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def _classify_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Add verdict bucket and token columns."""
    if df.empty:
        return df
    known_families, known_aliases = authority_contracts.load_known_family_and_alias_tokens()
    out = df.copy()
    out["verdict_label_lc"] = out["verdict_label"].map(normalize_verdict_token)
    out["verdict_bucket"] = out["verdict_label"].map(
        lambda value: classify_verdict_noise_bucket(
            value,
            known_family_tokens=known_families,
            known_alias_tokens=known_aliases,
        )
    )
    out["token_list"] = out["verdict_label"].map(tokenize_verdict_label)
    out["known_family_token_hits"] = out["token_list"].map(
        lambda tokens: ",".join(sorted(set(tokens) & known_families))
    )
    out["known_alias_token_hits"] = out["token_list"].map(
        lambda tokens: ",".join(sorted(set(tokens) & known_aliases))
    )
    return out


def _vendor_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate verdict debt posture by vendor."""
    if df.empty:
        return pd.DataFrame()
    grouped = (
        df.groupby("vendor_name", dropna=False)
        .agg(
            malicious_rows=("sample_id", "size"),
            distinct_samples=("sample_id", "nunique"),
            distinct_labels=("verdict_label_lc", "nunique"),
            family_ready_rows=("verdict_bucket", lambda s: int((s == "family_ready").sum())),
            family_overlap_rows=("verdict_bucket", lambda s: int((s == "family_overlap").sum())),
            generic_signal_rows=("verdict_bucket", lambda s: int((s == "generic_signal").sum())),
            provenance_noise_rows=("verdict_bucket", lambda s: int((s == "provenance_noise").sum())),
            other_signal_rows=("verdict_bucket", lambda s: int((s == "other_signal").sum())),
            mean_confidence_score=("confidence_score", "mean"),
        )
        .reset_index()
    )
    grouped["family_ready_pct"] = (100.0 * grouped["family_ready_rows"] / grouped["malicious_rows"]).round(2)
    grouped["generic_signal_pct"] = (100.0 * grouped["generic_signal_rows"] / grouped["malicious_rows"]).round(2)
    grouped["provenance_noise_pct"] = (100.0 * grouped["provenance_noise_rows"] / grouped["malicious_rows"]).round(2)
    grouped["overlap_pct"] = (100.0 * grouped["family_overlap_rows"] / grouped["malicious_rows"]).round(2)
    grouped["family_consensus_ratio"] = (grouped["family_ready_rows"] / grouped["malicious_rows"]).round(4)
    grouped["generic_pressure_ratio"] = (grouped["generic_signal_rows"] / grouped["malicious_rows"]).round(4)
    grouped["overlap_pressure_ratio"] = (grouped["family_overlap_rows"] / grouped["malicious_rows"]).round(4)
    grouped["debt_pressure_score"] = (
        (grouped["generic_signal_rows"] * 1.0)
        + (grouped["provenance_noise_rows"] * 1.25)
        + (grouped["family_overlap_rows"] * 1.5)
        - (grouped["family_ready_rows"] * 0.5)
    ).round(2)
    grouped["vendor_posture"] = grouped.apply(_classify_vendor_posture, axis=1)
    return grouped.sort_values(
        ["debt_pressure_score", "generic_signal_rows", "provenance_noise_rows", "vendor_name"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def _token_pressure(df: pd.DataFrame) -> pd.DataFrame:
    """Explode tokens and summarize top debt-driving tokens by bucket."""
    if df.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        tokens = list(dict.fromkeys(row.get("token_list", [])))
        for token in tokens:
            if len(token) < 3:
                continue
            rows.append(
                {
                    "token": token,
                    "vendor_name": row["vendor_name"],
                    "sample_id": row["sample_id"],
                    "verdict_bucket": row["verdict_bucket"],
                }
            )
    tokens_df = pd.DataFrame(rows)
    if tokens_df.empty:
        return tokens_df
    summary = (
        tokens_df.groupby(["token", "verdict_bucket"], dropna=False)
        .agg(
            row_count=("sample_id", "size"),
            sample_count=("sample_id", "nunique"),
            vendor_count=("vendor_name", "nunique"),
        )
        .reset_index()
    )
    summary = summary[summary["row_count"] >= TOKEN_MIN_SUPPORT].copy()
    return summary.sort_values(
        ["row_count", "sample_count", "vendor_count", "token"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def _sample_pressure(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize mixed-signal pressure by sample."""
    if df.empty:
        return pd.DataFrame()
    grouped = (
        df.groupby("sample_id", dropna=False)
        .agg(
            android_package_name_lc=("android_package_name_lc", "first"),
            family_label_lc=("family_label_lc", "first"),
            classification_primary_lc=("classification_primary_lc", "first"),
            classification_subtype_lc=("classification_subtype_lc", "first"),
            confidence_bucket=("confidence_bucket", "first"),
            confidence_score=("confidence_score", "max"),
            vt_malicious_count=("vt_malicious_count", "max"),
            malicious_rows=("vendor_name", "size"),
            distinct_vendors=("vendor_name", "nunique"),
            family_ready_rows=("verdict_bucket", lambda s: int((s == "family_ready").sum())),
            family_overlap_rows=("verdict_bucket", lambda s: int((s == "family_overlap").sum())),
            generic_signal_rows=("verdict_bucket", lambda s: int((s == "generic_signal").sum())),
            provenance_noise_rows=("verdict_bucket", lambda s: int((s == "provenance_noise").sum())),
        )
        .reset_index()
    )
    grouped["mixed_signal_score"] = (
        grouped["family_overlap_rows"] * 2
        + grouped["generic_signal_rows"]
        + grouped["provenance_noise_rows"]
        - grouped["family_ready_rows"]
    )
    grouped["sample_posture"] = grouped.apply(_classify_sample_posture, axis=1)
    return grouped.sort_values(
        ["mixed_signal_score", "confidence_score", "malicious_rows", "sample_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def _classify_vendor_posture(row: pd.Series) -> str:
    """Assign a compact operator posture to a vendor."""
    if float(row.get("overlap_pressure_ratio", 0.0)) >= 0.40:
        return "overlap_heavy"
    if float(row.get("provenance_noise_pct", 0.0)) >= 10.0:
        return "provenance_heavy"
    if float(row.get("generic_pressure_ratio", 0.0)) >= 0.85:
        return "generic_heavy"
    if float(row.get("family_consensus_ratio", 0.0)) >= 0.20:
        return "family_useful"
    return "mixed"


def _classify_sample_posture(row: pd.Series) -> str:
    """Assign an operator posture to a sample's verdict mix."""
    family_ready = int(row.get("family_ready_rows", 0))
    overlap = int(row.get("family_overlap_rows", 0))
    generic = int(row.get("generic_signal_rows", 0))
    provenance = int(row.get("provenance_noise_rows", 0))
    if family_ready >= 3 and overlap <= 1 and generic <= family_ready * 2:
        return "repair_candidate"
    if overlap >= family_ready and overlap >= 4:
        return "overlap_conflict"
    if provenance >= 3 and family_ready == 0:
        return "provenance_noise"
    if generic >= 10 and family_ready == 0:
        return "generic_noise"
    return "mixed_review"


def _write_markdown_summary(
    *,
    summary_df: pd.DataFrame,
    token_df: pd.DataFrame,
    sample_df: pd.DataFrame,
    detail_df: pd.DataFrame,
) -> None:
    """Write an operator-facing markdown digest for verdict debt."""
    lines: list[str] = [
        "# Vendor Verdict Debt Summary",
        "",
        "This report classifies Android malicious vendor verdicts into:",
        "- `family_ready`: contains known governed family or alias tokens with lower overlap pressure",
        "- `family_overlap`: mixes family-like evidence with known overlap-heavy detector tokens",
        "- `generic_signal`: mostly class/generic/detector language",
        "- `provenance_noise`: filename/artifact/provenance-style labels",
        "- `other_signal`: non-empty residue that does not fit the buckets above",
        "",
        "Interpretation notes:",
        "- The heuristics are aligned to AV label normalization research such as AVClass and AVClass2, which emphasize tokenization, generic-token removal, alias detection, and separating useful concepts from vendor-specific noise.",
        "- This surface is for operator triage, not ground-truth family attribution by itself.",
        "",
        f"- Malicious vendor rows: `{len(detail_df)}`",
        f"- Distinct Android samples: `{detail_df['sample_id'].nunique() if not detail_df.empty else 0}`",
        f"- Distinct vendors: `{detail_df['vendor_name'].nunique() if not detail_df.empty else 0}`",
        "",
        "## Top vendor debt pressure",
        "",
    ]
    if summary_df.empty:
        lines.append("No vendor verdict debt rows found.")
    else:
        top = summary_df.head(10)
        for _, row in top.iterrows():
            lines.append(
                f"- `{row['vendor_name']}`: posture=`{row['vendor_posture']}` "
                f"family_ready={row['family_ready_pct']:.2f}% "
                f"generic={row['generic_signal_pct']:.2f}% "
                f"provenance={row['provenance_noise_pct']:.2f}% "
                f"overlap={row['overlap_pct']:.2f}% "
                f"score={row['debt_pressure_score']:.2f}"
            )
    lines.extend(["", "## Top debt-driving tokens", ""])
    if token_df.empty:
        lines.append("No token pressure rows found.")
    else:
        for _, row in token_df.head(15).iterrows():
            lines.append(
                f"- `{row['token']}` in `{row['verdict_bucket']}`: "
                f"rows={int(row['row_count'])}, samples={int(row['sample_count'])}, vendors={int(row['vendor_count'])}"
            )
    lines.extend(["", "## Highest-pressure samples", ""])
    if sample_df.empty:
        lines.append("No sample pressure rows found.")
    else:
        for _, row in sample_df.head(15).iterrows():
            lines.append(
                f"- `sample_id={int(row['sample_id'])}` package=`{row['android_package_name_lc'] or '<blank>'}` "
                f"family=`{row['family_label_lc'] or '<blank>'}` posture=`{row['sample_posture']}` "
                f"family_ready={int(row['family_ready_rows'])} overlap={int(row['family_overlap_rows'])} "
                f"generic={int(row['generic_signal_rows'])} provenance={int(row['provenance_noise_rows'])} "
                f"score={int(row['mixed_signal_score'])}"
            )
    lines.extend(
        [
            "",
            "## Output files",
            "",
            f"- `{SUMMARY_CSV}`",
            f"- `{TOKEN_CSV}`",
            f"- `{SAMPLE_CSV}`",
            f"- `{DETAIL_CSV}`",
            "",
            "## Source references",
            "",
            "- AVClass release and RAID 2016 description: https://software.imdea.org/news/2016/07-18-avclass-release/",
            "- AVClass2 ACSAC 2020 paper: https://software.imdea.org/~juanca/papers/avclass2_acsac20.pdf",
            "- RecMaL discussion of AV-label structure and inconsistency: https://www.sciencedirect.com/science/article/pii/S0167404823000871",
        ]
    )
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Write verdict debt exports and print a compact operator summary."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_df = _fetch_verdict_rows()
    detail_df = _classify_rows(raw_df)
    summary_df = _vendor_summary(detail_df)
    token_df = _token_pressure(detail_df)
    sample_df = _sample_pressure(detail_df)

    detail_df.head(DETAIL_LIMIT).to_csv(DETAIL_CSV, index=False)
    summary_df.to_csv(SUMMARY_CSV, index=False)
    token_df.to_csv(TOKEN_CSV, index=False)
    sample_df.to_csv(SAMPLE_CSV, index=False)
    _write_markdown_summary(
        summary_df=summary_df,
        token_df=token_df,
        sample_df=sample_df,
        detail_df=detail_df,
    )

    print(f"[OK] Exported: {SUMMARY_CSV}")
    print(f"[OK] Exported: {TOKEN_CSV}")
    print(f"[OK] Exported: {SAMPLE_CSV}")
    print(f"[OK] Exported: {DETAIL_CSV} (top {min(len(detail_df), DETAIL_LIMIT)} rows)")
    print(f"[OK] Exported: {SUMMARY_MD}")
    print("")
    print(f"malicious_vendor_rows={len(detail_df)}")
    print(f"distinct_samples={detail_df['sample_id'].nunique() if not detail_df.empty else 0}")
    print(f"distinct_vendors={detail_df['vendor_name'].nunique() if not detail_df.empty else 0}")

    if not summary_df.empty:
        print("\n== vendor_debt_summary_top10 ==")
        print(
            summary_df[
                [
                    "vendor_name",
                    "malicious_rows",
                    "family_ready_pct",
                    "generic_signal_pct",
                    "provenance_noise_pct",
                    "overlap_pct",
                    "debt_pressure_score",
                ]
            ]
            .head(10)
            .to_string(index=False)
        )
    if not token_df.empty:
        print("\n== token_pressure_top15 ==")
        print(token_df.head(15).to_string(index=False))
    if not sample_df.empty:
        print("\n== sample_pressure_top15 ==")
        print(
            sample_df[
                [
                    "sample_id",
                    "android_package_name_lc",
                    "family_label_lc",
                    "confidence_score",
                    "family_ready_rows",
                    "family_overlap_rows",
                    "generic_signal_rows",
                    "provenance_noise_rows",
                    "mixed_signal_score",
                ]
            ]
            .head(15)
            .to_string(index=False)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
