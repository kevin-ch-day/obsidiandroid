import os
import tempfile
from pathlib import Path

import pandas as pd
import numpy as np
from zipfile import BadZipFile

from obsidiandroid.evaluation import evaluate_av_classifications
from obsidiandroid.evaluation import vendor_feature_extractor
from obsidiandroid.modeling import pipeline_core
from obsidiandroid.pipeline import score_av_engines
from obsidiandroid.reporting import export_manager


def test_export_dataframe_to_excel_creates_file(monkeypatch):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    with tempfile.TemporaryDirectory() as tmpdir:
        output_root = Path(tmpdir) / "out"
        monkeypatch.setattr(export_manager, "OUTPUT_ROOT", output_root)
        os.makedirs(export_manager.OUTPUT_ROOT, exist_ok=True)
        path = export_manager.export_dataframe_to_excel(df, "test.xlsx", sheet_name="Sheet1")
        assert os.path.isfile(path)


def test_export_dataframe_to_excel_compact_emits_single_summary(monkeypatch, capsys):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    monkeypatch.setattr(export_manager.app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(export_manager.app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        output_root = Path(tmpdir) / "out"
        monkeypatch.setattr(export_manager, "OUTPUT_ROOT", output_root)
        os.makedirs(export_manager.OUTPUT_ROOT, exist_ok=True)
        export_manager.export_dataframe_to_excel(df, "test.xlsx", sheet_name="Sheet1", preview_rows=0)
        out = capsys.readouterr().out
    assert "[EXPORT] consolidated: test.xlsx -> obsidiandroid_outputs.xlsx" in out
    assert "(1" in out and "sheet)" in out
    assert "Exported:" not in out


def test_save_structured_classification_report_uses_export(monkeypatch):
    df = pd.DataFrame({"sample_id": ["s1"], "predicted_family": ["foo"]})
    captured = {}

    def fake_export(dframe, filename, sheet_name, preview_rows):
        captured["called"] = True
        return "dummy.xlsx"

    monkeypatch.setattr(export_manager, "export_dataframe_to_excel", fake_export)
    path = export_manager.save_structured_classification_report(df)
    assert captured.get("called") is True
    assert path == "dummy.xlsx"


def test_export_dataframe_to_excel_locked_consolidated_returns_empty(monkeypatch):
    df = pd.DataFrame({"a": [1]})
    monkeypatch.setattr(export_manager, "ENABLE_CONSOLIDATED_WORKBOOK", True)

    def fail_consolidated(*args, **kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(export_manager, "_export_to_consolidated", fail_consolidated)
    path = export_manager.export_dataframe_to_excel(df, "locked.xlsx", sheet_name="Sheet1", preview_rows=0)
    assert str(path).endswith(".xlsx")


def test_write_excel_file_locked_consolidated_returns_empty(monkeypatch):
    frames = {"Sheet1": pd.DataFrame({"a": [1]})}
    monkeypatch.setattr(export_manager, "ENABLE_CONSOLIDATED_WORKBOOK", True)

    def fail_write(*args, **kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(export_manager, "_write_consolidated_batch", fail_write)
    path = export_manager.write_excel_file(frames, "locked_multi.xlsx")
    assert path == ""


def test_write_excel_file_compact_emits_single_summary(monkeypatch, capsys):
    frames = {
        "Sheet1": pd.DataFrame({"a": [1]}),
        "Sheet2": pd.DataFrame({"b": [2]}),
    }
    monkeypatch.setattr(export_manager.app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(export_manager.app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        output_root = Path(tmpdir) / "out"
        monkeypatch.setattr(export_manager, "OUTPUT_ROOT", output_root)
        os.makedirs(export_manager.OUTPUT_ROOT, exist_ok=True)
        export_manager.write_excel_file(frames, "multi.xlsx")
        out = capsys.readouterr().out
    assert "[EXPORT] consolidated: multi.xlsx -> obsidiandroid_outputs.xlsx" in out
    assert "(2" in out and "sheets)" in out
    assert "Excel file saved:" not in out


def test_export_vendor_results_skips_raw_excel_when_disabled(monkeypatch):
    summary_df = pd.DataFrame({"vendor": ["a"], "score": [1.0]})
    parsed_data = {"AhnLab": pd.DataFrame({"sample_id": [1], "Parsed Family": ["x"]})}
    captured = {}

    def fake_write(dataframes, filename):
        captured["filename"] = filename
        captured["sheets"] = list(dataframes.keys())
        return "ok.xlsx"

    monkeypatch.setattr(export_manager, "write_excel_file", fake_write)
    monkeypatch.setattr(export_manager, "EXPORT_VENDOR_RAW_SHEETS_TO_EXCEL", False)
    monkeypatch.setattr(export_manager, "EXPORT_VENDOR_RAW_ARTIFACTS", False)

    path = export_manager.export_vendor_results(parsed_data, summary_df)

    assert path == "ok.xlsx"
    assert captured["filename"] == export_manager.FILE_VENDOR_RESULTS
    assert captured["sheets"] == ["Vendor_Summary"]


def test_alias_generation_is_collision_safe_for_truncated_names():
    used = set()
    aliases = []
    logical = "vendor_parser_results__VeryLongVendorNameThatWillBeTruncatedInExcelSheetName"
    for idx in range(1, 201):
        df = pd.DataFrame({"value": [idx], "name": [logical]})
        alias = export_manager._resolve_unique_alias(
            logical_name=logical,
            df=df,
            occurrence=idx,
            used_aliases=used,
        )
        aliases.append(alias)

    assert len(aliases) == 200
    assert len(set(aliases)) == 200


def test_alias_generation_is_deterministic_for_same_inputs():
    logical = "vendor_parser_results__DuplicateName"
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    a1 = export_manager._alias_for_entry(logical, df, occurrence=1, nonce=0)
    a2 = export_manager._alias_for_entry(logical, df, occurrence=1, nonce=0)
    assert a1 == a2


def test_export_dataframe_corruption_locked_uses_fallback_workbook(monkeypatch):
    df = pd.DataFrame({"a": [1]})
    monkeypatch.setattr(export_manager, "ENABLE_CONSOLIDATED_WORKBOOK", True)
    monkeypatch.setattr(
        export_manager,
        "_export_to_consolidated",
        lambda *args, **kwargs: (_ for _ in ()).throw(BadZipFile("Bad CRC-32 for file 'docProps/core.xml'")),
    )
    monkeypatch.setattr(export_manager, "_quarantine_corrupted_workbook", lambda *_: None)
    monkeypatch.setattr(export_manager, "_write_sheet", lambda *args, **kwargs: "alias123")

    path = export_manager.export_dataframe_to_excel(
        df,
        "bad.xlsx",
        sheet_name="Sheet1",
        preview_rows=0,
    )
    assert str(path).endswith(".xlsx")
    assert "obsidiandroid_outputs__" in str(path)


def test_write_excel_corruption_locked_uses_fallback_workbook(monkeypatch):
    frames = {"Sheet1": pd.DataFrame({"a": [1]})}
    monkeypatch.setattr(export_manager, "ENABLE_CONSOLIDATED_WORKBOOK", True)
    monkeypatch.setattr(export_manager, "_quarantine_corrupted_workbook", lambda *_: None)

    def fake_batch(path, sheets):
        if path.name == export_manager.CONSOLIDATED_FILENAME:
            raise BadZipFile("Bad CRC-32 for file 'docProps/core.xml'")
        return [("alias123", sheets[0][0], int(sheets[0][1].shape[0]))]

    monkeypatch.setattr(export_manager, "_write_consolidated_batch", fake_batch)
    path = export_manager.write_excel_file(frames, "bad_multi.xlsx")
    assert str(path).endswith(".xlsx")
    assert "obsidiandroid_outputs__" in str(path)


def test_export_confusion_matrix_uses_run_scoped_name(monkeypatch, tmp_path):
    monkeypatch.setattr(export_manager, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ID", "20260228T184458Z__634d83", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_EXPERIMENT_ID", "", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ROOT", "", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)

    captured = {}

    def fake_export(**kwargs):
        captured["output_path"] = kwargs["output_path"]
        kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"].write_bytes(b"PNG")
        return str(kwargs["output_path"])

    monkeypatch.setattr(export_manager, "export_confusion_matrix_image", fake_export)
    path = export_manager.export_confusion_matrix(
        cm=np.array([[1, 0], [0, 1]]),
        class_labels=["A", "B"],
        model_name="random_forest",
    )
    output_path = Path(path)
    assert output_path.name == "confusion_matrix_random_forest.png"
    assert output_path.parent == tmp_path / "runs" / "20260228T184458Z__634d83" / "conf_matrices"
    assert captured["output_path"].name == "random_forest.png"
    assert captured["output_path"].parent.name == "headline"


def test_export_confusion_matrix_includes_experiment_id(monkeypatch, tmp_path):
    monkeypatch.setattr(export_manager, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ID", "20260228T184458Z__634d83", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_EXPERIMENT_ID", "vendor_only", raising=False)

    monkeypatch.setattr(
        export_manager,
        "export_confusion_matrix_image",
        lambda **kwargs: str(kwargs["output_path"]),
    )
    path = Path(
        export_manager.export_confusion_matrix(
            cm=np.array([[1, 0], [0, 1]]),
            class_labels=["A", "B"],
            model_name="xgboost",
        )
    )
    assert path.name == "confusion_matrix_vendor_only__xgboost.png"


def test_ablation_random_forest_never_overwrites_headline_stable_alias(monkeypatch, tmp_path):
    """``confusion_matrix_random_forest.png`` must remain headline-only; ablation must not clobber it."""
    rid = "20260228T184458Z__634d83"
    monkeypatch.setattr(export_manager, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ID", rid, raising=False)
    monkeypatch.setattr(
        export_manager.app_config,
        "RUNTIME_EXPERIMENT_ID",
        "vendor_full__lt_family_canonical_default",
        raising=False,
    )
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(export_manager.app_config, "CONFUSION_MATRIX_EXPORT_MODE", "full_grid", raising=False)

    cm_dir = tmp_path / "runs" / rid / "conf_matrices"
    cm_dir.mkdir(parents=True, exist_ok=True)
    canon = cm_dir / "confusion_matrix_random_forest.png"
    canon.write_bytes(b"HEADLINE_STABLE")

    def fake_export(**kwargs):
        p = Path(kwargs["output_path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"ABLATION_CELL")
        return str(p)

    monkeypatch.setattr(export_manager, "export_confusion_matrix_image", fake_export)
    export_manager.export_confusion_matrix(
        cm=np.array([[1, 0], [0, 1]]),
        class_labels=["A", "B"],
        model_name="random_forest",
    )
    assert canon.read_bytes() == b"HEADLINE_STABLE"


def test_export_confusion_matrix_filename_excludes_run_id(monkeypatch, tmp_path):
    monkeypatch.setattr(export_manager, "OUTPUT_ROOT", tmp_path)
    run_id = "20260304T003828Z__bcfc09"
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_EXPERIMENT_ID", "permissions_only", raising=False)
    monkeypatch.setattr(
        export_manager,
        "export_confusion_matrix_image",
        lambda **kwargs: str(kwargs["output_path"]),
    )
    path = Path(
        export_manager.export_confusion_matrix(
            cm=np.array([[1, 0], [0, 1]]),
            class_labels=["A", "B"],
            model_name="logistic_regression",
        )
    )
    assert run_id not in path.name


def test_export_confusion_matrix_uses_dynamic_default_output_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(export_manager.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ID", "20260304T003828Z__bcfc09", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_EXPERIMENT_ID", "", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ROOT", "", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(
        export_manager,
        "export_confusion_matrix_image",
        lambda **kwargs: (
            kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True),
            kwargs["output_path"].write_bytes(b"PNG"),
            str(kwargs["output_path"]),
        )[-1],
    )

    path = Path(
        export_manager.export_confusion_matrix(
            cm=np.array([[1, 0], [0, 1]]),
            class_labels=["A", "B"],
            model_name="xgboost",
        )
    )
    assert path.parent == tmp_path / "output" / "runs" / "20260304T003828Z__bcfc09" / "conf_matrices" / "headline"


def test_export_confusion_matrix_uses_slot_run_root_when_active(monkeypatch, tmp_path):
    run_id = "20260304T003828Z__bcfc09"
    slot_root = tmp_path / "output" / "runs" / "allcurrent_diagnostic"
    monkeypatch.setattr(export_manager.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_RUN_ROOT", str(slot_root), raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_EXPERIMENT_ID", "", raising=False)
    monkeypatch.setattr(export_manager.app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(
        export_manager,
        "export_confusion_matrix_image",
        lambda **kwargs: (
            kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True),
            kwargs["output_path"].write_bytes(b"PNG"),
            str(kwargs["output_path"]),
        )[-1],
    )

    path = Path(
        export_manager.export_confusion_matrix(
            cm=np.array([[1, 0], [0, 1]]),
            class_labels=["A", "B"],
            model_name="xgboost",
        )
    )
    assert path.parent == slot_root / "conf_matrices" / "headline"
    assert not (tmp_path / "output" / "runs" / run_id / "conf_matrices").exists()


def test_export_manager_shared_import_aliases_point_to_module() -> None:
    """Ensure major pipeline modules import the shared export manager module."""
    assert evaluate_av_classifications.em is export_manager
    assert vendor_feature_extractor.em is export_manager
    assert score_av_engines.em is export_manager
    assert pipeline_core.em is export_manager


def test_apply_scoring_defaults_tolerates_none_engine_thresholds(monkeypatch) -> None:
    from config import app_config

    monkeypatch.setattr(app_config, "ENGINE_MIN_SAMPLES_SCANNED", None, raising=False)
    monkeypatch.setattr(app_config, "ENGINE_MIN_COVERAGE_PCT", None, raising=False)
    monkeypatch.setattr(app_config, "ENGINE_MIN_POSITIVE_FLAGS", None, raising=False)
    monkeypatch.setattr(app_config, "ENGINE_MIN_DETECTION_PCT", None, raising=False)

    cfg = score_av_engines.apply_scoring_defaults({})
    assert cfg["min_engine_detections"] == 10
    assert cfg["min_coverage_pct"] == 20.0
    assert cfg["min_positive_flags"] == 5
    assert cfg["min_detection_pct"] == 1.0
