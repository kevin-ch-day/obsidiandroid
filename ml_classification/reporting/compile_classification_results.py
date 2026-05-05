# Filename: compile_classification_results.py
# Purpose  : Build and validate structured classification labels from ML predictions

import pandas as pd
from obsidiandroid.cli.ui import display as du
from ml_classification.builder import sample_classification_builder
from ml_classification.inference.label_consensus_engine import resolve_consensus_label


def build_structured_classification_results(
    records_by_vendor: dict,
    results: dict,
    label_format: str = "structured",
    include_confidence: bool = True,
    return_metadata: bool = False,
    verbose: bool = True,
    use_consensus: bool = True
) -> pd.DataFrame | tuple[pd.DataFrame, dict]:
    if not _validate_inputs(records_by_vendor, results):
        return (pd.DataFrame(), {}) if return_metadata else pd.DataFrame()

    try:
        df = _build_classification_dataframe(
            records_by_vendor, results, label_format, include_confidence, use_consensus
        )
        if df.empty:
            du.print_warning("[RESULT BUILD] No structured classification rows were generated.")
            return (df, {}) if return_metadata else df

        if verbose:
            _print_classification_summary(df, records_by_vendor, label_format, include_confidence)

        metadata = results.get("metadata", {}) or {}
        return (df, metadata) if return_metadata else df

    except Exception as e:
        du.print_error(f"[RESULT BUILD] Failed to compile structured results: {type(e).__name__} — {e}")
        return (pd.DataFrame(), {}) if return_metadata else pd.DataFrame()


# -----------------------------------------------------------------------------
# Internal Helper Functions
# -----------------------------------------------------------------------------

def _validate_inputs(records_by_vendor, results) -> bool:
    if not isinstance(records_by_vendor, dict) or not records_by_vendor:
        du.print_error("[RESULT BUILD] Vendor record map is missing or invalid.")
        return False
    if not isinstance(results, dict) or "predictions" not in results:
        du.print_error("[RESULT BUILD] Classifier results are missing or incomplete.")
        return False
    return True


def _build_classification_dataframe(
    records_by_vendor,
    results,
    label_format,
    include_confidence,
    use_consensus
) -> pd.DataFrame:
    return sample_classification_builder.build_sample_classification_records(
        records_by_vendor=records_by_vendor,
        results=results,
        label_format=label_format,
        include_confidence=include_confidence,
        verbose=False,
        use_consensus=use_consensus,
        consensus_function=resolve_consensus_label if use_consensus else None
    )


def _print_classification_summary(df: pd.DataFrame, records_by_vendor: dict, label_format: str, include_confidence: bool):
    du.print_section("[RESULT SUMMARY] Classification Output Overview")
    du.print_success(f"Structured results created for {len(df)} samples.")
    du.print_stat("Output Format", label_format)
    du.print_stat("Include Confidence", "Yes" if include_confidence else "No")

    _summarize_predictions(df)
    if include_confidence:
        _summarize_confidence(df)
    _summarize_known_families(df)
    _summarize_behavioral_tags(df)
    _validate_record_types(records_by_vendor)


def _summarize_predictions(df: pd.DataFrame):
    if "predicted_family" in df.columns:
        top_fams = df["predicted_family"].value_counts().head(5)
        du.print_info("Top Predicted Families:")
        for fam, count in top_fams.items():
            du.print_info(f" - {fam:<12}: {count}")


def _summarize_confidence(df: pd.DataFrame):
    if "confidence" in df.columns:
        conf_min = df["confidence"].min()
        conf_max = df["confidence"].max()
        conf_avg = df["confidence"].mean()
        du.print_stat("Confidence Range", f"{conf_min:.2f} → {conf_max:.2f}")
        du.print_stat("Average Confidence", f"{conf_avg:.4f}")


def _summarize_known_families(df: pd.DataFrame):
    if "known_family" in df.columns:
        known_count = df["known_family"].sum()
        du.print_stat("Known Family Matches", f"{known_count} / {len(df)} ({(known_count / len(df)):.2%})")


def _summarize_behavioral_tags(df: pd.DataFrame):
    if "malware_type" in df.columns and "threat_class" in df.columns:
        fam_threat = (
            df.groupby(["malware_type", "threat_class"]).size().reset_index(name="count")
        )
        du.print_info("Malware Type / Threat Class Combinations (Top 5):")
        du.print_table(
            fam_threat.sort_values("count", ascending=False).head(5),
            show_index=False,
        )


def _validate_record_types(records_by_vendor: dict):
    flat_records = []
    type_tracker = {}

    for vendor, rec_list in records_by_vendor.items():
        for idx, rec in enumerate(rec_list):
            rec_type = rec.__class__.__name__
            type_tracker.setdefault(rec_type, 0)
            type_tracker[rec_type] += 1

            if rec_type == "VendorClassificationRecord":
                flat_records.append(rec)
            else:
                du.print_error(f"[SANITY] Unexpected object under vendor '{vendor}':")
                print(f"  → Type      : {type(rec)}")
                print(f"  → Module    : {rec.__class__.__module__}")
                print(f"  → Index     : {idx}")
                print(f"  → Object    : {repr(rec)[:500]}")
                print(f"  → Dict Keys : {list(rec.keys()) if isinstance(rec, dict) else 'N/A'}")
                print("  → Suggested Fix: Check if this vendor is importing from a different module.")
                print("\n[ERROR] Aborting execution to prevent downstream signal analysis crash.\n")
                print("[SUMMARY] Object type histogram:")
                for tname, count in type_tracker.items():
                    print(f"  • {tname:<35} → {count} instance(s)")
                exit(99)
