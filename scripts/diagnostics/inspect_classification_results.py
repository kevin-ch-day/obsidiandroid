# Filename: scripts/diagnostics/inspect_classification_results.py
# Purpose: Publication-grade interpretation of malware family classification results
# Context: ObsidianDroid - ML-based evaluation using AV engine consensus and metadata scoring

import pandas as pd
from datetime import datetime
import os

def generate_classification_summary(
    accuracy,
    report_path,
    model_path,
    metadata=None,
    output_dir="output/diagnostics",
    model_name="random_forest",
):
    # === PART 1: Summary Header - Results Overview ===
    lines = _build_summary_header(
        accuracy=accuracy,
        report_path=report_path,
        model_path=model_path,
        model_name=model_name,
    )

    if accuracy is None:
        error_msg = "[ERROR] Accuracy not available - evaluation terminated."
        print(f"\n{error_msg}\n")
        lines.append(error_msg)
        _write_summary_report(lines, output_dir)
        return

    # === PART 2: Performance Interpretation ===
    interpretation = _interpret_model_performance(accuracy)
    for line in interpretation:
        print(line)
    lines.append("")  # spacing
    lines.extend(interpretation)

    # === PART 3: Metadata Diagnostics Summary (Optional) ===
    if metadata:
        print("\n=== [DATA CONTEXT] Evaluation Metadata ===")
        metadata_lines = _summarize_metadata_summary(metadata)
        lines.append("")  # spacing
        lines.extend(metadata_lines)

    # === PART 4: Strategic Action Plan ===
    print("\n=== [RECOMMENDATIONS] Strategic Action Plan ===")
    recommendations = _get_recommendations(accuracy=accuracy, metadata=metadata or {})
    for rec in recommendations:
        print(f"- {rec}")
    lines.append("\n=== Strategic Action Plan ===")
    lines.extend([f"- {r}" for r in recommendations])

    # === PART 5: Add Final Note for Audit and Validation ===
    lines.append("\n[NOTE] Report generated for diagnostic and academic use. Validate against real-world deployment sets before production use.")

    # === PART 6: Output Summary File ===
    _write_summary_report(lines, output_dir)

# === Internal Helpers === #

def _build_summary_header(accuracy, report_path, model_path, model_name="random_forest"):
    model_map = {
        "random_forest": (
            "Random Forest",
            "Ensemble-based learner using decision tree voting",
        ),
        "xgboost": (
            "XGBoost",
            "Gradient-boosted decision trees for supervised multi-class Android malware family detection.",
        ),
        "logistic_regression": (
            "Logistic Regression",
            "Linear probabilistic classifier with regularization for multi-class labeling.",
        ),
        "svm": (
            "Support Vector Machine",
            "Margin-based classifier for supervised multi-class discrimination.",
        ),
        "balanced_random_forest": (
            "Balanced Random Forest",
            "Class-balanced ensemble for imbalanced multi-class malware family detection.",
        ),
    }
    arch_name, model_desc = model_map.get(
        (model_name or "").lower(),
        ("Custom Classifier", "Supervised malware family classifier."),
    )
    # === Terminal Output === #
    print("\n" + "=" * 74)
    print("          [RESULTS] Malware Family Classification Summary Report")
    print("=" * 74)
    print(f"Model Architecture        : {arch_name}")
    print(f"Classifier Description    : {model_desc}")

    # Interpret accuracy and derive insight
    if accuracy is not None:
        percentage = accuracy * 100
        print(f"\nEvaluation Accuracy       : {accuracy:.4f}  ({percentage:.2f}%)")

        if percentage >= 90:
            confidence = "EXCELLENT - Deployment-ready for real-time detection and research use."
        elif 85 <= percentage < 90:
            confidence = "STRONG - High generalization with minor family-level classification noise."
        elif 75 <= percentage < 85:
            confidence = "MODERATE - Distinguishes most families; tuning and feature calibration recommended."
        elif 60 <= percentage < 75:
            confidence = "LIMITED - Marginal family separation. Investigate class imbalance and feature resolution."
        else:
            confidence = "INSUFFICIENT - Classification reliability too low for informed use."
        print(f"Performance Insight       : {confidence}")
    else:
        print("Evaluation Accuracy       : [Unavailable]")
        confidence = "Accuracy missing - model validation was not completed successfully."

    print(f"\nClassification Report     : {report_path}")
    print(f"Trained Model Export      : {model_path}")

    # === Report Body Lines === #
    summary_lines = [
        "==========================================================================",
        "  Malware Family Classifier - Diagnostic Execution Summary",
        "==========================================================================",
        f"Model Architecture        : {arch_name}",
        f"Classifier Description    : {model_desc}",
        f"Accuracy Score (Decimal)  : {accuracy:.4f}" if accuracy is not None else "Accuracy Score (Decimal)  : [Unavailable]",
        f"Accuracy Score (Percent)  : {percentage:.2f}%" if accuracy is not None else "Accuracy Score (Percent)  : [Unavailable]",
        f"Performance Assessment    : {confidence}",
        f"Classification Report     : {report_path}",
        f"Model Export File         : {model_path}"
    ]

    return summary_lines


