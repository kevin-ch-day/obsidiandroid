from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.hostile_audit import permission_signal_quality as psq


def test_write_permission_signal_quality_rebuilds_permission_frame_silently(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_permission_rows(_sample_ids):
        return pd.DataFrame(columns=["sample_id", "permission_string"])

    def fake_build_permission_enrichment_frame(samples_df, feature_flags, **kwargs):
        captured["log_frame_built"] = kwargs.get("log_frame_built")
        return pd.DataFrame(
            {
                "sample_id": samples_df["sample_id"].tolist(),
                "perm__android_permission_internet": [1.0] * len(samples_df),
                "perm__total_count": [1] * len(samples_df),
            }
        )

    monkeypatch.setattr(psq, "_fetch_permission_rows", fake_fetch_permission_rows)
    monkeypatch.setattr(psq, "build_permission_enrichment_frame", fake_build_permission_enrichment_frame)

    csv_path, md_path = psq.write_permission_signal_quality(
        diagnostics_dir=tmp_path,
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["FamA", "FamB"],
            }
        ),
    )

    assert captured["log_frame_built"] is False
    assert csv_path and csv_path.is_file()
    assert md_path and md_path.is_file()
