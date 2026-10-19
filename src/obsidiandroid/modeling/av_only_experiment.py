"""Isolated retained-AV development experiment; never uses the normal run slots.

Default is plan-only. An explicit --train runs one declared model fit after all contracts pass.
The target is recorded family attribution, not independent APK ground truth.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import time
import warnings

import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold

from config import app_config
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.features.av_lineage import LINEAGE_POLICY_ID, identifier
from obsidiandroid.features.retained_av_reports import prepare_retained_av
from obsidiandroid.features.av_detection_contract import fit_av_detection_contract, transform_av_detection_features
from .av_partition import AVPartition, frame_digest

PROFILE_ID = 'dev_av_only_recorded_family'
MODELS = ('logistic_regression', 'random_forest', 'xgboost')


def prepare(snapshot, source_digest):
    """Freeze eligibility and the first predeclared group fold before model fitting."""
    for member in snapshot.get('members', []):
        if (type(member.get('authority_id')) is not int or member['authority_id'] <= 0
                or not member.get('authority_version') or not member.get('authority_basis')
                or type(member.get('recorded_family_id')) is not int or member['recorded_family_id'] <= 0
                or not identifier(member.get('package_group'))
                or str(member.get('recorded_family', '')).lower() in {'', 'unknown', 'other', 'unmapped'}):
            raise ValueError('Recorded reviewed label provenance or package identity is missing')
    rows, meta = prepare_retained_av(snapshot)
    support = meta.groupby('recorded_family_id').agg(
        samples=('sample_id', 'size'), components=('lineage_component', 'nunique'))
    eligible = support.index[(support.samples >= 20) & (support.components >= 4)]
    admitted = meta[meta.recorded_family_id.isin(eligible)].copy().reset_index(drop=True)
    if len(eligible) < 2:
        raise ValueError('Fewer than two families meet 20 samples / four lineage components')
    train, test = next(StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=1337).split(
        admitted, admitted.recorded_family_id, admitted.lineage_component))
    train_ids = tuple(int(i) for i in admitted.iloc[train].sample_id)
    test_ids = tuple(int(i) for i in admitted.iloc[test].sample_id)
    rows = rows[rows.sample_id.isin(admitted.sample_id)]
    contract = fit_av_detection_contract(rows, train_ids, scope='all_observed')
    features = transform_av_detection_features(rows, contract, admitted.sample_id).set_index('sample_id')
    labels = admitted.set_index('sample_id').recorded_family_id.astype(str).rename('family_id')
    plan = AVPartition(source_digest, frame_digest(features), frame_digest(labels), train_ids, test_ids,
                       tuple((int(r.sample_id), int(r.lineage_component)) for r in admitted.itertuples()))
    plan.validate(features, labels)
    return features, labels, plan, admitted, meta, contract


def execute(snapshot_path, expected_digest, output, *, train=False, model_type="logistic_regression"):
    """Read one frozen local snapshot, validate, and optionally fit once in a new directory."""
    if model_type not in MODELS:
        raise ValueError('Unsupported development model')
    started = time.monotonic()
    snapshot_path, output = Path(snapshot_path), Path(output).resolve()
    if snapshot_path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('Snapshot exceeds 128 MiB bound')
    raw = snapshot_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError('Snapshot bytes differ from the reviewed digest')
    if output.is_relative_to(repo_root().resolve()) or output.exists():
        raise ValueError('Output must be a new directory outside the repository')
    snapshot = json.loads(raw)
    features, labels, plan, admitted, all_meta, contract = prepare(snapshot, expected_digest)
    # No output slot preparation, archival, Core persistence or database adapter.
    output.mkdir(parents=True, exist_ok=False)
    diagnostics = output / 'diagnostics'
    diagnostics.mkdir()
    (output / 'PARTITION.json').write_text(json.dumps(asdict(plan), indent=2))
    features.to_csv(output / 'FEATURES.csv')
    ledger = admitted.copy()
    ledger['partition'] = ledger.sample_id.map(lambda i: 'train' if i in plan.train_ids else 'test')
    ledger.to_csv(output / 'MEMBERSHIP.csv', index=False)
    all_meta.to_csv(output / 'SOURCE_LINEAGE.csv', index=False)
    contract.report_selection.to_csv(output / 'REPORT_SELECTION.csv', index=False)
    result = {'lineage_policy': LINEAGE_POLICY_ID, 'status': 'PLAN_ONLY', 'profile_id': PROFILE_ID,
              'claim': 'Exploratory reconstruction of recorded reviewed family attribution; shared AV-source labels, not independent ground truth',
              'source_sha256': expected_digest, 'source_samples': len(snapshot['members']),
              'admitted': len(admitted), 'families': labels.nunique(),
              'train': len(plan.train_ids), 'test': len(plan.test_ids),
              'feature_policy_hash': contract.policy_hash, 'input_features': list(features),
              'split_policy': f'first StratifiedGroupKFold(4, shuffle=True, seed=1337); {LINEAGE_POLICY_ID}',
              'limitations': ['AV-supported recorded targets are not independent ground truth',
                              'Exact similarity fingerprints do not exhaust approximate near-duplicate relationships',
                              'Retained latest reports are not an as-of temporal evaluation',
                              'One small holdout; no population-wide or paper-comparable claim'],
              'model_fitted': False, 'model_type': model_type,
              'evaluation_role': 'development comparison; previously inspected holdout, not tuning evidence'}
    if train:
        settings = {'DEFAULT_OUTPUT_DIR': str(output), 'RUNTIME_OUTPUT_ROOT_BASE': str(output),
                    'RUNTIME_RUN_ROOT': str(output), 'RUNTIME_DIAGNOSTICS_DIR': str(diagnostics),
                    'RUNTIME_PROFILE_ID': PROFILE_ID, 'RUNTIME_RUN_ID': output.name,
                    'RUNTIME_EXPERIMENT_ID': PROFILE_ID, 'RUNTIME_QUIET_TRAINING': True,
                    'RUNTIME_SPLIT_SAMPLE_METADATA': admitted.rename(columns={'package': 'package_name'}),
                    'ENABLE_DB_LOGGING': False, 'ENABLE_ML_LOGGING': False,
                    'ENABLE_CROSS_VALIDATION': False, 'ENABLE_SMOTE_OVERSAMPLING': False,
                    'ENABLE_PROBABILITY_CALIBRATION': False, 'ENABLE_LR_GRID_SEARCH': False,
                    'ENABLE_RF_GRID_SEARCH': False, 'ENABLE_XGB_GRID_SEARCH': False,
                    'ENABLE_SVM_GRID_SEARCH': False, 'ENABLE_PERMISSION_FEATURES': False,
                    'ENABLE_SAMPLE_METADATA_FEATURES': False, 'RUNTIME_ABLATION_ACTIVE': False}
        settings.update(LR_MAX_ITER=2000, LR_SOLVER='lbfgs')
        prior = {name: (hasattr(app_config, name), getattr(app_config, name, None)) for name in settings}
        try:
            for name, value in settings.items():
                setattr(app_config, name, value)
            from .model_trainer_factory import train_model_factory
            with warnings.catch_warnings():
                warnings.simplefilter('error', ConvergenceWarning)
                fitted = train_model_factory(features, labels, model_type=model_type,
                                             random_state=1337, use_smote=False,
                                             enable_grid_search=False, cross_validate=False,
                                             av_partition=plan, verbose=False,
                                             **({'early_stopping_rounds': 0} if model_type == 'xgboost' else {}))
            predictions = fitted['model'].predict(fitted['X_test'])
            encoder = fitted['label_encoder']
            names_by_id = dict(zip(admitted.recorded_family_id.astype(str), admitted.recorded_family))
            names = [names_by_id[str(i)] for i in encoder.classes_]
            classes = list(range(len(names)))
            report = classification_report(fitted['y_test'], predictions, labels=classes,
                                           target_names=names, output_dict=True, zero_division=0)
            pd.DataFrame(confusion_matrix(fitted['y_test'], predictions, labels=classes),
                         index=names, columns=names).to_csv(output / 'CONFUSION_MATRIX.csv')
            pd.DataFrame({'sample_id': fitted['sample_ids_test'],
                          'truth': [names[i] for i in fitted['y_test']],
                          'prediction': [names[i] for i in predictions]}).to_csv(output / 'PREDICTIONS.csv', index=False)
            import joblib
            joblib.dump({'model': fitted['model'], 'label_encoder': encoder,
                         'feature_columns': list(fitted['X_test']), 'source_sha256': expected_digest},
                        output / 'MODEL.joblib')
            result.update(status='EXPLORATORY_COMPLETE', model_fitted=True,
                          accuracy=accuracy_score(fitted['y_test'], predictions), classification_report=report,
                          model_parameters=fitted['model'].get_params(deep=True),
                          feature_selection=fitted['feature_selection_contract'])
        except Exception as exc:
            result.update(status='FAILED', error_type=type(exc).__name__, detail=str(exc))
            raise
        finally:
            for name, (existed, value) in prior.items():
                if existed:
                    setattr(app_config, name, value)
                else:
                    delattr(app_config, name)
            result.update(elapsed_seconds=time.monotonic()-started,
                          process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            (output / 'RESULT.json').write_text(json.dumps(result, indent=2, default=str))
    else:
        (output / 'RESULT.json').write_text(json.dumps(result, indent=2, default=str))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--snapshot-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--train', action='store_true', help='Explicitly fit one declared model after preflight')
    parser.add_argument('--model', choices=MODELS, default='logistic_regression')
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    result = execute(args.snapshot, args.snapshot_sha256, args.output, train=args.train, model_type=args.model)
    print(json.dumps({k: result[k] for k in ('status', 'admitted', 'families', 'train', 'test')}, default=str))


if __name__ == '__main__':
    main()
