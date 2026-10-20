"""Explicit AV representations; absent observations are not observed negatives."""
import pandas as pd


def av_representation(features, mode):
    """Produce a frozen-vocabulary view; detection missingness stays NaN.

    Detection-only requires train-fitted imputation downstream. Combined features
    retain both bits, so avobs=0 distinguishes the structural avdet=0 placeholder
    from a completed negative verdict. No semantic labels are accepted.
    """
    observations=[c for c in features if c.startswith('avobs__')]
    detections=[c for c in features if c.startswith('avdet__')]
    if len(observations)+len(detections)!=len(features.columns):
        raise ValueError('AV representation rejects non-binary-feature namespaces')
    if not features.columns.is_unique or not features.isin([0,1]).all().all():
        raise ValueError('AV representation requires unique binary features')
    engines={c.removeprefix('avobs__') for c in observations}
    if engines!={c.removeprefix('avdet__') for c in detections}:
        raise ValueError('Observation/detection pairs differ')
    if mode=='combined':return features.copy()
    if mode=='observation':return features[observations].copy()
    if mode=='detection':
        result=features[detections].astype(float).copy()
        for column in detections:
            engine=column.removeprefix('avdet__')
            result.loc[features['avobs__'+engine].eq(0),column]=float('nan')
        return result
    raise ValueError('Unsupported AV representation')
