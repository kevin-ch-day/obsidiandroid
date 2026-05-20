"""Tests for permission-type figure diagnostics output hygiene."""

from __future__ import annotations

import json

import pandas as pd

from config import app_config
from obsidiandroid.diagnostics.research_validity import type_permission_figures as tpf
from obsidiandroid.pipeline import stage_feature_enrichment as sfe


def test_type_permission_figures_uses_global_latest_for_jsd_diagnostics(
    make_run_diagnostics_layout,
    monkeypatch,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "banker", "stealer"],
            "family_canonical": ["FamA", "FamB", "FamZero"],
        }
    )
    frame = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "perm__android_permission_internet": [1.0, 0.0, 0.0],
            "perm__android_permission_camera": [0.0, 1.0, 0.0],
            "perm__android_permission_contacts": [0.0, 0.0, 0.0],
            "perm__android_permission_sms": [0.0, 0.0, 0.0],
            "perm__dangerous_count": [1, 1, 0],
            "perm__normal_count": [0, 0, 0],
            "perm__oem_count": [0, 0, 0],
            "perm__total_count": [1, 1, 1],
            "perm_grp__network": [1.0, 0.0, 0.0],
            "perm_grp__privacy": [0.0, 1.0, 0.0],
        }
    )
    monkeypatch.setattr(sfe, "build_permission_enrichment_frame", lambda *args, **kwargs: frame)

    artifacts: list[str] = []
    tpf.write_type_permission_figure_bundle(
        diagnostics_dir=diagnostics_dir,
        samples_df=samples_df,
        artifact_list=artifacts,
    )

    canonical = diagnostics_dir / "permission_jsd_degenerate_diagnostics_rid.json"
    global_latest = output_root / "diagnostics" / "permission_jsd_degenerate_diagnostics.latest.json"
    assert canonical.is_file()
    assert not (diagnostics_dir / "permission_jsd_degenerate_diagnostics.latest.json").exists()
    assert global_latest.is_file()

    payload = json.loads(canonical.read_text(encoding="utf-8"))
    assert payload["run_id"] == "rid"
    assert payload["skipped_degenerate_pair_count"] >= 1
    assert str(canonical) in artifacts
    assert str(global_latest) in artifacts
