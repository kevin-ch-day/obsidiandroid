"""Model ranking and terminal/report verbosity options."""

MODEL_RANK_PRIMARY_METRIC = "macro_f1_score"
ENABLE_MODEL_COMPARISON_EXCEL_EXPORT = False
ENABLE_MODEL_COMPARISON_CSV_EXPORT = True

# Persist sklearn RF ``feature_importances_`` (Gini) for headline runs (not ablations).
ENABLE_RF_IMPURITY_IMPORTANCE_EXPORT = True
RF_IMPORTANCE_EXPORT_TOP_K = 50
ML_CONSOLE_MODE = "research"  # one of: minimal, research, debug
ML_TERMINAL_COMPACT = True
ML_SHOW_METRIC_GUIDE = False
ML_SHOW_LABEL_ENCODER_INFO = False
ML_SHOW_PREDICTION_PREVIEWS = False
ML_SHOW_PER_FAMILY_TABLE = False
# When per-family table is hidden, optionally show a small top-N preview.
ML_SHOW_PER_FAMILY_PREVIEW_WHEN_HIDDEN = False
ML_PER_FAMILY_TOP_ROWS = 12
ML_SHOW_IMPROVEMENT_OUTLOOK = False
ENGINE_SUMMARY_SHOW_TOP5_TABLE = False
FAMILY_DISTRIBUTION_MAX_CONSOLE_ROWS = 20
