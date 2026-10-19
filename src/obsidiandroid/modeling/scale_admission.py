"""Plan-only scale gate: candidate counts never imply a legitimate fitted model."""
from dataclasses import dataclass, asdict

from sklearn.model_selection import StratifiedGroupKFold

from obsidiandroid.features.av_lineage import LINEAGE_POLICY_ID


@dataclass(frozen=True)
class ScaleDesign:
    minimum_final_fit_samples: int = 1000
    minimum_family_samples: int = 20
    minimum_family_groups: int = 4
    minimum_fold_train_per_class: int = 10
    minimum_fold_validation_per_class: int = 3
    folds: int = 3
    seed: int = 1337


def preview_scale(metadata, consumed_ids, design=ScaleDesign()):
    """Return exact eligible/fold identities and blocking reasons, without fitting.

    Input metadata must already carry validated authority, AV and whole-catalog
    lineage. Final refit is only contemplated after feasible development CV; no
    independent test population is established by this helper.
    """
    required={'sample_id','sha256','recorded_family','lineage_component','reviewed_label','av_state'}
    if not required<=set(metadata):
        raise ValueError('Scale source metadata incomplete')
    if metadata.sample_id.duplicated().any() or metadata.sha256.duplicated().any():
        raise ValueError('Scale identities duplicated')
    if not consumed_ids or not set(consumed_ids)<=set(metadata.sample_id):
        raise ValueError('Consumed evaluation identities incomplete')
    if design.minimum_final_fit_samples<1000 or design.folds<3:
        raise ValueError('Scale floor cannot be silently reduced')
    blocked=set(metadata.loc[metadata.sample_id.isin(consumed_ids),'lineage_component'])
    pool=metadata[metadata.reviewed_label.eq(True) & metadata.av_state.eq('VALIDATED_RETAINED_REPORT') & ~metadata.lineage_component.isin(blocked)].copy()
    support=pool.groupby('recorded_family').agg(samples=('sample_id','size'),groups=('lineage_component','nunique'))
    names=sorted(support.index[(support.samples>=design.minimum_family_samples)&(support.groups>=design.minimum_family_groups)])
    candidate=pool[pool.recorded_family.isin(names)].sort_values('sample_id').reset_index(drop=True)
    result={'status':'NO_GO','lineage_policy':LINEAGE_POLICY_ID,'design':asdict(design),
            'candidate_samples':len(candidate),'class_universe':names,'actual_fitted_samples':0,
            'independent_test_established':False,'candidate_ids':candidate.sample_id.tolist(),
            'folds':[],'blockers':[]}
    if len(candidate)<design.minimum_final_fit_samples:
        result['blockers'].append('Candidate population below 1000 distinct final-fit samples')
    if len(names)<2:
        result['blockers'].append('Fewer than two supported families');return result
    cv=StratifiedGroupKFold(n_splits=design.folds,shuffle=True,random_state=design.seed)
    for number,(train,valid) in enumerate(cv.split(candidate,candidate.recorded_family,candidate.lineage_component),1):
        training=candidate.iloc[train];validation=candidate.iloc[valid]
        if set(training.lineage_component)&set(validation.lineage_component):
            raise ValueError('Group leakage in scale plan')
        entry={'fold':number,'train_ids':training.sample_id.tolist(),'validation_ids':validation.sample_id.tolist(),
               'train_samples':len(training),'validation_samples':len(validation),
               'train_class_support':{name:int((training.recorded_family==name).sum()) for name in names},
               'validation_class_support':{name:int((validation.recorded_family==name).sum()) for name in names}}
        result['folds'].append(entry)
        for name in names:
            if entry['train_class_support'][name]<design.minimum_fold_train_per_class:
                result['blockers'].append(f'Fold {number}: {name} has fewer than {design.minimum_fold_train_per_class} training samples')
            if entry['validation_class_support'][name]<design.minimum_fold_validation_per_class:
                result['blockers'].append(f'Fold {number}: {name} has fewer than {design.minimum_fold_validation_per_class} validation samples')
    if not result['blockers']:result['status']='PLAN_FEASIBLE_NOT_FITTED'
    return result
