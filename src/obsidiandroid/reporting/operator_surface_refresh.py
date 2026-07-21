"""Refresh operator-facing summaries on completed runs without rerunning the pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.diagnostics.cohort_persistence import resolve_effective_samples_df
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode
from obsidiandroid.observability.pipeline_observability.finalize import (
    patch_observability_funnel_fields,
    patch_observability_post_operator_artifacts,
)
from obsidiandroid.reporting import operator_dashboard
from obsidiandroid.reporting import research_three_questions as research_rq


def build_manifest_context_from_run_artifacts(
    *,
    manifest: Mapping[str, Any],
    observability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild a manifest_context blob from frozen run artifacts."""
    obs = observability if isinstance(observability, Mapping) else {}
    ctx: dict[str, Any] = {}

    paper_payload = manifest.get("paper_mode")
    if isinstance(paper_payload, dict):
        ctx["paper_mode"] = dict(paper_payload)
    else:
        ctx["paper_mode"] = {
            "resolved_value": bool(paper_payload),
            "source": "run_manifest",
        }

    evidence_payload = manifest.get("evidence_mode")
    if isinstance(evidence_payload, dict):
        ctx["evidence_mode"] = dict(evidence_payload)
    elif evidence_payload is not None:
        ctx["evidence_mode"] = {
            "resolved_value": bool(evidence_payload),
            "source": "run_manifest",
        }
    else:
        ctx["evidence_mode"] = dict(ctx["paper_mode"])

    for key in (
        "run_id",
        "run_mode",
        "run_slot",
        "profile_id",
        "cohort_prepared_row_count",
        "governed_cohort_rows",
        "aligned_supervised_rows",
        "post_low_support_training_rows",
        "cohort_persistence_source",
        "dataset_hash",
        "paper_locked",
        "label_authority",
        "split",
        "model_summary",
    ):
        if key in manifest and manifest.get(key) not in (None, ""):
            ctx[key] = manifest.get(key)

    if obs.get("aligned_supervised_rows") is not None and ctx.get("aligned_supervised_rows") is None:
        ctx["aligned_supervised_rows"] = obs.get("aligned_supervised_rows")
    if obs.get("post_low_support_training_rows") is not None and ctx.get("post_low_support_training_rows") is None:
        ctx["post_low_support_training_rows"] = obs.get("post_low_support_training_rows")
    if obs.get("cohort_persistence_source") and not ctx.get("cohort_persistence_source"):
        ctx["cohort_persistence_source"] = obs.get("cohort_persistence_source")
    if obs.get("dataset_hash") and not ctx.get("dataset_hash"):
        ctx["dataset_hash"] = obs.get("dataset_hash")

    split_blob = ctx.get("split")
    if not isinstance(split_blob, dict):
        split_blob = {}
        ctx["split"] = split_blob
    if obs.get("train_sample_count") is not None and split_blob.get("train_sample_count") is None:
        split_blob["train_sample_count"] = obs.get("train_sample_count")
    if obs.get("test_sample_count") is not None and split_blob.get("test_sample_count") is None:
        split_blob["test_sample_count"] = obs.get("test_sample_count")
    sci = obs.get("scientific_adequacy") if isinstance(obs.get("scientific_adequacy"), dict) else {}
    temporal_dropped = int(sci.get("temporal_future_only_rows_dropped", 0) or 0)
    if temporal_dropped > 0:
        split_blob.setdefault("temporal_split_summary", {})
        if isinstance(split_blob["temporal_split_summary"], dict):
            split_blob["temporal_split_summary"]["test_rows_dropped_unseen_train_classes"] = temporal_dropped

    if obs.get("feature_matrix_rows") is not None and ctx.get("fused_feature_rows") is None:
        ctx["fused_feature_rows"] = obs.get("feature_matrix_rows")

    return ctx