def _interpret_model_performance(accuracy: float) -> list:
    """
    Interpret model performance based on accuracy score.
    Returns a list of performance analysis lines.
    """
    lines = []
    lines.append("\n=== [INTERPRETATION] Model Performance Analysis ===")

    if accuracy >= 0.90:
        lines.append("Performance Insight: OUTSTANDING - Model exhibits exceptional accuracy.")
        lines.append("The model generalizes well across diverse malware families and is ready for production and academic benchmarking.")
    elif 0.85 <= accuracy < 0.90:
        lines.append("Performance Insight: EXCELLENT - High reliability with minor edge-case volatility.")
        lines.append("Ideal for analyst dashboards and internal operational use with light validation.")
    elif 0.75 <= accuracy < 0.85:
        lines.append("Performance Insight: MODERATE - Indicates good family discrimination with room for tuning.")
        lines.append("Consider improving feature diversity, balancing training data, or reexamining label consistency.")
    elif 0.60 <= accuracy < 0.75:
        lines.append("Performance Insight: BORDERLINE - Model struggles with generalization.")
        lines.append("Likely affected by noisy data, AV engine imbalance, or insufficient sample support.")
    else:
        lines.append("Performance Insight: INSUFFICIENT - Model accuracy falls below deployment thresholds.")
        lines.append("Requires full pipeline review: dataset quality, labeling practices, and AV engine signal contribution.")

    return lines


