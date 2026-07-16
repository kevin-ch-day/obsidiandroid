from __future__ import annotations

from datetime import datetime, timezone

from obsidiandroid.pipeline import sample_exports


def test_run_date_eod_contract_uses_next_midnight_for_exclusive_end(monkeypatch) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(sample_exports, "datetime", FixedDatetime)
    monkeypatch.setattr(sample_exports.app_config, "ENABLE_PAPER_TIME_WINDOW", True, raising=False)
    monkeypatch.setattr(sample_exports.app_config, "PAPER_TIME_WINDOW_END_MODE", "run_date_eod_utc", raising=False)

    contract = sample_exports.resolve_dataset_time_contract(gates={}, run_id="r1")

    assert contract["window_semantics"] == "start_inclusive_end_exclusive"
    assert contract["end_utc"] == "2026-07-16T00:00:00Z"
