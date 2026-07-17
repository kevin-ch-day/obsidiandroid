"""Operator-facing terminal layout for headline ML evaluation and ablation summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console


def should_defer_headline_training_terminal() -> bool:
    """Return True when per-model training noise should defer to the consolidated summary."""
    if ml_console.is_debug():
        return False
    if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
        return False
    if bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False)):
        return False
    return ml_console.is_compact()


def should_quiet_headline_training_preamble() -> bool:
    """Return True when pre-training step banners and distributions should be suppressed."""
    return should_defer_headline_training_terminal()


def should_suppress_ablation_feature_build_terminal() -> bool:
    """Return True when ablation matrix builds should not spam per-set build logs."""
    if ml_console.is_debug():
        return False
    if not bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
        return False
    return ml_console.is_compact()


def format_run_relative_path(path_like: str | Path) -> str:
    """Return a run-root-relative path for terminal display when possible."""
    resolved = Path(path_like).resolve()
    runtime_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if runtime_root:
        try:
            return resolved.relative_to(Path(runtime_root).resolve()).as_posix()
        except ValueError:
            pass
    return du.format_console_path(resolved)


def tier_code_only(tier_text: str | None) -> str:
    """Extract a short tier code such as ``T6`` from a tier label."""
    token = str(tier_text or "").strip()
    if not token:
        return "—"
    return token.split(" - ", 1)[0].strip() or token


def tier_readable(tier_text: str | None) -> str:
    """Return a concise operator-facing tier phrase."""
    token = str(tier_text or "").strip()
    if not token:
        return "—"
    code = tier_code_only(token)
    descriptions = {
        "T1": "elite headline performance",
        "T2": "very strong headline performance",
        "T3": "strong headline performance",
        "T4": "moderate headline performance",
        "T5": "mixed headline performance",
        "T6": "usable baseline; long-tail performance remains uneven",
        "T7": "weak but functional; review tail-family balance",
        "T8": "limited baseline quality",
        "T9": "poor baseline quality",
        "T10": "critically weak baseline quality",
    }
    return descriptions.get(code, token.split(" - ", 1)[-1].strip().lower() or token)


def claim_surface_label_for_profile(profile_id: str | None = None) -> str:
    """Return the human-readable claim surface label for terminal summaries."""
    profile = str(
        profile_id or getattr(app_config, "RUNTIME_PROFILE_ID", "") or ""
    ).strip()
    evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))
    paper_mode = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
    if evidence_mode or paper_mode:
        return "Locked publication cohort"
    if profile == "android_malware_all_current":
        return "Current-corpus diagnostic surface"
    if profile == "android_malware_major_families":
        return "Support-gated benchmark cohort"
    if profile == "android_malware_expanded_families":
        return "Expanded-family exploratory cohort"
    if profile == "android_malware_type_taxonomy":
        return "Type taxonomy benchmark"
    return "Benchmark research surface"


def resolve_claim_surface_label(manifest_context: dict[str, Any] | None = None) -> str:
    """Resolve claim-surface wording from manifest context or profile defaults."""
    for source in (manifest_context, getattr(app_config, "RUNTIME_MANIFEST_CONTEXT", None)):
        if not isinstance(source, dict):
            continue
        token = str(source.get("claim_surface_label", "") or "").strip()
        if token:
            return token
    return claim_surface_label_for_profile()


def interpretation_for_macro_f1(
    macro_f1: float | None,
    *,
    weighted_f1: float | None = None,
    accuracy: float | None = None,
) -> str:
    """Return a short research-honest interpretation line for the headline metric."""
    macro = float(macro_f1 or 0.0)
    weighted = float(weighted_f1 or 0.0)
    acc = float(accuracy or 0.0)
    if weighted >= 0.90 and macro < 0.75:
        return (
            "Strong dominant-family performance, but Macro-F1 remains the claim metric "
            "because family concentration is high."
        )
    if acc >= 0.90 and macro < 0.70:
        return (
            "Accuracy is high, but Macro-F1 remains the claim metric because family "
            "concentration is high."
        )
    if macro >= 0.75:
        return "Usable supervised baseline with reasonable family-balance signal."
    if macro >= 0.65:
        return "Functional baseline; review weaker families and feature trust sources."
    return "Macro-F1 remains below a stable family-balance baseline; review features and labels."


def _fmt_metric(value: Any, *, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _profile_and_run_context() -> tuple[str, str, str]:
    profile_id = str(getattr(app_config, "RUNTIME_PROFILE_ID", "") or "").strip()
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
    slot = str(getattr(app_config, "RUNTIME_RUN_SLOT", "") or "").strip()
    profile_surface = slot or profile_id or "unknown"
    label_field = str(
        getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id") or "family_id"
    ).strip()
    return profile_surface, run_id, label_field


def build_terminal_manifest_context(manifest_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge runner manifest context with runtime training counters for terminal display."""
    ctx: dict[str, Any] = {}
    if isinstance(manifest_context, dict):
        ctx.update(manifest_context)
    runtime_manifest = getattr(app_config, "RUNTIME_MANIFEST_CONTEXT", None)
    if isinstance(runtime_manifest, dict):
        for key, value in runtime_manifest.items():
            ctx.setdefault(key, value)

    aligned = ctx.get("aligned_supervised_rows")
    if aligned is None:
        aligned = getattr(app_config, "RUNTIME_ALIGNED_ROWS_BEFORE_LOW_SUPPORT_FILTER", None)
    if aligned is not None:
        ctx["aligned_supervised_rows"] = aligned

    postls = ctx.get("post_low_support_training_rows")
    if postls is None:
        postls = getattr(app_config, "RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS", None)
    if postls is not None:
        ctx["post_low_support_training_rows"] = postls

    gov = ctx.get("cohort_prepared_row_count")
    if gov is None:
        gov = ctx.get("fused_feature_rows")
    if gov is None:
        gov = aligned
    if gov is not None:
        ctx["cohort_prepared_row_count"] = gov

    split_meta = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
    if isinstance(split_meta, dict):
        ctx.setdefault("train_sample_count", split_meta.get("train_sample_count"))
        ctx.setdefault("test_sample_count", split_meta.get("test_sample_count"))
    return ctx


