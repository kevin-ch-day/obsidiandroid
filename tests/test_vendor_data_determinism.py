import pandas as pd

from analysis.execution.vendor_record_factory import create_vendor_record
from database import db_fetch_av_engine_raw_results as fetcher


def _dummy_parser(label, metadata=None):
    raise AssertionError("Parser should not be called for missing labels")


def test_vendor_record_factory_treats_nan_label_as_missing():
    row = pd.Series(
        {
            "sample_id": 101,
            "family_name": "FluBot",
            "Avast": float("nan"),
        }
    )
    result = create_vendor_record(row, "Avast", _dummy_parser, parser_mode="column")
    assert result["record"] is None
    assert result["error"] == "LabelMissingOrEmpty"


def test_vendor_record_factory_treats_null_token_as_missing():
    row = pd.Series(
        {
            "sample_id": 102,
            "family_name": "FluBot",
            "Avast": " NULL ",
        }
    )
    result = create_vendor_record(row, "Avast", _dummy_parser, parser_mode="column")
    assert result["record"] is None
    assert result["error"] == "LabelMissingOrEmpty"


def test_db_fetch_deduplicates_by_latest_record():
    raw = pd.DataFrame(
        [
            {"sample_id": 1, "record_id": 10, "updated_at": "2026-01-01 10:00:00", "avast": "old"},
            {"sample_id": 1, "record_id": 12, "updated_at": "2026-01-01 11:00:00", "avast": "new"},
            {"sample_id": 2, "record_id": 20, "updated_at": "2026-01-01 10:00:00", "avast": "stable"},
        ]
    )

    out = fetcher._deduplicate_sample_rows(raw, verbose=False)
    assert out["sample_id"].tolist() == [1, 2]
    assert out.loc[out["sample_id"] == 1, "avast"].iloc[0] == "new"
