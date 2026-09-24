from obsidiandroid.diagnostics.assessment_gaps import format_explanation


def test_static_projection_is_distinct_from_legacy_gap():
    report = {
        "artifact_sha256": "a" * 64,
        "revision": 2,
        "assessment_id": "b" * 64,
        "processing_status": "complete_with_unresolved_fields",
        "scope": "Stored only",
        "static_declaration_projection": {
            "file_sha256": "c" * 64,
            "summary": {
                "accounted_count": 8,
                "declared_count": 8,
                "semantically_resolved_count": 7,
                "unresolved_count": 1,
                "invalid_or_non_permission_count": 0,
            },
        },
        "gaps": [
            {
                "code": "PERMISSION_EVIDENCE_UNAVAILABLE",
                "owner": "Provider observations",
                "reason": "Missing provider observations",
                "next_step": "Retain separate provenance",
            }
        ],
    }
    text = format_explanation(report)
    assert "8/8" in text and "7 resolved; 1 unresolved" in text
    assert "legacy provider observations remain separate" in text
    assert "PERMISSION_EVIDENCE_UNAVAILABLE" in text
