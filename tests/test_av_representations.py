import pandas as pd
import pytest
from obsidiandroid.modeling.av_representations import av_representation


def test_detection_missing_is_not_completed_negative():
    frame=pd.DataFrame({'avobs__engine':[0,1,1],'avdet__engine':[0,0,1]})
    detection=av_representation(frame,'detection')
    assert pd.isna(detection.iloc[0,0])
    assert detection.iloc[1,0]==0 and detection.iloc[2,0]==1
    assert av_representation(frame,'observation').iloc[:,0].tolist()==[0,1,1]
    assert av_representation(frame,'combined').equals(frame)


def test_semantic_predictors_and_unpaired_features_rejected():
    with pytest.raises(ValueError,match='namespaces'):
        av_representation(pd.DataFrame({'family':['Joker']}),'combined')
    with pytest.raises(ValueError,match='pairs'):
        av_representation(pd.DataFrame({'avdet__engine':[1]}),'detection')
