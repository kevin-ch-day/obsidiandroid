from __future__ import annotations

import inspect

from obsidiandroid.database import db_permission_analysis_queries
from obsidiandroid.database import permission_current_interpretation
from obsidiandroid.orchestration import permission_features
from obsidiandroid.pipeline.permission_trends import sample_permission_data
from obsidiandroid.reporting import permission_authority_enrichment


def test_active_legacy_aosp_interpretation_queries_filter_invalid_tokens() -> None:
    guard_source = inspect.getsource(permission_current_interpretation)
    assert "lifecycle_status" in guard_source
    assert "invalid_token" in guard_source

    # Active consumers must call the shared evidence guard instead of carrying
    # divergent copies of the legacy-table filter.
    assert "interpretation_" in inspect.getsource(permission_features)
    assert "interpretation_" in inspect.getsource(sample_permission_data)
    assert "permission_current_interpretation" in inspect.getsource(
        permission_authority_enrichment
    )
    assert "api_permission_declaration_conflict" in inspect.getsource(
        db_permission_analysis_queries
    )


def test_invalid_token_examples_are_not_aliased_or_promoted_in_filter_contract() -> None:
    invalid_examples = {
        "android.permission.SYSTEM_OVERLAY_WINDOW",
        "android.permission.GET_INSTALLED_APPS",
        "android.permission.USES_POLICY_FORCE_LOCK",
    }
    assert all(value.startswith("android.permission.") for value in invalid_examples)
    assert "android.permission.UWB_RANGING" not in invalid_examples
