from __future__ import annotations

from types import SimpleNamespace

from obsidiandroid.database.permission_intel_v1.__main__ import run_probe


class _Adapter:
    def __init__(self) -> None:
        self.lookups: list[str] = []

    def read_catalog_gate(self):
        return SimpleNamespace(
            state=SimpleNamespace(value="COMPATIBLE_INCOMPLETE_SCOPE"),
            shadow_available=True,
            diagnostic_codes=("source_scope_explicitly_incomplete",),
            catalog_status=SimpleNamespace(
                catalog_release_id="release-1",
                schema_contract_version="1.0.0-draft",
                exhaustive_scope=False,
            ),
        )

    def get_permission(self, value: str):
        self.lookups.append(value)
        if value == "android.permission.INTERNET":
            return SimpleNamespace(
                authority_class=SimpleNamespace(value="AOSP_PUBLIC")
            )
        return None

    def get_split_relations(self, _value: str):
        return ()

    def get_source_evidence(self, _value: str):
        return ({"fact_type": "declaration"},)


def test_probe_exercises_gate_exact_case_and_evidence_reads() -> None:
    adapter = _Adapter()
    payload = run_probe(adapter, "android.permission.INTERNET")

    assert payload["status"] == "PASS"
    assert payload["exact_match"] is True
    assert payload["case_folded_match"] is False
    assert payload["authority_class"] == "AOSP_PUBLIC"
    assert payload["source_evidence_count"] == 1
    assert adapter.lookups == [
        "android.permission.INTERNET",
        "android.permission.internet",
    ]
