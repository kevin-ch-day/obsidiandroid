"""CCNCPS 2026 published reference values: not reproduced by any retained run.

These numbers are the values printed in the CCNCPS 2026 paper (Table II and
the Vendor+Perms Random Forest row of Table III). They entered this repository
as test fixtures in df88e67 (2026-04-29), before the frozen benchmark run
20260504T044304Z__8c64e6. No retained run artifact, warehouse row, backup or
git revision produces them; see
output/reports/ccncps2026_provenance_search_2026-10-19.md.

Tests use them only as realistic formatting and display inputs. A test that
reads them must not be taken as evidence that the pipeline reproduces the
published results.
"""

from __future__ import annotations

NOT_REPRODUCED = True

# Table II, Random Forest (published).
PUBLISHED_TABLE_II_RF = {
    "Accuracy": 0.9761,
    "Precision": 0.9751,
    "Recall": 0.9761,
    "F1-Score": 0.9750,
    "Macro F1-Score": 0.9530,
}

# Table II, XGBoost (published).
PUBLISHED_TABLE_II_XGB = {
    "Accuracy": 0.9681,
    "Precision": 0.9684,
    "Recall": 0.9681,
    "F1-Score": 0.9665,
    "Macro F1-Score": 0.9412,
}

# Table III, Vendor+Perms Random Forest (published).
PUBLISHED_TABLE_III_VENDOR_PERMS_RF = {
    "accuracy": 0.9761,
    "macro_precision": 0.9584,
    "macro_recall": 0.9568,
    "macro_f1_score": 0.9566,
}

# Four-decimal spellings used by the guard test to keep these values here only.
PUBLISHED_VALUE_LITERALS = (
    "0.9761", "0.9751", "0.9750", "0.9530",
    "0.9681", "0.9684", "0.9665", "0.9412",
    "0.9584", "0.9568", "0.9566",
)
