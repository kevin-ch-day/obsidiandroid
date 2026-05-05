"""Tests for sample-level vendor record indexing fast path."""

from __future__ import annotations

from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord
from ml_classification.builder import vendor_record_selector


def test_select_best_vendor_record_uses_preindexed_records() -> None:
    """Selector should work with pre-index map even when vendor map is empty."""
    rec = VendorClassificationRecord(
        sample_id="1001",
        vendor_name="trusted_vendor",
        original_label="trojan.example",
        confidence_score=0.9,
        parser_quality="high",
        is_known_family=True,
    )

    selected = vendor_record_selector.select_best_vendor_record(
        sample_id="1001",
        records_by_vendor={},
        records_by_sample_id={"1001": [rec]},
        verbose=False,
    )

    assert selected.sample_id == "1001"
    assert selected.vendor_name == "trusted_vendor"
