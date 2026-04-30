from database import schema_map


def test_schema_table_resolution():
    assert schema_map.table("vendor_engines") == "virustotal_vendor_engines"
    assert schema_map.table("vendor_verdicts") == "virustotal_sample_vendor_engine_verdicts"


def test_schema_column_resolution():
    assert schema_map.column("vendor_engines", "engine_name") == "vendor_key"
    assert schema_map.column("vendor_engines", "trusted_flag") == "is_trusted_vendor"
    assert schema_map.column("vendor_engines", "active_flag") == "is_engine_active"
