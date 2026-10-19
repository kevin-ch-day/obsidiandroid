"""Chunked full-catalog AV research, retaining unknowns and exact exclusions.

Source collection is separate. This consumer has no database/provider adapter.
Only reviewed label groups may train; no permission features or label writes.
"""
from collections import Counter
import gzip
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
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.features.av_lineage import LINEAGE_POLICY_ID, identifier
from obsidiandroid.features.retained_av_reports import prepare_retained_av
from obsidiandroid.features.av_detection_contract import fit_av_detection_contract, transform_av_detection_features
from obsidiandroid.vendors.retained_analysis import describe_retained_vendors
from .expanded_av_experiment import plan_population


def global_lineage(records):
    """Apply the shared versioned grouping policy across the complete catalog."""
    from obsidiandroid.features.av_lineage import lineage_components
    return lineage_components(records)


def reviewed(member):
    """Recorded authority is necessary, but does not imply independent ground truth."""
    return bool(member.get('review_status') == 'reviewed'
                and type(member.get('authority_id')) is int and member['authority_id'] > 0
                and type(member.get('recorded_family_id')) is int and member['recorded_family_id'] > 0
                and member.get('authority_version') and member.get('authority_basis')
                and identifier(member.get('package_group'))
                and member.get('governed_family_name') == member.get('effective_family_name') == member.get('recorded_family')
                and str(member.get('recorded_family','')).strip().lower() not in {'','unknown','other','unmapped'})


