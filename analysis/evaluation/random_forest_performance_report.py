import json
from pathlib import Path

from utils import display_utils as du


def report_performance(metadata_path: str = "output/models/random_forest/random_forest_classifier_model_metadata.json", threshold: float = 0.75) -> None:
    """Display Random Forest evaluation details to help diagnose weak classes."""
    meta_file = Path(metadata_path)
    if not meta_file.exists():
        du.print_error(f"Metadata file not found: {meta_file}")
        return

    with open(meta_file, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    report = meta.get("classification_report")
    if not report:
        du.print_error("Classification report missing from metadata.")
        return

    du.print_section("Random Forest Performance Summary")
    overall = report.get("weighted avg", {}).get("f1-score")
    if overall is not None:
        du.print_stat("F1-Score (weighted)", round(overall, 4))

    weak = []
    for label, stats in report.items():
        if not isinstance(stats, dict) or "f1-score" not in stats:
            continue
        if label in {"accuracy", "macro avg", "weighted avg"}:
            continue
        f1 = stats["f1-score"]
        du.print_info(f"{label:15s} -> F1: {f1:.4f} | Support: {stats.get('support')}")
        if f1 < threshold:
            weak.append(label)

    if weak:
        du.print_warning(f"Weak classes (f1 < {threshold}): {', '.join(weak)}")

    if meta.get("feature_importances"):
        du.print_section("Top Feature Importances")
        for idx, score in meta["feature_importances"]:
            du.print_info(f"Feature {idx}: {score:.4f}")

    if meta.get("cv_scores"):
        du.print_section("Cross-validation")
        scores = [round(s, 4) for s in meta["cv_scores"]]
        du.print_info(f"Scores: {scores}")
        du.print_info(f"Mean  : {meta.get('cv_score_mean'):.4f}")


if __name__ == "__main__":
    report_performance()
