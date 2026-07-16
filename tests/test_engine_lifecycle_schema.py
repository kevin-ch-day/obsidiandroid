import pandas as pd

from obsidiandroid.pipeline.engine_lifecycle_schema import (
    DEPRECATED_READINESS_FLAG,
    READINESS_FLAG,
    add_readiness_compatibility_columns,
    readiness_mask,
)


def test_v2_lifecycle_keeps_deprecated_readiness_alias() -> None:
    out = add_readiness_compatibility_columns(
        pd.DataFrame({DEPRECATED_READINESS_FLAG: [True, False]})
    )
    assert out[READINESS_FLAG].tolist() == [True, False]
    assert out[DEPRECATED_READINESS_FLAG].tolist() == [True, False]
    assert out["deprecated_included_in_model_flag"].all()


def test_readiness_mask_reads_legacy_artifact() -> None:
    frame = pd.DataFrame({DEPRECATED_READINESS_FLAG: [False, True]})
    assert readiness_mask(frame).tolist() == [False, True]
