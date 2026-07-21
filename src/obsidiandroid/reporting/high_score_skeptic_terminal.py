"""Terminal rendering for high-score skeptic audit bundles."""

from __future__ import annotations

from typing import Any, Callable, Mapping


def print_scope_of_headline_score_terminal(skeptic: Mapping[str, Any], *, pr: Callable[[str], None], du: Any) -> None:
    """Print governed vs trainable headline task boundary (run first)."""
    scope = skeptic.get("scope") or {}
    gov = scope.get("governed_cohort") or {}
    tt = scope.get("trainable_family_classification_task") or {}
    du.print_section("SCOPE OF HEADLINE SCORE")
    pr("Governed cohort:")
    pr(f"  Samples: {gov.get('samples', '—')}")
    pr(f"  Families: {gov.get('families', '—')}")
    pr(f"  Types: {gov.get('malware_types', '—')}")
    pr("")
    pr("Trainable family-classification task:")
    pr(f"  Samples after support filtering: {tt.get('samples_after_support_filter', '—')}")
    pr(f"  Families after support filtering: {tt.get('families_after_support_filter', '—')}")
    pr(f"  Samples dropped before training: {tt.get('samples_dropped_before_training', '—')}")
    pr(f"  Families dropped before training (est.): {tt.get('families_dropped_before_training_est', '—')}")
    pr("")
    pr("Interpretation:")
    pr(f"  {scope.get('interpretation', '')}")
    pr("")
    pr("Why this matters:")
    pr(f"  {scope.get('why_this_matters', '')}")
    pr("")