def format_population_terminal_lines(manifest_context: dict[str, Any] | None) -> list[str]:
    """Return multiline cohort/split summary rows for terminal display."""
    manifest_context = build_terminal_manifest_context(manifest_context)
    if not manifest_context:
        return []

    gov = manifest_context.get("cohort_prepared_row_count")
    aligned = manifest_context.get("aligned_supervised_rows")
    postls = manifest_context.get("post_low_support_training_rows")
    tr = manifest_context.get("train_sample_count")
    te = manifest_context.get("test_sample_count")
    modeled_families = getattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", None)
    visible_families = getattr(app_config, "RUNTIME_COHORT_FAMILY_COUNT", None)
    if gov is None or aligned is None or postls is None:
        return []

    excluded_rows = max(0, int(aligned) - int(postls))
    excluded_families = getattr(app_config, "RUNTIME_BENCHMARK_SUPPORT_EXCLUDED_FAMILY_COUNT", None)
    if excluded_families in (None, ""):
        detail = getattr(app_config, "RUNTIME_LOW_SUPPORT_FAMILY_DROP_DETAIL", None)
        if isinstance(detail, list):
            excluded_families = len(detail)
    lines = [
        f"Governed cohort       : {int(gov):,}",
        f"Aligned supervised    : {int(aligned):,}",
        f"Trainable pool        : {int(postls):,}",
    ]
    if tr is not None and te is not None:
        lines.append(f"Train / test split    : {int(tr):,} / {int(te):,}")
    if visible_families not in (None, "", 0):
        lines.append(f"Visible families      : {int(visible_families)}")
    if modeled_families not in (None, "", "-"):
        lines.append(f"Modeled families      : {int(modeled_families)}")
    if excluded_rows > 0:
        family_text = (
            f"{excluded_rows:,} rows / {int(excluded_families)} families"
            if excluded_families not in (None, "", 0)
            else f"{excluded_rows:,} rows"
        )
        lines.append(f"Support exclusions    : {family_text}")
    return lines


