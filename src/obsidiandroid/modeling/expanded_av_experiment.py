"""Bounded three-fold development CV over exact retained AV evidence.

No independent holdout, tuning, permission features, provider calls or DB writes.
The consumed prior evaluation population and connected groups are excluded.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import time
import warnings

import joblib
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_selection import VarianceThreshold
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.features.av_lineage import LINEAGE_POLICY_ID, identifier
from obsidiandroid.features.retained_av_reports import prepare_retained_av
from obsidiandroid.features.av_detection_contract import fit_av_detection_contract, transform_av_detection_features


def plan_population(metadata, excluded_ids):
    """Exclude connected old evaluation groups, then apply fixed support floors."""
    if not excluded_ids or not set(excluded_ids) <= set(metadata.sample_id):
        raise ValueError('Prior evaluation identities are absent or incomplete')
    blocked = set(metadata.loc[metadata.sample_id.isin(excluded_ids), 'lineage_component'])
    eligible = metadata.loc[~metadata.lineage_component.isin(blocked)].copy()
    support = eligible.groupby('recorded_family').agg(
        samples=('sample_id', 'size'), groups=('lineage_component', 'nunique'))
    names = support.index[(support.samples >= 20) & (support.groups >= 4)]
    selected = eligible[eligible.recorded_family.isin(names)].sort_values('sample_id').reset_index(drop=True)
    if len(names) < 3:
        raise ValueError('Fewer than three eligible families')
    folds = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=1337).split(
        selected, selected.recorded_family, selected.lineage_component))
    for train, valid in folds:
        if set(selected.iloc[train].lineage_component) & set(selected.iloc[valid].lineage_component):
            raise ValueError('Lineage crosses fold')
        for indices, minimum in [(train, 10), (valid, 3)]:
            counts = selected.iloc[indices].recorded_family.value_counts()
            if set(counts.index) != set(names) or counts.min() < minimum:
                raise ValueError('Predeclared fold class support infeasible')
    return selected, folds, blocked


def execute(snapshot_path, digest, old_partition_path, old_partition_digest, output, *, train=False):
    """Plan, then optionally fit one fixed LR baseline per validated grouped fold."""
    started = time.monotonic()
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(repo_root().resolve()):
        raise ValueError('A new external output directory is required')
    source = Path(snapshot_path)
    if source.stat().st_size > 128 * 1024**2:
        raise ValueError('Snapshot exceeds byte bound')
    raw = source.read_bytes(); old_raw = Path(old_partition_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest or hashlib.sha256(old_raw).hexdigest() != old_partition_digest:
        raise ValueError('Source or excluded partition digest differs')
    snapshot = json.loads(raw)
    for m in snapshot['members']:
        if (m.get('review_status') != 'reviewed' or not m.get('authority_id')
                or not m.get('authority_version') or not m.get('authority_basis')
                or not identifier(m.get('package_group'))
                or m.get('governed_family_name') != m.get('recorded_family')
                or m.get('effective_family_name') != m.get('recorded_family')
                or str(m.get('recorded_family', '')).lower() in {'', 'unknown', 'other', 'unmapped'}):
            raise ValueError('Reviewed agreeing label authority required')
    rows, metadata = prepare_retained_av(snapshot)
    old = json.loads(old_raw)
    selected, folds, blocked = plan_population(metadata, old['test_ids'])
    output.mkdir(parents=True)
    selected.to_csv(output/'ELIGIBLE.csv', index=False)
    exclusions = metadata.loc[~metadata.sample_id.isin(selected.sample_id)].copy()
    exclusions['reason'] = exclusions.lineage_component.map(
        lambda g: 'connected_to_consumed_holdout' if g in blocked else 'family_support_or_components')
    exclusions.to_csv(output/'EXCLUDED.csv', index=False)
    names = sorted(selected.recorded_family.unique())
    config = {'lineage_policy':LINEAGE_POLICY_ID,'seed':1337, 'folds':3, 'model':'StandardScaler + LogisticRegression',
              'variance_threshold':0, 'C':1.0, 'class_weight':'balanced', 'max_iter':2000,
              'family_minimum':20, 'component_minimum':4, 'fold_train_minimum':10,
              'fold_validation_minimum':3, 'source_sha256':digest,
              'excluded_partition_sha256':old_partition_digest,
              'claim':'training-only grouped development CV; no independent test or tuning'}
    (output/'CONFIG.json').write_text(json.dumps(config,indent=2))
    config_digest=hashlib.sha256((output/'CONFIG.json').read_bytes()).hexdigest()
    summary={'status':'PLAN_ONLY','samples':len(selected),'families':names,'config_sha256':config_digest,'folds':[]}
    predictions=[]
    try:
        for number,(tr,va) in enumerate(folds,1):
            train_ids=selected.iloc[tr].sample_id.tolist();valid_ids=selected.iloc[va].sample_id.tolist()
            fold={'fold':number,'train_ids':train_ids,'validation_ids':valid_ids}
            contract=fit_av_detection_contract(rows,train_ids,scope='all_observed')
            features=transform_av_detection_features(rows,contract,selected.sample_id).set_index('sample_id')
            fold['feature_policy_hash']=contract.policy_hash;fold['features']=list(features)
            summary['folds'].append(fold)
            if not train: continue
            folder=output/f'fold_{number}';folder.mkdir()
            y=selected.set_index('sample_id').recorded_family
            model=make_pipeline(VarianceThreshold(0),StandardScaler(),LogisticRegression(
                C=1.0,class_weight='balanced',solver='lbfgs',max_iter=2000,random_state=1337))
            with warnings.catch_warnings():
                warnings.simplefilter('error',ConvergenceWarning)
                model.fit(features.loc[train_ids],y.loc[train_ids])
            predicted=model.predict(features.loc[valid_ids]);prob=model.predict_proba(features.loc[valid_ids])
            pd.DataFrame(prob,index=valid_ids,columns=model.classes_).to_csv(folder/'PROBABILITIES.csv',index_label='sample_id')
            for sid,pred in zip(valid_ids,predicted):
                predictions.append({'sample_id':sid,'fold':number,'truth':y[sid],'prediction':pred})
            fold['metrics']=classification_report(y.loc[valid_ids],predicted,labels=names,output_dict=True,zero_division=0)
            fold['retained_features']=list(features.columns[model[0].get_support()])
            pd.DataFrame(confusion_matrix(y.loc[valid_ids],predicted,labels=names),index=names,columns=names).to_csv(folder/'CONFUSION.csv')
            features.to_csv(folder/'FEATURES.csv')
            joblib.dump({'model':model,'av_contract':contract,'config_sha256':config_digest},folder/'MODEL.joblib')
            restored=joblib.load(folder/'MODEL.joblib')['model']
            if list(restored.predict(features.loc[valid_ids])) != list(predicted):
                raise ValueError('Saved model replay mismatch')
        if train:
            frame=pd.DataFrame(predictions)
            if frame.sample_id.duplicated().any() or set(frame.sample_id)!=set(selected.sample_id):
                raise ValueError('CV predictions do not partition eligible population')
            frame.to_csv(output/'OOF_PREDICTIONS.csv',index=False)
            summary['pooled_oof_metrics']=classification_report(frame.truth,frame.prediction,labels=names,output_dict=True,zero_division=0)
            summary['status']='DEVELOPMENT_CV_COMPLETE'
    except Exception as exc:
        summary.update(status='FAILED',error_type=type(exc).__name__,detail=str(exc));raise
    finally:
        summary.update(elapsed_seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        (output/'RESULT.json').write_text(json.dumps(summary,indent=2))
    return summary
