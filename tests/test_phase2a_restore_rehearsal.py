"""Pure transform tests for the disposable Phase 2A restore tool."""

from scripts.core_migration.phase2a_restore_rehearsal import _transform_line


def test_transform_removes_only_dump_database_selection_lines() -> None:
    replacements = {"erebus_threat_intel_prod": "od_phase2a_restore_20260719_erebus", "android_permission_intel": "od_phase2a_restore_20260719_permission"}
    assert _transform_line("CREATE DATABASE /*!32312 IF NOT EXISTS*/ `erebus_threat_intel_prod`;\n", replacements) is None
    assert _transform_line("USE `erebus_threat_intel_prod`;\n", replacements) is None


def test_transform_retargets_qualified_view_and_trigger_references() -> None:
    replacements = {"erebus_threat_intel_prod": "od_phase2a_restore_20260719_erebus", "android_permission_intel": "od_phase2a_restore_20260719_permission"}
    view = _transform_line("select * from `erebus_threat_intel_prod`.`analysis_run` join `android_permission_intel`.`android_permission_dict_unknown`;\n", replacements)
    trigger = _transform_line("/*!50003 TRIGGER erebus_threat_intel_prod.trg_x BEFORE INSERT */\n", replacements)
    trigger_target = _transform_line("BEFORE INSERT ON erebus_threat_intel_prod.android_malware_family\n", replacements)
    assert "`od_phase2a_restore_20260719_erebus`." in view
    assert "`od_phase2a_restore_20260719_permission`." in view
    assert "TRIGGER od_phase2a_restore_20260719_erebus." in trigger
    assert "ON od_phase2a_restore_20260719_erebus.android_malware_family" in trigger_target


def test_transform_retargets_restore_only_definer_to_local_root() -> None:
    line = _transform_line(
        "/*!50017 DEFINER=`erebus_app`@`localhost`*/ /*!50003 VIEW `v_x` AS select 1 */\n",
        {"android_permission_intel": "od_phase2a_restore_20260719_permission"},
    )
    assert "DEFINER=`root`@`localhost`" in line
    assert "erebus_app" not in line