def _unknown_prediction_line(results: dict[str, dict], model_key: str) -> str | None:
    payload = results.get(model_key, {})
    if not isinstance(payload, dict):
        return None
    predictions = payload.get("predictions")
    if not isinstance(predictions, dict) or not predictions:
        return None
    total = len(predictions)
    unknown = 0
    for label in predictions.values():
        token = str(label).strip().lower()
        if token in {"unknown", "other"}:
            unknown += 1
    return f"{unknown:,} / {total:,} ({(unknown / total if total else 0.0):.2%})"


def _confidence_range_line(evaluation: dict[str, Any]) -> str | None:
    confidences = evaluation.get("confidences")
    if confidences is None:
        return None
    try:
        series = pd.Series(list(confidences), dtype="float64")
        if series.empty:
            return None
        return f"{series.min():.2f} → {series.max():.2f}"
    except Exception:
        return None


def _collect_training_runtime_sec(results: dict[str, dict]) -> float | None:
    total = 0.0
    seen = False
    for payload in results.values():
        if not isinstance(payload, dict):
            continue
        evaluation = payload.get("evaluation", {})
        if not isinstance(evaluation, dict):
            continue
        train_time = evaluation.get("train_time")
        if train_time is None:
            continue
        try:
            total += float(train_time)
            seen = True
        except (TypeError, ValueError):
            continue
    return total if seen else None


def _artifact_lines(
    *,
    results: dict[str, dict],
    top_model: str,
    run_id: str,
    training_runtime_sec: float | None,
) -> list[str]:
    lines: list[str] = [f"Promoted model: {top_model}"]
    export_paths = {}
    payload = results.get(top_model, {})
    if isinstance(payload, dict):
        maybe_paths = payload.get("export_paths")
        if isinstance(maybe_paths, dict):
            export_paths = maybe_paths

    model_path = export_paths.get("model_path")
    metadata_path = export_paths.get("metadata_path")
    if training_runtime_sec is not None:
        lines.append(f"Training runtime: {du.format_elapsed_duration(training_runtime_sec)}")
    lines.append("")
    lines.append("Model artifacts")
    if model_path:
        lines.append(f"Model: {format_run_relative_path(model_path)}")
    if metadata_path:
        lines.append(f"Model metadata: {format_run_relative_path(metadata_path)}")
    lines.append("")
    lines.append("Run diagnostics")
    if run_id and run_id != "unknown":
        lines.append(f"Leaderboard: diagnostics/model_comparison_summary_{run_id}.csv")
    lines.append("Additional reports: diagnostics/ (family tiers, RF importances, inspector)")
    return lines


def _print_summary_stat(label: str, value: Any, *, compact: bool) -> None:
    """Render an evaluation summary field without table padding in compact mode."""
    du.print_stat(label, value, width=0 if compact else 32)


def _compact_key_value_line(line: str) -> str:
    """Collapse legacy pre-aligned ``label : value`` text for compact output."""
    label, separator, value = line.partition(":")
    if not separator:
        return line.strip()
    return f"{label.strip()}: {value.strip()}"