def enrich_manifest_context_funnel_fields(
    *,
    diagnostics_dir: Path,
    manifest_context: dict[str, Any],
    samples_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Load offline funnel metadata (low-support drops, support floor) into manifest_context."""
    ctx = dict(manifest_context)
    if isinstance(samples_df, pd.DataFrame):
        support_floor_mode = str(samples_df.attrs.get("support_floor_mode", "") or "").strip().lower()
        if support_floor_mode:
            ctx["support_floor_mode"] = support_floor_mode

    if not ctx.get("support_floor_mode"):
        for contract_path in sorted(diagnostics_dir.glob("label_contract_*.json")):
            contract = read_json_dict(contract_path)
            support_floor_mode = str(contract.get("support_floor_mode", "") or "").strip().lower()
            if support_floor_mode:
                ctx["support_floor_mode"] = support_floor_mode
                break

    low_support_path = diagnostics_dir / "low_support_families.csv"
    if low_support_path.is_file() and not ctx.get("low_support_family_drop_detail"):
        try:
            low_df = pd.read_csv(low_support_path)
        except Exception:
            low_df = pd.DataFrame()
        if not low_df.empty and "source" in low_df.columns:
            source_series = low_df["source"].astype(str).str.lower()
            low_df = low_df[
                source_series.str.contains("drop|excluded|training", regex=True, na=False)
                & ~source_series.str.contains("retained", regex=True, na=False)
            ]
        detail: list[dict[str, Any]] = []
        if not low_df.empty:
            family_col = "family" if "family" in low_df.columns else None
            if family_col is None and "family_canonical" in low_df.columns:
                family_col = "family_canonical"
            if "aligned_support" in low_df.columns:
                support_col = "aligned_support"
            elif "rows_in_cohort" in low_df.columns:
                support_col = "rows_in_cohort"
            else:
                support_col = "sample_count"
            for _, row in low_df.iterrows():
                family = str(row.get(family_col or "", "") or "").strip()
                if not family:
                    continue
                try:
                    support = int(row.get(support_col, 0) or 0)
                except (TypeError, ValueError):
                    support = 0
                detail.append({"family": family, "aligned_support": support})
        if detail:
            ctx["low_support_family_drop_detail"] = detail

    return ctx


def _model_results_stub_from_run_artifacts(
    *,
    manifest: Mapping[str, Any],
    observability: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Return minimal model_results + top_model for research summary refresh."""
    obs = observability if isinstance(observability, Mapping) else {}
    model_summary = manifest.get("model_summary")
    if not isinstance(model_summary, dict):
        model_summary = {}
    obs_model = obs.get("model") if isinstance(obs.get("model"), dict) else {}

    top_model = str(model_summary.get("top_model") or obs_model.get("top_model") or "random_forest").strip()
    top_model = top_model.lower().replace("-", "_")
    macro = model_summary.get("top_macro_f1")
    if macro is None:
        macro = obs_model.get("top_macro_f1")
    if macro is None:
        macro = obs_model.get("top_model_primary_metric_value")
    weighted = model_summary.get("top_weighted_f1")
    if weighted is None:
        weighted = obs_model.get("top_weighted_f1")
    accuracy = model_summary.get("top_accuracy")
    if accuracy is None:
        accuracy = obs_model.get("top_accuracy")

    evaluation = {
        "macro_f1_score": float(macro or 0.0),
        "f1_score": float(weighted or 0.0),
        "accuracy": float(accuracy or 0.0),
    }
    return {top_model: {"evaluation": evaluation}}, top_model


def _write_claim_readiness_summary_from_refreshed_artifacts(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    manifest_context: Mapping[str, Any],
    samples_df: pd.DataFrame | None,
    bundle: Mapping[str, Any],
    observability: Mapping[str, Any] | None,
) -> Path:
    """Rewrite claim_readiness_summary JSON from refreshed dataset/observability artifacts."""
    obs = observability if isinstance(observability, Mapping) else {}
    q1 = bundle.get("q1") if isinstance(bundle.get("q1"), dict) else {}
    label_strategy = q1.get("label_strategy") if isinstance(q1.get("label_strategy"), dict) else {}

    readiness_title, readiness_surface = operator_dashboard._claim_readiness_context(  # pylint: disable=protected-access
        profile_id=str(profile_id or ""),
        manifest_context=manifest_context,
        samples_df=samples_df,
    )
    split_blob = manifest_context.get("split") if isinstance(manifest_context.get("split"), dict) else {}
    temporal_summary = (
        split_blob.get("temporal_split_summary")
        if isinstance(split_blob.get("temporal_split_summary"), dict)
        else {}
    )
    readiness_heading, readiness_blockers = operator_dashboard._claim_readiness_posture(  # pylint: disable=protected-access
        bundle=dict(bundle),
        runtime_temporal_summary=temporal_summary,
    )
    dl_seed = operator_dashboard._dl_seed_readiness_context(  # pylint: disable=protected-access
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id=str(profile_id or ""),
        manifest_context=manifest_context,
    )
    from obsidiandroid.common.run_slots import is_canonical_profile

    if is_canonical_profile(str(profile_id or "")) and dl_seed.get("dl_seed_status") != "ready":
        readiness_blockers = list(readiness_blockers)
        readiness_blockers.append("DL seed handoff incomplete for canonical profile")

    claim_status = operator_dashboard._claim_status_for_surface(  # pylint: disable=protected-access
        readiness_heading,
        readiness_blockers,
        readiness_surface=readiness_surface,
    )
    primary_surface_label = operator_dashboard._claim_surface_label(  # pylint: disable=protected-access
        profile_id=str(profile_id or ""),
        readiness_surface=readiness_surface,
    )
    mc_la = manifest_context.get("label_authority") if isinstance(manifest_context, dict) else None
    active_cls = ""
    if isinstance(mc_la, dict) and mc_la.get("active_training_classes") is not None:
        active_cls = str(mc_la.get("active_training_classes"))
    eligible_family_classes = int(active_cls) if str(active_cls).isdigit() else None
    known_family_classes = int(q1.get("governed_known_family_count", 0) or 0) or None
    observed_family_classes = (
        int(
            q1.get(
                "observed_family_label_count_including_unknown",
                q1.get("families_represented", 0),
            )
            or 0
        )
        or None
    )
    visible_family_classes = known_family_classes or observed_family_classes
    modeled_family_classes = eligible_family_classes
    excluded_family_classes = None
    if known_family_classes is not None and eligible_family_classes is not None:
        excluded_family_classes = max(0, known_family_classes - eligible_family_classes)

    details_name = (
        "publication_claim_audit.md"
        if readiness_surface == "locked_publication_surface"
        else "benchmark_claim_audit.md"
        if readiness_surface in {"major_family_benchmark", "type_taxonomy_surface"}
        else "research_claim_audit.md"
    )
    family_target = str(label_strategy.get("preferred_family_target", "") or "").strip()
    type_target = str(label_strategy.get("preferred_type_target", "") or "").strip()

    payload = {
        "claim_status": claim_status,
        "claim_surface": primary_surface_label,
        "primary_surface": readiness_surface,
        "dl_seed_status": dl_seed.get("dl_seed_status"),
        "dl_seed_missing_refs": dl_seed.get("dl_seed_missing_refs"),
        "dl_seed_caveats": dl_seed.get("dl_seed_caveats"),
        "dl_handoff_summary": f"dl_handoff_summary_{run_id}.json",
        "dataset_hash": dl_seed.get("dataset_hash") or manifest_context.get("dataset_hash"),
        "cohort_persistence_source": dl_seed.get("cohort_persistence_source")
        or manifest_context.get("cohort_persistence_source"),
        "ml_vocabulary_entry_count": dl_seed.get("ml_vocabulary_entry_count"),
        "benchmark_family_support_floor": None,
        "family_claim_surface": family_target or None,
        "type_claim_surface": type_target or None,
        "permission_claim_status": "capability_analysis_layer_available",
        "publication_ready": operator_dashboard._publication_mode_active(manifest_context),  # pylint: disable=protected-access
        "paper_locked": bool(manifest_context.get("paper_locked")),
        "claim_eligible_family_classes": eligible_family_classes,
        "governed_known_family_count": known_family_classes,
        "observed_family_label_count_including_unknown": observed_family_classes,
        "visible_governed_family_classes": visible_family_classes,
        "modeled_family_classes": modeled_family_classes,
        "excluded_non_claim_family_classes": excluded_family_classes,
        "benchmark_support_excluded_samples": None,
        "benchmark_support_excluded_families": None,
        "details_artifact": details_name,
        "supported_claims": [],
        "claim_limits": [],
        "unsupported_claims": [],
        "next_review": [],
        "run_mode": str(manifest_context.get("run_mode", "") or obs.get("run_mode", "") or ""),
        "profile_id": str(profile_id or ""),
        "supervised_family_claims_suitable": bool(q1.get("supervised_family_claims_suitable", False)),
        "scientific_adequacy_posture": readiness_heading,
        "scientific_adequacy_blockers": list(readiness_blockers),
    }
    return operator_dashboard._write_claim_readiness_summary_json(  # pylint: disable=protected-access
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        payload=payload,
    )


def refresh_operator_surfaces_from_disk(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Refresh dataset foundation, claim readiness, and observability operator fields."""
    run_root = Path(run_root)
    diagnostics_dir = Path(diagnostics_dir)
    manifest_path = run_root / "run_manifest.json"
    manifest_payload = dict(manifest) if isinstance(manifest, Mapping) else read_json_dict(manifest_path)
    if not manifest_payload:
        return {"ok": False, "error": f"missing or empty manifest at {manifest_path}"}

    rid = str(run_id or manifest_payload.get("run_id", "") or "").strip()
    if not rid:
        return {"ok": False, "error": "run_id missing"}
    profile = str(profile_id or manifest_payload.get("profile_id", "") or "").strip()
    if not profile:
        return {"ok": False, "error": "profile_id missing"}

    obs_path = diagnostics_dir / "run_observability_summary.json"
    observability = read_json_dict(obs_path) if obs_path.is_file() else {}
    manifest_context = build_manifest_context_from_run_artifacts(
        manifest=manifest_payload,
        observability=observability,
    )
    samples_df = resolve_effective_samples_df(diagnostics_dir, rid, None)
    manifest_context = enrich_manifest_context_funnel_fields(
        diagnostics_dir=diagnostics_dir,
        manifest_context=manifest_context,
        samples_df=samples_df,
    )
    model_results, top_model = _model_results_stub_from_run_artifacts(
        manifest=manifest_payload,
        observability=observability,
    )

    bundle = research_rq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=rid,
        profile_id=profile,
        manifest_context=manifest_context,
        samples_df=samples_df,
        model_results=model_results,
        top_model=top_model,
    )
    claim_path = _write_claim_readiness_summary_from_refreshed_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=rid,
        profile_id=profile,
        manifest_context=manifest_context,
        samples_df=samples_df,
        bundle=bundle,
        observability=observability,
    )
    observability_patched = patch_observability_post_operator_artifacts(
        diagnostics_dir=diagnostics_dir,
        manifest=manifest_payload,
        manifest_context=manifest_context,
    )
    funnel_patched = patch_observability_funnel_fields(
        diagnostics_dir=diagnostics_dir,
        manifest=manifest_payload,
        manifest_context=manifest_context,
    )

    foundation_path = diagnostics_dir / "dataset_foundation_summary.json"
    foundation = read_json_dict(foundation_path) if foundation_path.is_file() else {}
    claim_payload = read_json_dict(claim_path) if claim_path.is_file() else {}

    return {
        "ok": True,
        "run_id": rid,
        "profile_id": profile,
        "dataset_foundation_refreshed": foundation_path.is_file(),
        "supervised_family_claims_suitable": foundation.get("supervised_family_claims_suitable"),
        "claim_readiness_refreshed": claim_path.is_file(),
        "claim_status": claim_payload.get("claim_status"),
        "publication_ready": claim_payload.get("publication_ready"),
        "claim_surface": claim_payload.get("claim_surface"),
        "observability_patched": observability_patched,
        "funnel_patched": funnel_patched,
        "cohort_funnel_plain_refreshed": bool(funnel_patched),
        "publication_mode_active": coalesce_manifest_publication_mode(manifest_context),
    }