def _get_recommendations(accuracy: float, metadata: dict) -> list:
    recommendations = []

    # Accuracy-based guidance
    if accuracy is None:
        return ["Model accuracy was not computed. Ensure training and evaluation completed successfully."]

    if accuracy < 0.60:
        recommendations += [
            "Reengineer the ML pipeline: investigate weak feature engineering, high feature sparsity, or insufficient vendor input signal.",
            "Verify AV engine label quality - prioritize engines with high precision and discard noisy engines.",
            "Consider rebalancing or relabeling conflicting samples and enhancing engine label parsers."
        ]
    elif 0.60 <= accuracy < 0.75:
        recommendations += [
            "Model performance is below acceptable threshold for confident classification. Analyze class overlap in confusion matrix.",
            "Reduce reliance on noisy engines and strengthen training signal using enriched family metadata.",
            "Apply tier-aware engine filtering to isolate top contributors from generic scanners."
        ]
    elif 0.75 <= accuracy < 0.85:
        recommendations += [
            "Moderate model accuracy suggests difficulty in learning minor family variants. Analyze vendor parser entropy per family.",
            "Consider feature expansion with static capabilities like permissions, network intents, or suspicious API calls.",
            "Integrate ensemble classifiers (e.g., Random Forest + Gradient Boosting) to boost minority class resolution."
        ]
    elif 0.85 <= accuracy < 0.90:
        recommendations += [
            "Strong performance achieved. Focus on edge-case misclassifications and further reduce vendor redundancy.",
            "Introduce per-family threshold tuning or confidence calibration to enhance decision robustness."
        ]
    else:
        recommendations += [
            "Model demonstrates excellent family discrimination. Maintain a routine validation schedule to detect drift.",
            "Expand training set with recent threats or simulated variants to ensure adaptability to future samples."
        ]

    # General best practices
    recommendations += [
        "Integrate SHAP or LIME analysis to diagnose top features contributing to predictions per malware family.",
        "Use stratified k-fold cross-validation to ensure consistent results across rare and dominant families.",
        "Assess feature importance heatmaps across top 10 AV engines to confirm contribution diversity."
    ]

    # Metadata-specific diagnostics
    if metadata:
        imbalance_ratio = metadata.get("imbalance_ratio")
        if imbalance_ratio:
            if imbalance_ratio > 0.5:
                recommendations.append(f"Severe class imbalance detected (Imbalance Index: {imbalance_ratio:.2f}). Use SMOTE or synthetic generation.")
            elif imbalance_ratio > 0.3:
                recommendations.append(f"Moderate imbalance detected (Imbalance Index: {imbalance_ratio:.2f}). Use class weighting during training.")

        filtered_families = metadata.get("filtered_families", [])
        if filtered_families:
            recommendations.append(f"{len(filtered_families)} low-support families were removed. Augment these families using targeted sampling or simulations.")

        filtered_engines = metadata.get("filtered_engines", [])
        if filtered_engines:
            recommendations.append(f"{len(filtered_engines)} engines removed due to low tier or high noise. Review parser logic or engine contribution reliability.")

    return recommendations