def print_model_evaluation_terminal_summary(
    results: dict[str, dict],
    summary_df: pd.DataFrame,
    *,
    manifest_context: dict[str, Any] | None = None,
) -> None:
    """Print the consolidated headline model-evaluation terminal block."""
    if ml_console.is_minimal() or summary_df.empty:
        return

    profile_surface, run_id, label_field = _profile_and_run_context()
    top = summary_df.iloc[0]
    top_model = str(top["Model"])
    top_eval = results.get(top_model, {}).get("evaluation", {})
    if not isinstance(top_eval, dict):
        top_eval = {}

    rank_metric = str(
        getattr(app_config, "MODEL_RANK_PRIMARY_METRIC", "macro_f1_score") or "macro_f1_score"
    ).strip().lower()
    primary_label = "Macro-F1"
    if rank_metric == "f1_score":
        primary_label = "Weighted F1"
    elif rank_metric == "accuracy":
        primary_label = "Accuracy"

    macro_f1 = top_eval.get("macro_f1_score", top.get("Macro F1-Score"))
    weighted_f1 = top_eval.get("f1_score", top.get("F1-Score"))
    accuracy = top_eval.get("accuracy", top.get("Accuracy"))
    test_n = top_eval.get("samples_tested", top.get("Samples"))
    classes = top_eval.get("num_classes", top.get("Classes"))
    trainable_n = None
    if isinstance(manifest_context, dict):
        trainable_n = manifest_context.get("post_low_support_training_rows")

    claim_surface = resolve_claim_surface_label(manifest_context)
    compact = ml_console.is_compact()

    du.print_section("MODEL EVALUATION SUMMARY")
    _print_summary_stat("Profile", profile_surface, compact=compact)
    if run_id:
        _print_summary_stat("Run ID", run_id, compact=compact)
    _print_summary_stat("Target label", label_field, compact=compact)
    _print_summary_stat("Claim surface", claim_surface, compact=compact)
    _print_summary_stat("Primary metric", primary_label, compact=compact)
    if test_n not in (None, "", "-"):
        _print_summary_stat("Evaluation set", f"{int(test_n):,} test samples", compact=compact)
    if trainable_n not in (None, ""):
        _print_summary_stat("Trainable cohort", f"{int(trainable_n):,} samples", compact=compact)
    if classes not in (None, "", "-"):
        _print_summary_stat("Modeled families", f"{int(classes)}", compact=compact)

    if not compact:
        print("")
    _print_summary_stat("Best model", top_model, compact=compact)
    _print_summary_stat("Macro-F1", _fmt_metric(macro_f1), compact=compact)
    _print_summary_stat("Weighted F1", _fmt_metric(weighted_f1), compact=compact)
    _print_summary_stat("Accuracy", _fmt_metric(accuracy), compact=compact)
    _print_summary_stat(
        "Primary tier",
        f"{tier_code_only(str(top.get('Primary Tier', '')))} — {tier_readable(str(top.get('Primary Tier', '')))}",
        compact=compact,
    )
    interpretation = interpretation_for_macro_f1(
        float(macro_f1) if macro_f1 is not None else None,
        weighted_f1=float(weighted_f1) if weighted_f1 is not None else None,
        accuracy=float(accuracy) if accuracy is not None else None,
    )
    interpretation_indent = "  " if compact else "                       "
    wrapped = _wrap_terminal_prose(interpretation, indent=interpretation_indent)
    print(("Interpretation: " if compact else "Interpretation       : ") + wrapped[0])
    for extra in wrapped[1:]:
        print(interpretation_indent + extra)

    if ml_console.is_debug():
        print("")
        du.print_subheader(f"BEST MODEL METRICS — {top_model}")
        du.print_stat("Weighted Precision", _fmt_metric(top_eval.get("precision", top.get("Precision"))))
        du.print_stat("Weighted Recall", _fmt_metric(top_eval.get("recall", top.get("Recall"))))
        du.print_stat("Macro Precision", _fmt_metric(top_eval.get("macro_precision")))
        du.print_stat("Macro Recall", _fmt_metric(top_eval.get("macro_recall")))
        conf_range = _confidence_range_line(top_eval)
        if conf_range:
            du.print_stat("Confidence range", conf_range)
        unknown_line = _unknown_prediction_line(results, top_model)
        if unknown_line:
            du.print_stat("Unknown predictions", unknown_line)

    print("")
    du.print_subheader("MODEL LEADERBOARD — ranked by Macro-F1")
    print(f"{'Rank':<5}{'Model':<22}{'Macro-F1':>10}{'Weighted F1':>13}{'Accuracy':>11}{'Gap':>8}")
    top_macro = float(macro_f1) if macro_f1 is not None else float(top.get("Macro F1-Score", 0.0))
    for _, row in summary_df.iterrows():
        gap = "—" if int(row["Rank"]) == 1 else f"{float(row['Macro F1-Score']) - top_macro:+.4f}"
        print(
            f"{int(row['Rank']):<5}"
            f"{str(row['Model']):<22}"
            f"{_fmt_metric(row['Macro F1-Score']):>10}"
            f"{_fmt_metric(row['F1-Score']):>13}"
            f"{_fmt_metric(row['Accuracy']):>11}"
            f"{gap:>8}"
        )

    pop_lines = format_population_terminal_lines(manifest_context)
    if pop_lines:
        print("")
        du.print_subheader("COHORT / SPLIT SUMMARY")
        for line in pop_lines:
            print(_compact_key_value_line(line) if compact else line)

    print("")
    du.print_subheader("EXPORTED ARTIFACTS")
    runtime_sec = _collect_training_runtime_sec(results)
    for line in _artifact_lines(
        results=results,
        top_model=top_model,
        run_id=run_id,
        training_runtime_sec=runtime_sec,
    ):
        print(_compact_key_value_line(line) if compact else line)
    print("")