def print_skeptic_audit_followup_terminal(bundle: dict[str, Any], *, pr: Callable[[str], None], du: Any) -> None:
    """Print high-score skeptic blocks after MODEL AND FAMILY FAILURE (not scope)."""
    scope = bundle.get("scope") or {}
    tt = scope.get("trainable_family_classification_task") or {}
    hm = bundle.get("headline_metrics") or {}
    mk = str(
        bundle.get("model_key")
        or (bundle.get("high_score_audit") or {}).get("headline_model")
        or "random_forest"
    )
    du.print_section("WHY IS PERFORMANCE THIS HIGH?")
    pr("Headline model:")
    pr(f"  Model: {mk}")
    pr(f"  Accuracy: {float(hm.get('accuracy') or 0):.4f}")
    pr(f"  Macro-F1: {float(hm.get('macro_f1') or 0):.4f}")
    pr(f"  Weighted F1: {float(hm.get('weighted_f1') or 0):.4f}")
    pr(f"  Test samples: {hm.get('test_samples', '—')}")
    pr(f"  Trainable families: {tt.get('families_after_support_filter', '—')}")
    pr("")
    pr("Possible inflation factors:")
    for block in (bundle.get("high_score_audit") or {}).get("possible_inflation_factors") or []:
        tag = block.get("tag", "")
        pr(f"  [{tag}]")
        for ln in block.get("lines") or []:
            pr(f"    {ln}")
    pr("")
    pr("Interpretation:")
    pr(f"  {(bundle.get('high_score_audit') or {}).get('interpretation', '')}")
    pr("")

    fa = bundle.get("false_attribution") or {}
    du.print_section("FALSE ATTRIBUTION AUDIT")
    pr(f"Holdout mis-predictions: {fa.get('holdout_wrong_predictions', '—')} | confidence: {'yes' if fa.get('confidence_available') else 'no'}")
    if fa.get("note"):
        pr(f"Note: {fa['note']}")
    pr("")
    pr("Most over-predicted families (by false positives on holdout):")
    for row in (fa.get("top_fp_families") or [])[:8]:
        pr(
            f"  {row.get('predicted_family')}: FP={row.get('false_positives')} TP={row.get('true_positives')} "
            f"fp_rate={float(row.get('fp_rate') or 0):.3f}"
        )
    pr("")
    pr("Most missed true families (false negatives):")
    for row in (fa.get("top_fn_families") or [])[:8]:
        pr(
            f"  {row.get('true_family')}: FN={row.get('false_negatives')} recall={float(row.get('recall') or 0):.3f} "
            f"support={row.get('support_holdout')}"
        )
    pr("")
    pr("Top holdout confusion pairs (true → pred):")
    for row in (fa.get("top_confusion_pairs") or [])[:8]:
        pr(
            f"  {row.get('true_family')} → {row.get('predicted_family')}: n={row.get('count')} "
            f"same_type={row.get('shared_type', '?')}"
        )
    pr("")
    pr("Files: false_positive_by_predicted_family.csv, false_negative_by_true_family.csv, "
        "high_confidence_wrong_predictions.csv, top_confusion_pairs.csv")
    pr("")

    sc = bundle.get("split_contamination") or {}
    du.print_section("SPLIT CONTAMINATION CHECK")
    pr(f"Exact SHA overlap train/test: {sc.get('sha_overlap_train_test', '—')}")
    pr(f"Package names in both splits: {sc.get('package_names_in_both_splits', '—')}")
    pr(f"Two-segment package prefix in both: {sc.get('package_prefix_two_segment_overlap', '—')}")
    pr(f"Family + package pairs in both: {sc.get('family_package_pairs_in_both', '—')}")
    pr(f"Samples on overlapping packages: {sc.get('samples_affected_by_package_overlap', '—')}")
    pr(f"Families affected by package overlap: {sc.get('families_affected_by_package_overlap', '—')}")
    pr("")
    pr("Interpretation:")
    pr(f"  {sc.get('interpretation', '')}")
    pr("")

    sm = bundle.get("smote") or {}
    snap = sm.get("smote_snapshot") if isinstance(sm.get("smote_snapshot"), dict) else {}
    du.print_section("SMOTE EFFECT CHECK")
    pr(f"With SMOTE/ROS (headline): Macro-F1 ≈ {float(hm.get('macro_f1') or 0):.4f} | Acc ≈ {float(hm.get('accuracy') or 0):.4f}")
    pr("Without SMOTE: (not auto-run — see smote_effect_check.md / re-run with "
       "`OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE=1` or oversampling disabled)")
    if snap:
        pr(f"Snapshot: original_train_n={snap.get('original_train_n')} post_resample_train_n={snap.get('post_resample_train_n')} "
            f"method={snap.get('method')} k_neighbors={snap.get('k_neighbors', '—')}")
    pr("")

    lc = bundle.get("leakage_comparison") or {}
    du.print_section("LEAKAGE-SAFE SCORE COMPARISON")
    pr(f"Headline eval Macro-F1: {float(hm.get('macro_f1') or 0):.4f}")
    for row in (lc.get("rows") or [])[:12]:
        pr(
            f"  {row.get('feature_set_label')}: Macro-F1={row.get('macro_f1')} "
            f"(headline_eval − row = {row.get('delta_vs_headline_macro_f1')})"
        )
    if lc.get("note"):
        pr(f"  ({lc['note']})")
    pr("")

    fm = bundle.get("feature_modality") or {}
    du.print_section("TOP FEATURE MODALITY AUDIT (RF)")
    mass = fm.get("importance_mass_by_modality") or {}
    if mass:
        pr("Importance mass by bucket: " + ", ".join(f"{k}={v:.5f}" for k, v in sorted(mass.items(), key=lambda kv: -kv[1])))
    else:
        pr("(No RF importances in payload.)")
    pr("")
    if float(hm.get("macro_f1") or 0) >= 0.85:
        du.print_section("RECOMMENDED HARDER VALIDATION")
        pr("  1. package_grouped split")
        pr("  2. family_package_grouped split")
        pr("  3. time split by first_seen / VT timestamps")
        pr("  4. no-SMOTE baseline")
        pr("  5. leakage-safe fused model (vendor_parsed_no_family + permissions)")
        pr("See recommended_validation_plan.md")
        pr("")


def print_skeptic_audit_terminal(bundle: dict[str, Any], *, pr: Callable[[str], None], du: Any) -> None:
    """Print full skeptical audit (scope + follow-up); prefer split calls from research terminal."""
    print_scope_of_headline_score_terminal(bundle, pr=pr, du=du)
    print_skeptic_audit_followup_terminal(bundle, pr=pr, du=du)