def _decode_chunk(source, entry):
    relative = Path(entry['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Chunk path escapes source')
    path = source / relative
    if path.is_symlink() or path.stat().st_size > 64*1024**2:
        raise ValueError('Invalid chunk path or bound')
    compressed = path.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != entry['sha256']:
        raise ValueError('Chunk digest mismatch')
    with gzip.open(path,'rb') as stream:
        blob = stream.read(64*1024**2+1)
    if len(blob) > 64*1024**2 or len(blob) != entry['json_bytes']:
        raise ValueError('Chunk decoded byte bound mismatch')
    return json.loads(blob)


def run(source, expected_digest, old_partition, old_digest, output, *, train=False):
    """Describe the whole catalog, then optionally compare fixed models by grouped CV."""
    started = time.monotonic();source=Path(source);output=Path(output).resolve()
    if output.exists() or output.is_relative_to(repo_root().resolve()):
        raise ValueError('New external output required')
    raw=(source/'SOURCE_MANIFEST.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_digest:
        raise ValueError('Source manifest changed')
    manifest=json.loads(raw)
    catalog_raw=(source/'CATALOG.json').read_bytes()
    if manifest['status']!='COMPLETE' or hashlib.sha256(catalog_raw).hexdigest()!=manifest['catalog_sha256']:
        raise ValueError('Catalog incomplete or changed')
    members=json.loads(catalog_raw)['members']
    if not 1<=len(members)<=50000 or len(members)!=manifest['samples']:
        raise ValueError('Catalog population bound invalid')
    by_id={m['sample_id']:m for m in members}
    if len(by_id)!=len(members) or len({m['sha256'] for m in members})!=len(members):
        raise ValueError('Catalog identities duplicated')
    old_raw=Path(old_partition).read_bytes()
    if hashlib.sha256(old_raw).hexdigest()!=old_digest:
        raise ValueError('Consumed evaluation manifest changed')
    consumed=json.loads(old_raw)['test_ids']
    output.mkdir(parents=True);(output/'vendor_chunks').mkdir()
    meta=[];training_rows=[];errors=[];seen=set();events=set();counts=Counter();family_counts=Counter();consensus=[]
    for number,entry in enumerate(manifest['chunks'],1):
        chunk=_decode_chunk(source,entry)
        reports={r['sha256']:r for r in chunk['reports']}
        if len(reports)!=len(chunk['reports']) or len(reports)!=entry['reports'] or len(chunk['members'])!=entry['samples']:
            raise ValueError('Chunk count mismatch')
        if not set(reports)<={m['sha256'] for m in chunk['members']}:
            raise ValueError('Orphan report')
        valid_members=[];valid_reports=[]
        for member in chunk['members']:
            sid=member['sample_id']
            if sid in seen or by_id.get(sid)!=member:
                raise ValueError('Chunk catalog identity mismatch')
            seen.add(sid)
            row={**member,'package':str(member.get('package_group') or '').strip().lower(),
                 'signer_sha1':'','vhash':'','tlsh':'','ssdeep':'','av_state':'NO_RETAINED_HTTP_200',
                 'reviewed_label':reviewed(member)}
            report=reports.get(member['sha256'])
            if report:
                event=report.get('event_id')
                if event in events:raise ValueError('Duplicate report event')
                events.add(event)
                snapshot={'format':'obsidiandroid-retained-av-development-v1','members':[member],'reports':[report]}
                try:
                    av,details=prepare_retained_av(snapshot)
                    row.update(details.iloc[0].to_dict());row['av_state']='VALIDATED_RETAINED_REPORT'
                    valid_members.append(member);valid_reports.append(report)
                    if row['reviewed_label']:training_rows.append(av)
                except (ValueError,TypeError,KeyError,AttributeError) as exc:
                    row['av_state']='INVALID_RETAINED_REPORT'
                    errors.append({'sample_id':sid,'error_type':type(exc).__name__,'detail':str(exc)})
            meta.append(row)
        if valid_members:
            snapshot={'format':'obsidiandroid-retained-av-development-v1','members':valid_members,'reports':valid_reports}
            frame,_,votes=describe_retained_vendors(snapshot)
            frame.to_csv(output/f'vendor_chunks/{number:04d}.csv.gz',index=False,compression='gzip')
            consensus.extend(votes.to_dict(orient='records'))
            counts.update(frame.groupby(['engine','category']).size().to_dict())
            family_counts.update(frame.groupby(['recorded_family','engine','category']).size().to_dict())
        if number%10==0:
            print(json.dumps({'status':'ANALYZING','samples':len(seen),'total':len(members)}),flush=True)
    if seen!=set(by_id):raise ValueError('Catalog chunks incomplete')
    groups=global_lineage(meta)
    for row in meta:row['lineage_component']=groups[row['sample_id']]
    metadata=pd.DataFrame(meta);metadata.to_csv(output/'CATALOG_COVERAGE.csv',index=False)
    pd.DataFrame(errors,columns=['sample_id','error_type','detail']).to_csv(output/'INVALID_REPORTS.csv',index=False)
    pd.DataFrame(consensus).to_csv(output/'VENDOR_CONSENSUS.csv',index=False)
    pd.DataFrame([{'engine':k[0],'category':k[1],'verdicts':v} for k,v in counts.items()]).to_csv(output/'ENGINE_CATEGORIES.csv',index=False)
    pd.DataFrame([{'recorded_family':k[0],'engine':k[1],'category':k[2],'verdicts':v} for k,v in family_counts.items()]).to_csv(output/'FAMILY_ENGINE_CATEGORIES.csv',index=False)
    candidates=metadata[metadata.reviewed_label & metadata.av_state.eq('VALIDATED_RETAINED_REPORT')].copy()
    # Entire-catalog groups, including unlabeled bridges, define consumed exclusion.
    blocked={groups[i] for i in consumed if i in groups}
    if not set(consumed)<=set(groups):raise ValueError('Consumed evaluation identities missing from catalog')
    candidates=candidates[~candidates.lineage_component.isin(blocked)]
    support=candidates.groupby('recorded_family').agg(samples=('sample_id','size'),groups=('lineage_component','nunique'))
    support.to_csv(output/'FAMILY_ELIGIBILITY.csv')
    summary={'lineage_policy':LINEAGE_POLICY_ID,'status':'CATALOG_ANALYSIS_COMPLETE','source_manifest_sha256':expected_digest,
             'samples':len(metadata),'av_states':metadata.av_state.value_counts().to_dict(),
             'reviewed_with_valid_av':int((metadata.reviewed_label & metadata.av_state.eq('VALIDATED_RETAINED_REPORT')).sum()),
             'whole_catalog_components':len(set(groups.values())),'consumed_groups':len(blocked),
             'models':{},'training_claim':'recorded-attribution grouped development CV; no independent test'}
    try:
        # Add consumed identities for the shared planner to validate and exclude.
        planning=pd.concat([candidates,metadata[metadata.sample_id.isin(consumed)]],ignore_index=True)
        selected,folds,_=plan_population(planning,consumed)
        selected.to_csv(output/'TRAINING_ELIGIBLE.csv',index=False)
        excluded=metadata[~metadata.sample_id.isin(selected.sample_id)].copy()
        excluded['exclusion_reason']=['consumed_evaluation_group' if g in blocked else
            'unreviewed_or_disagreeing_label' if not r else 'av_unavailable_or_invalid' if s!='VALIDATED_RETAINED_REPORT' else
            'family_support_or_group_floor' for g,r,s in zip(excluded.lineage_component,excluded.reviewed_label,excluded.av_state)]
        excluded.to_csv(output/'TRAINING_EXCLUSIONS.csv',index=False)
        summary.update(training_samples=len(selected),training_families=sorted(selected.recorded_family.unique()))
        if train:
            if len(selected)>3000:raise ValueError('Training population exceeds reviewed resource bound')
            av=pd.concat(training_rows,ignore_index=True)
            summary['models']=compare_models(av,selected,folds,output,expected_digest)
            summary['status']='FULL_CATALOG_AV_COMPLETE'
        else:summary['status']='FULL_CATALOG_PLAN_COMPLETE'
    except ValueError as exc:
        summary.update(status='CATALOG_COMPLETE_TRAINING_BLOCKED',blocker=str(exc))
    finally:
        summary.update(elapsed_seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        (output/'RESULT.json').write_text(json.dumps(summary,indent=2))
    return summary


def compare_models(rows,selected,folds,output,source_digest):
    """Identical predeclared folds; fold-local vocabularies/transforms; no tuning."""
    from xgboost import XGBClassifier
    from sklearn.preprocessing import LabelEncoder
    names=sorted(selected.recorded_family.unique());labels=selected.set_index('sample_id').recorded_family
    encoder=LabelEncoder().fit(names)
    models={
        'logistic_regression':lambda:make_pipeline(VarianceThreshold(0),StandardScaler(),LogisticRegression(C=1,class_weight='balanced',max_iter=2000,random_state=1337)),
        'random_forest':lambda:make_pipeline(VarianceThreshold(0),RandomForestClassifier(n_estimators=150,max_depth=12,class_weight='balanced',random_state=1337,n_jobs=1)),
        'xgboost':lambda:make_pipeline(VarianceThreshold(0),XGBClassifier(n_estimators=200,max_depth=6,learning_rate=.1,random_state=1337,n_jobs=1,eval_metric='mlogloss'))}
    ledgers=[];all_predictions={name:[] for name in models};results={name:[] for name in models}
    config={'seed':1337,'folds':3,'source_manifest_sha256':source_digest,'classes':names,
            'claim':'development CV, no holdout or hyperparameter selection','models':{name:repr(factory()) for name,factory in models.items()}}
    (output/'MODEL_CONFIG.json').write_text(json.dumps(config,indent=2))
    for number,(tr,va) in enumerate(folds,1):
        train_ids=selected.iloc[tr].sample_id.tolist();valid_ids=selected.iloc[va].sample_id.tolist()
        contract=fit_av_detection_contract(rows,train_ids,scope='all_observed')
        features=transform_av_detection_features(rows,contract,selected.sample_id).set_index('sample_id')
        folder=output/f'fold_{number}';folder.mkdir();features.to_csv(folder/'FEATURES.csv')
        ledgers.append({'fold':number,'train_ids':train_ids,'validation_ids':valid_ids,'feature_policy_hash':contract.policy_hash,'features':list(features)})
        for name,factory in models.items():
            started=time.monotonic();model=factory()
            with warnings.catch_warnings():
                warnings.simplefilter('error',ConvergenceWarning)
                model.fit(features.loc[train_ids],encoder.transform(labels.loc[train_ids]))
            predictions=encoder.inverse_transform(model.predict(features.loc[valid_ids]));prob=model.predict_proba(features.loc[valid_ids])
            pd.DataFrame(prob,index=valid_ids,columns=names).to_csv(folder/f'{name}_PROBABILITIES.csv',index_label='sample_id')
            bundle={'model':model,'label_encoder':encoder,'av_contract':contract,'source_manifest_sha256':source_digest}
            joblib.dump(bundle,folder/f'{name}.joblib')
            reloaded=joblib.load(folder/f'{name}.joblib')
            if list(encoder.inverse_transform(reloaded['model'].predict(features.loc[valid_ids])))!=list(predictions):raise ValueError('Model reload mismatch')
            metrics=classification_report(labels.loc[valid_ids],predictions,labels=names,output_dict=True,zero_division=0)
            results[name].append({'fold':number,'metrics':metrics,'elapsed_seconds':time.monotonic()-started,'retained_features':list(features.columns[model[0].get_support()]),'parameters':model.get_params(deep=True)})
            all_predictions[name].extend({'sample_id':sid,'fold':number,'truth':labels[sid],'prediction':prediction} for sid,prediction in zip(valid_ids,predictions))
            print(json.dumps({'status':'FOLD_MODEL_COMPLETE','fold':number,'model':name}),flush=True)
    (output/'FOLDS.json').write_text(json.dumps(ledgers,indent=2))
    summary={}
    for name,records in all_predictions.items():
        frame=pd.DataFrame(records)
        if frame.sample_id.duplicated().any() or set(frame.sample_id)!=set(selected.sample_id):raise ValueError('OOF identity mismatch')
        frame.to_csv(output/f'{name}_OOF.csv',index=False)
        metrics=classification_report(frame.truth,frame.prediction,labels=names,output_dict=True,zero_division=0)
        pd.DataFrame(confusion_matrix(frame.truth,frame.prediction,labels=names),index=names,columns=names).to_csv(output/f'{name}_CONFUSION.csv')
        (output/f'{name}_RESULT.json').write_text(json.dumps({'folds':results[name],'pooled_oof_metrics':metrics},indent=2,default=str))
        summary[name]=metrics
    return summary