def print_ablation_experiments_header(*, cohort_n: int, selected_vendors: int | str, effective_top_k: int | str) -> None:
    """Print the ablation section header and purpose block."""
    if ml_console.is_minimal():
        return
    du.print_section("ABLATION EXPERIMENTS")
    print(
        "Purpose              : Compare feature families and estimate how much signal\n"
        "                       comes from permissions, vendor features, and fused inputs."
    )
    du.print_stat("Cohort", f"{int(cohort_n):,} aligned samples")
    du.print_stat("Selected vendors", selected_vendors)
    du.print_stat("Effective top-k", effective_top_k)
    print("")


def print_ablation_feature_sets_built(
    *,
    rows: list[dict[str, Any]],
    built_ok: int,
    built_total: int,
    skipped_count: int,
) -> None:
    """Print the compact ablation feature-set build table."""
    if ml_console.is_minimal() or not rows:
        return
    du.print_success(f"Built {built_ok}/{built_total} feature sets; {skipped_count} skipped.")
    print("")
    du.print_subheader("FEATURE SETS BUILT")
    display_rows = []
    for row in rows:
        status = str(row.get("status", "OK"))
        skip_reason = str(row.get("skip_reason", "—"))
        if status == "SKIPPED" and skip_reason not in {"", "—"}:
            status = f"SKIPPED — {skip_reason.replace('_', ' ')}"
        display_rows.append(
            {
                "Feature set": row.get("feature_set", ""),
                "Columns": row.get("columns", 0),
                "Status": status,
            }
        )
    du.print_table(pd.DataFrame(display_rows), show_index=False, max_col_width=None, tablefmt="github")


def _best_macro_f1_for_experiment(
    summary_df: pd.DataFrame,
    *,
    label_target: str,
    experiment: str,
) -> float | None:
    if summary_df.empty or "macro_f1_score" not in summary_df.columns:
        return None
    frame = summary_df.copy()
    if "label_target" in frame.columns:
        frame = frame[frame["label_target"].astype(str) == str(label_target)]
    frame = frame[frame["experiment"].astype(str) == str(experiment)]
    if frame.empty:
        return None
    values = pd.to_numeric(frame["macro_f1_score"], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.max())


def _primary_ablation_label_target(summary_df: pd.DataFrame) -> str:
    if "label_target" not in summary_df.columns:
        return "family_canonical_default"
    targets = [str(v) for v in summary_df["label_target"].dropna().astype(str).unique().tolist()]
    for preferred in ("family_id", "family_canonical_default", "type_slug", "family_within_type"):
        if preferred in targets:
            return preferred
    return targets[0] if targets else "family_canonical_default"


