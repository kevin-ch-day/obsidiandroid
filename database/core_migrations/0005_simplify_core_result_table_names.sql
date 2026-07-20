-- Keep the established Core foundation names and simplify generated-result
-- table names.  This migration is metadata-only and preserves all rows.

RENAME TABLE
  core_run_stage TO run_stage,
  core_feature_contract TO feature_contract,
  core_split_ledger TO split_ledger,
  core_model_execution TO model_execution,
  core_model_metric TO model_metric,
  core_prediction TO prediction,
  core_experiment TO experiment,
  core_experiment_metric TO experiment_metric,
  core_permission_measure TO permission_measure,
  core_label_contract TO label_contract,
  core_label_assignment TO label_assignment,
  core_confusion_cell TO confusion_cell;
