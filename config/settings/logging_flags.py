"""Debug and logging controls."""

DEBUG_MODE = False
LOGGING_ENABLED = True
LOG_FILE_PATH = "logs/runtime.log"
LOG_LEVEL = "INFO"
ENABLE_DB_LOGGING = True
ENABLE_ML_LOGGING = True
ML_TRAINER_VERBOSE = False
LOG_RETENTION_POLICY = "per_run_only"  # one of: per_run_only, rolling_only, hybrid