def ablation_interpretation_lines(summary_df: pd.DataFrame) -> list[str]:
    """Return compact ablation interpretation rows for terminal display."""
    if summary_df.empty:
        return []

    label_target = _primary_ablation_label_target(summary_df)
    permissions_raw = _best_macro_f1_for_experiment(
        summary_df, label_target=label_target, experiment="permissions_raw"
    )
    full_fused = _best_macro_f1_for_experiment(
        summary_df, label_target=label_target, experiment="full_fused"
    )
    vendor_parsed = _best_macro_f1_for_experiment(
        summary_df, label_target=label_target, experiment="vendor_full"
    )
    vendor_safe = _best_macro_f1_for_experiment(
        summary_df, label_target=label_target, experiment="vendor_no_parsed_family"
    )

    lines: list[str] = []
    if permissions_raw is not None:
        lines.append(f"Permissions raw       : {_fmt_metric(permissions_raw)} Macro-F1")
    if full_fused is not None:
        lines.append(f"Full fused            : {_fmt_metric(full_fused)} Macro-F1")
    if permissions_raw is not None and full_fused is not None:
        lines.append(f"Permission gap        : {permissions_raw - full_fused:+.4f}")
    if vendor_parsed is not None and vendor_safe is not None:
        lines.append(f"Vendor leakage gap    : {vendor_parsed - vendor_safe:+.4f}")

    if permissions_raw is not None and full_fused is not None:
        perm_gap = permissions_raw - full_fused
        leak_gap = (vendor_parsed - vendor_safe) if vendor_parsed is not None and vendor_safe is not None else None
        if perm_gap >= 0.02 and (leak_gap is None or leak_gap <= 0.02):
            interpretation = (
                "Permissions carry strong independent signal; fused gains are modest."
            )
        elif perm_gap >= 0.0 and leak_gap is not None and leak_gap > 0.02:
            interpretation = (
                "Permissions carry strong independent signal; parsed vendor-family "
                "features remain leakage-sensitive."
            )
        elif leak_gap is not None and leak_gap > 0.02:
            interpretation = (
                "Parsed vendor-family features remain leakage-sensitive; permissions "
                "add complementary but smaller lift."
            )
        elif perm_gap < -0.02:
            interpretation = (
                "Fused features outperform permissions-only signal; permission slice "
                "is informative but not sufficient alone."
            )
        else:
            interpretation = (
                "Permissions and fused vendor features contribute comparable signal; "
                "review leakage-sensitive vendor slices before claiming family separation."
            )
        wrapped = _wrap_terminal_prose(interpretation, indent="                       ")
        lines.append("Interpretation        : " + wrapped[0])
        for extra in wrapped[1:]:
            lines.append("                       " + extra)
    return lines


def _wrap_terminal_prose(text: str, *, indent: str, width: int = 92) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    first_limit = max(24, width - 24)
    cont_limit = max(24, width - len(indent))
    for word in words:
        candidate = f"{current} {word}".strip()
        limit = first_limit if not lines else cont_limit
        if current and len(candidate) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def print_ablation_leaderboard_compact(leaderboard_rows: list[dict[str, Any]]) -> None:
    """Print a compact ablation leaderboard focused on the primary family target."""
    if ml_console.is_minimal() or not leaderboard_rows:
        return
    if ml_console.is_debug():
        return
    primary = next(
        (row for row in leaderboard_rows if str(row.get("label_target")) == "family_id"),
        leaderboard_rows[0],
    )
    label_target = str(primary.get("label_target", "family"))
    du.print_subheader(
        f"ABLATION LEADERBOARD — {label_target} (best Macro-F1 per slice)"
    )
    print(f"{'Slice':<16}{'Feature set':<28}{'Macro-F1':>10}")
    print(f"{'Best overall':<16}{str(primary.get('best_feature_set', '—')):<28}{_fmt_metric(primary.get('best_macro_f1')):>10}")
    perm = str(primary.get("permission_only", "—"))
    vendor = str(primary.get("vendor_safe", "—"))
    fused = str(primary.get("full_fused", "—"))
    if perm != "—":
        print(f"{'Permission-only':<16}{perm:<28}")
    if vendor != "—":
        print(f"{'Vendor-safe':<16}{vendor:<28}")
    if fused != "—":
        print(f"{'Full fused':<16}{fused:<28}")
    print("")


def print_ablation_interpretation_summary(summary_df: pd.DataFrame) -> None:
    """Print the compact post-leaderboard ablation interpretation block."""
    if ml_console.is_minimal():
        return
    lines = ablation_interpretation_lines(summary_df)
    if not lines:
        return
    print("")
    du.print_subheader("ABLATION INTERPRETATION")
    for line in lines:
        print(line)


def print_ablation_cohort_integrity_summary(
    *,
    aligned_feature_sets: int,
    total_feature_sets: int,
    aligned_samples: int,
    missing_ids: int,
) -> None:
    """Print the compact post-build ablation cohort integrity block."""
    if ml_console.is_minimal():
        return
    print("")
    du.print_stat("Cohort integrity", "PASS" if missing_ids == 0 else "WARN")
    du.print_stat("Aligned feature sets", f"{aligned_feature_sets} / {total_feature_sets}")
    du.print_stat("Missing sample IDs", missing_ids)
    if aligned_samples:
        du.print_stat("Aligned samples", f"{int(aligned_samples):,}")
