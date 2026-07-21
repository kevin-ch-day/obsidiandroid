"""Synthetic tests for package-balanced permission analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.reporting import package_balanced_permission_analysis as mod
from obsidiandroid.reporting.package_balanced_permission_analysis import (
    LINEAGE_BALANCE_UNAVAILABLE,
    assign_package_keys,
    build_family_package_concentration,
    build_package_collision_audit,
    build_source_batch_concentration,
    classify_package_collision,
    classify_package_concentration_state,
    compute_hhi,
    effective_package_count,
    family_balanced_prevalence,
    normalize_package_name,
    package_balanced_prevalence,
    package_within_family_balanced_prevalence,
    sample_weighted_prevalence,
)


def test_package_normalization_and_missing_keys() -> None:
    assert normalize_package_name("  Com.Example.App ") == "com.example.app"
    assert normalize_package_name("") == ""
    assert normalize_package_name(None) == ""
    labels = pd.DataFrame(
        [
            {"sample_id": 1, "package_name": "com.a", "android_package_name": "", "sha256": "x", "family_canonical": "F", "type_slug": "rat"},
            {"sample_id": 2, "package_name": "", "android_package_name": "", "sha256": "y", "family_canonical": "F", "type_slug": "rat"},
            {"sample_id": 3, "package_name": "", "android_package_name": "", "sha256": "z", "family_canonical": "F", "type_slug": "rat"},
        ]
    )
    keyed = assign_package_keys(labels)
    assert keyed.loc[0, "package_key"] == "com.a"
    assert keyed.loc[1, "is_missing_package"]
    assert keyed.loc[2, "is_missing_package"]
    assert keyed.loc[1, "package_key"] != keyed.loc[2, "package_key"]
    assert keyed.loc[1, "package_key"].startswith("__missing_package__:")


def test_one_package_many_samples_and_many_packages_one_sample() -> None:
    labels = pd.DataFrame(
        [
            {"sample_id": i, "package_name": "com.same", "family_canonical": "DevLike", "type_slug": "rat", "sha256": f"h{i}", "source_batch_label": "b"}
            for i in range(10)
        ]
        + [
            {"sample_id": 100 + i, "package_name": f"com.p{i}", "family_canonical": "ClayLike", "type_slug": "rat", "sha256": f"p{i}", "source_batch_label": "b"}
            for i in range(10)
        ]
    )
    conc = build_family_package_concentration(labels)
    dev = conc[conc.family_canonical == "DevLike"].iloc[0]
    clay = conc[conc.family_canonical == "ClayLike"].iloc[0]
    assert dev.concentration_state == "single_package_dominated"
    assert clay.known_package_count == 10
    assert clay.largest_package_share <= 0.11


def test_weighting_schemes_and_missing_exclusion() -> None:
    frame = pd.DataFrame(
        [
            {"sample_id": 1, "package_name": "com.a", "family_canonical": "F1", "type_slug": "rat", "is_missing_package": False, "package_key": "com.a", "perm": 1},
            {"sample_id": 2, "package_name": "com.a", "family_canonical": "F1", "type_slug": "rat", "is_missing_package": False, "package_key": "com.a", "perm": 1},
            {"sample_id": 3, "package_name": "com.b", "family_canonical": "F1", "type_slug": "rat", "is_missing_package": False, "package_key": "com.b", "perm": 0},
            {"sample_id": 4, "package_name": "", "family_canonical": "F2", "type_slug": "rat", "is_missing_package": True, "package_key": "__missing_package__:4", "perm": 1},
            {"sample_id": 5, "package_name": "com.c", "family_canonical": "F2", "type_slug": "rat", "is_missing_package": False, "package_key": "com.c", "perm": 0},
        ]
    )
    sw = sample_weighted_prevalence(frame, "perm")
    pb = package_balanced_prevalence(frame, "perm")
    fb = family_balanced_prevalence(frame, "perm")
    pwf = package_within_family_balanced_prevalence(frame, "perm")
    assert abs(sw - 0.6) < 1e-9
    # known packages a,b,c → prevalences 1,0,0 → mean 1/3
    assert abs(pb - (1 / 3)) < 1e-9
    assert pb != sw
    assert pd.notna(fb) and pd.notna(pwf)


def test_collision_cross_family_and_cross_type() -> None:
    assert classify_package_collision(family_count=2, type_count=1, sha_count=2) == "cross_family_collision"
    assert classify_package_collision(family_count=1, type_count=2, sha_count=2) == "cross_type_collision"
    labels = pd.DataFrame(
        [
            {"sample_id": 1, "package_name": "com.x", "family_canonical": "A", "type_slug": "rat", "sha256": "1", "source_batch_label": "b1"},
            {"sample_id": 2, "package_name": "com.x", "family_canonical": "B", "type_slug": "banker", "sha256": "2", "source_batch_label": "b2"},
        ]
    )
    audit = build_package_collision_audit(labels)
    hit = audit[audit.sample_count == 2].iloc[0]
    assert hit.collision_class == "cross_family_collision"
    assert "package_key" not in audit.columns
    assert "com.x" not in str(audit.values)


def test_hhi_effective_count_and_states() -> None:
    assert abs(compute_hhi([10]) - 1.0) < 1e-9
    assert effective_package_count([10]) == 1.0
    assert (
        classify_package_concentration_state(
            sample_count=100,
            known_package_count=90,
            known_package_samples=100,
            largest_package_share=0.02,
            hhi=0.01,
        )
        == "broad_package_diversity"
    )
    assert (
        classify_package_concentration_state(
            sample_count=100,
            known_package_count=1,
            known_package_samples=30,
            largest_package_share=1.0,
            hhi=1.0,
        )
        == "single_package_dominated"
    )


def test_source_batch_and_lineage_unavailable() -> None:
    labels = pd.DataFrame(
        [
            {"sample_id": 1, "package_name": "com.a", "family_canonical": "F", "type_slug": "rat", "sha256": "1", "source_batch_label": "zimperium_ioc"},
            {"sample_id": 2, "package_name": "com.b", "family_canonical": "F", "type_slug": "rat", "sha256": "2", "source_batch_label": "zimperium_ioc"},
            {"sample_id": 3, "package_name": "com.c", "family_canonical": "G", "type_slug": "banker", "sha256": "3", "source_batch_label": "other"},
        ]
    )
    batch = build_source_batch_concentration(labels)
    assert not batch.empty
    assert LINEAGE_BALANCE_UNAVAILABLE == "lineage_balance_unavailable"


def test_deterministic_ordering() -> None:
    labels = pd.DataFrame(
        [
            {"sample_id": 2, "package_name": "com.b", "family_canonical": "B", "type_slug": "rat", "sha256": "2", "source_batch_label": "b"},
            {"sample_id": 1, "package_name": "com.a", "family_canonical": "A", "type_slug": "banker", "sha256": "1", "source_batch_label": "a"},
        ]
    )
    a = build_package_collision_audit(labels)
    b = build_package_collision_audit(labels.sample(frac=1.0, random_state=0))
    assert list(a.package_key_hash) == list(b.package_key_hash)


def test_module_has_no_db_or_core_access() -> None:
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "execute_permission_query" not in src
    assert "execute_core_query" not in src
    assert "INSERT INTO" not in src.upper()
    assert "CREATE TABLE" not in src.upper()


def test_compose_refuses_banned_dirs(tmp_path: Path) -> None:
    run = tmp_path / "run"
    diag = run / "diagnostics"
    diag.mkdir(parents=True)
    (run / ".COMPLETE").write_text("{}", encoding="utf-8")
    # Minimal fixtures to pass verify would be heavy; just test ban check path by
    # invoking banned name resolution via compose guard after patching verify.
    import obsidiandroid.reporting.package_balanced_permission_analysis as m

    old = m.verify_completed_run

    def fake_verify(run_root, expected_run_id="x"):
        return {
            "run_id": "20260721T142432Z__07f657",
            "profile_id": "android_malware_all_current",
            "repository_commit": "abc",
            "prepared_sample_count": 9716,
            "permission_bearing_sample_count": 9457,
        }

    m.verify_completed_run = fake_verify  # type: ignore[assignment]
    try:
        banned = diag / "type_permission_protection_enriched"
        banned.mkdir()
        try:
            m.compose_package_balanced_permission_analysis(
                run_root=run,
                output_dir=banned,
                load_features=False,
            )
            raised = False
        except RuntimeError:
            raised = True
        assert raised
    finally:
        m.verify_completed_run = old  # type: ignore[assignment]