def _write_summary_report(lines, output_dir):
    """
    Writes the classification summary to a timestamped text file in the diagnostics output directory.
    """
    if not lines or not isinstance(lines, list):
        print("[ERROR] No summary lines provided for report generation.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs(output_dir, exist_ok=True)

    filename = f"classifier_summary_eval_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"\n\nEvaluation summary report generated and saved to: {filepath}\n")
    except Exception as e:
        print(f"[ERROR] Failed to write summary report to {filepath}: {e}")


def _summarize_metadata_summary(metadata: dict) -> list:
    lines = []
    lines.append("\n=== [DATASET OVERVIEW] Classification Metadata Summary ===")

    samples = metadata.get("samples")
    families = metadata.get("families")
    features = metadata.get("features")
    imbalance_ratio = metadata.get("imbalance_ratio")
    filtered_engines = metadata.get("filtered_engines")
    filtered_families = metadata.get("filtered_families")

    if samples:
        lines.append(f"- Total Samples Evaluated              : {samples:,}")
    if families:
        lines.append(f"- Unique Malware Families              : {families:,}")
    if features:
        lines.append(f"- Feature Dimensions Used              : {features:,}")

    if imbalance_ratio is not None:
        if imbalance_ratio > 0.5:
            status = "HIGH - Severe imbalance; many families may be underrepresented or skewed."
        elif imbalance_ratio > 0.3:
            status = "MODERATE - Some imbalance present; review rare class representation."
        else:
            status = "LOW - Balanced dataset distribution across most families."
        lines.append(f"- Family Imbalance Index               : {imbalance_ratio:.2f} ({status})")

    if filtered_engines:
        shown = ', '.join(filtered_engines[:5]) + (" ..." if len(filtered_engines) > 5 else "")
        lines.append(f"- AV Engines Filtered for Noise        : {len(filtered_engines)} engine(s) -> {shown}")

    if filtered_families:
        shown = ', '.join(filtered_families[:5]) + (" ..." if len(filtered_families) > 5 else "")
        lines.append(f"- Low-Support Families Removed         : {len(filtered_families)} family group(s) -> {shown}")

    # Optional analytics insight
    if imbalance_ratio and imbalance_ratio > 0.4 and filtered_families:
        lines.append("- [Insight] Data pruning and class imbalance suggest uneven learning potential for minority families.")

    # Console output
    for line in lines:
        print(line)

    return lines

def summarize_av_engine_weight_distribution(weights_df: pd.DataFrame):
    if weights_df.empty or "ML Weight Score" not in weights_df:
        print("[WARNING] No AV engine weight data available for summarization.")
        return

    print("\n=== [ENGINE SCORING SUMMARY] AV Engine ML Weight Distribution ===")

    # Core distribution statistics
    max_score = weights_df['ML Weight Score'].max()
    min_score = weights_df['ML Weight Score'].min()
    mean_score = weights_df['ML Weight Score'].mean()
    median_score = weights_df['ML Weight Score'].median()
    std_dev = weights_df['ML Weight Score'].std()
    q25 = weights_df['ML Weight Score'].quantile(0.25)
    q75 = weights_df['ML Weight Score'].quantile(0.75)

    print(f"- Total AV Engines Evaluated      : {len(weights_df)}")
    print(f"- Max ML Score                    : {max_score:.4f}")
    print(f"- Min ML Score                    : {min_score:.4f}")
    print(f"- Mean ML Score                   : {mean_score:.4f}")
    print(f"- Median ML Score                 : {median_score:.4f}")
    print(f"- Std Dev of ML Scores            : {std_dev:.4f}")
    print(f"- Interquartile Range (Q1-Q3)     : {q25:.4f} to {q75:.4f}")

    # Tier classification analysis
    if "Detection Tier" in weights_df.columns:
        print("\n[ENGINE CLASSIFICATION] Detection Tier Distribution:")
        tier_counts = weights_df["Detection Tier"].value_counts()
        for tier, count in tier_counts.items():
            print(f"  - {tier:<25}: {count} engine(s)")

    # Reliability profile breakdown
    if "Reliability" in weights_df.columns:
        print("\n[RELIABILITY PROFILE] Engine Trustworthiness Summary:")
        rel_counts = weights_df["Reliability"].value_counts()
        for rel, count in rel_counts.items():
            print(f"  - {rel:<12}: {count} engine(s)")

    # Stratified segmentation
    print("\n[SEGMENTATION] ML Weight-Based Engine Clusters:")
    high_perf = weights_df[weights_df["ML Weight Score"] >= q75]
    mid_perf = weights_df[(weights_df["ML Weight Score"] < q75) & (weights_df["ML Weight Score"] >= q25)]
    low_perf = weights_df[weights_df["ML Weight Score"] < q25]

    print(f"- High-Performing Engines (Top 25%) : {len(high_perf)}")
    print(f"- Moderate Engines (Mid 50%)        : {len(mid_perf)}")
    print(f"- Low-Performing Engines (Bottom 25%): {len(low_perf)}")

    # Strategy and Recommendations
    print("\n=== [STRATEGIC INSIGHTS] AV Engine Evaluation Guidance ===")
    print("-> Top 25% engines contribute the most consistent signal to classification accuracy.")
    print("-> Engines below Q1 (bottom 25%) may introduce false positives or degraded family attribution.")
    print("-> Focus retraining efforts on high-weight, high-specificity engines.")
    print("-> Consider removing noisy, low-signal engines from future model inputs.")
    print("-> Benchmark engine performance longitudinally to capture concept drift or dataset bias.")

    # Top-performing engine showcase
    print("\n[TOP ENGINES] Highest-Ranked AV Vendors by ML Score:")
    top_engines = high_perf.sort_values("ML Weight Score", ascending=False).head(5)
    for _, row in top_engines.iterrows():
        tier = row["Detection Tier"] if "Detection Tier" in row else "N/A"
        print(f"  - {row['Engine']:<20} | Score: {row['ML Weight Score']:.4f} | Tier: {tier}")
