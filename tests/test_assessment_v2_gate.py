"""The deployed-style assessment reader cannot bypass a blocked PI V2 gate."""

from obsidiandroid.assessment.source import ReadOnlyEvidenceReader


SHA = "a" * 64


def test_assessment_blocks_direct_legacy_observation_read():
    reader = object.__new__(ReadOnlyEvidenceReader)
    queried = []

    def read(name, sql, params=()):
        queried.append(name)
        if name.endswith(":catalog"):
            return [{"sample_id": 7, "sha256": SHA}]
        if name.endswith(":permission_research_gate"):
            return [{"legacy_observation_reads": "BLOCK"}]
        return []

    reader.read = read
    evidence = reader.collect(SHA)
    assert not any(name.endswith(":permission_observations") for name in queried)
    assert evidence["permissions"]["availability"] == "error"
    assert evidence["permissions"]["observations"] == []
    assert "permission_observations:V2_RESEARCH_GATE_BLOCKED" in evidence["errors"]
