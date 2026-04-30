# Filename: db_av_disagreement_analysis.py
# Purpose: Identify Android malware samples with low consensus among trusted AV engines

from typing import Union
import pandas as pd
from database import db_engine, db_utils
from utils import display_utils as du

# --------------------------------------------------------
# Step 1: Build UNION SQL to melt wide columns
# --------------------------------------------------------
def build_melt_union_sql(engine_names: list) -> str:
    queries = []
    for eng in engine_names:
        safe = eng.replace("`", "").replace('"', "")
        queries.append(
            f"""SELECT sample_id, '{safe}' AS engine, `{safe}` AS result
                FROM virustotal_sample_vendor_engine_verdicts
                WHERE `{safe}` IS NOT NULL AND `{safe}` NOT IN ('', 'None', 'undetected')"""
        )
    return "\nUNION ALL\n".join(queries)

# --------------------------------------------------------
# Step 2: Run disagreement scoring query
# --------------------------------------------------------
def get_high_disagreement_samples(
    threshold: float = 0.3,
    min_engines: int = 5,
    engine_override: list = None,
    verbose: bool = False,
    as_dataframe: bool = False
) -> Union[pd.DataFrame, list]:

    try:
        engines = engine_override if engine_override else db_utils.get_trusted_active_engine_names(only_existing=True)

        if not engines:
            du.print_error("[ABORT] No valid engines available for scoring.")
            return pd.DataFrame() if as_dataframe else []

        if verbose:
            du.print_debug(f"[INFO] Using {len(engines)} engines for scoring.")

        union_sql = build_melt_union_sql(engines)

        query = f"""
            WITH melted AS (
                {union_sql}
            ),
            scored AS (
                SELECT
                    sample_id,
                    SUM(CASE WHEN result = 'malicious' THEN 1 ELSE 0 END) AS malicious_count,
                    SUM(CASE WHEN result = 'undetected' THEN 1 ELSE 0 END) AS undetected_count,
                    COUNT(*) AS total_engines,
                    ROUND(
                        ABS(
                            SUM(CASE WHEN result = 'malicious' THEN 1 ELSE 0 END) -
                            SUM(CASE WHEN result = 'undetected' THEN 1 ELSE 0 END)
                        ) / COUNT(*), 2
                    ) AS disagreement_score
                FROM melted
                GROUP BY sample_id
            )
            SELECT *
            FROM scored
            WHERE disagreement_score <= {threshold}
              AND total_engines >= {min_engines}
            ORDER BY disagreement_score ASC, total_engines DESC
        """

        if verbose:
            du.print_section("[DEBUG] Disagreement Query")
            du.print_info(query)

        return db_engine.execute_query(query, fetch=True, return_columns=True, as_dataframe=as_dataframe)

    except Exception as e:
        du.print_error(f"[ERROR] Disagreement scoring failed: {e}")
        return pd.DataFrame() if as_dataframe else []
