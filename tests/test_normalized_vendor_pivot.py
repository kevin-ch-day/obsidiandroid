from obsidiandroid.database.normalized_vendor_pivot import pivot_vendor_verdicts


def test_pivot_preserves_wide_cell_semantics() -> None:
    rows = [
        {"sample_id": 1, "vendor_key": "engine_a", "verdict_label": "Trojan.A", "verdict_category": "malicious"},
        {"sample_id": 1, "vendor_key": "engine_b", "verdict_label": None, "verdict_category": "undetected"},
        {"sample_id": 2, "vendor_key": "unknown", "verdict_label": "x", "verdict_category": None},
    ]
    assert pivot_vendor_verdicts(rows, ("engine_a", "engine_b")) == {
        1: {"engine_a": "Trojan.A", "engine_b": "undetected"},
        2: {"engine_a": None, "engine_b": None},
    }
