"""Inspect missing parser patterns from live vendor labels.

Exports high-frequency labels where parsing still fails:
- unknown/generic threat_class
- unknown/generic family
- RAT-like labels parsed as non-RAT
"""

from __future__ import annotations

from pathlib import Path
import sys
from collections import Counter
import pandas as pd
import mysql.connector

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.repo_import_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.vendors.parsing import (  # noqa: E402
    avast_parser,
    avast_mobile_parser,
    bitdefender_parser,
    bitdefenderfalx_parser,
    ikarus_parser,
    k7gw_parser,
    kaspersky_parser,
    lionic_parser,
    microsoft_parser,
    tencent_parser,
    zonealarm_parser,
    alibaba_parser,
    ahnlab_v3_parser,
    generic_label_parser,
)


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "vendor_missing_patterns_latest.csv"


PARSER_MAP = {
    "ahnlab_v3": ahnlab_v3_parser.parse_ahnlab_v3_classification,
    "alibaba": alibaba_parser.parse_alibaba_classification,
    "avast": avast_parser.parse_avast_label,
    "avast_mobile": avast_mobile_parser.parse_avast_mobile_label,
    "bitdefender": bitdefender_parser.parse_bitdefender_classification,
    "bitdefenderfalx": bitdefenderfalx_parser.parse_bitdefenderfalx_classification,
    "ikarus": ikarus_parser.parse_ikarus_classification,
    "k7gw": k7gw_parser.parse_k7gw_classification,
    "kaspersky": kaspersky_parser.parse_kaspersky_classification,
    "lionic": lionic_parser.parse_lionic_classification,
    "microsoft": microsoft_parser.parse_microsoft_classification,
    "tencent": tencent_parser.parse_tencent_classification,
    "zonealarm": zonealarm_parser.parse_zonealarm_classification,
    "drweb": generic_label_parser.parse_generic_classification,
    "eset_nod32": generic_label_parser.parse_generic_classification,
    "f_secure": generic_label_parser.parse_generic_classification,
    "fortinet": generic_label_parser.parse_generic_classification,
    "avira": generic_label_parser.parse_generic_classification,
    "sophos": generic_label_parser.parse_generic_classification,
}


def _collect_vendor_labels(cur, vendor_col: str) -> list[str]:
    cur.execute(
        f"""
        SELECT {vendor_col}
        FROM virustotal_sample_vendor_engine_verdicts
        WHERE {vendor_col} IS NOT NULL
          AND TRIM({vendor_col}) <> ''
          AND LOWER(TRIM({vendor_col})) NOT IN ('none', 'null', 'n/a')
        """
    )
    return [row[0] for row in cur.fetchall()]


def run_inspection() -> pd.DataFrame:
    conn = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="",
        database="erebus_database_dev",
    )
    cur = conn.cursor()

    rows: list[dict] = []
    for vendor, parser in PARSER_MAP.items():
        labels = _collect_vendor_labels(cur, vendor)
        unknown_threat = Counter()
        unknown_family = Counter()
        rat_missed = Counter()

        for label in labels:
            parsed = parser(label)
            parsed_dict = parsed.to_dict() if hasattr(parsed, "to_dict") else parsed
            threat = str(parsed_dict.get("threat_class", "unknown")).strip().lower()
            family = str(parsed_dict.get("family", "unknown")).strip().lower()

            if threat in {"unknown", "generic", ""}:
                unknown_threat[label] += 1
            if family in {"unknown", "generic", "agent", "malware", ""}:
                unknown_family[label] += 1
            if (
                any(tok in str(label).lower() for tok in ["rat", "androrat", "realrat", "xrat", "gravityrat", "remote-access"])
                and threat != "rat"
            ):
                rat_missed[label] += 1

        for category, counter in (
            ("unknown_threat", unknown_threat),
            ("unknown_family", unknown_family),
            ("rat_missed", rat_missed),
        ):
            for label, count in counter.most_common(30):
                rows.append(
                    {
                        "vendor": vendor,
                        "category": category,
                        "count": int(count),
                        "label": label,
                    }
                )

    cur.close()
    conn.close()

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values(["vendor", "category", "count"], ascending=[True, True, False], inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = run_inspection()
    if df.empty:
        print("[WARN] No missing-pattern rows generated.")
        return 1
    df.to_csv(CSV_OUT, index=False)
    print(f"[OK] Exported: {CSV_OUT}")
    print(df.head(20).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
