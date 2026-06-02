# Filename: src/obsidiandroid/database/db_extract_av_label_keywords.py
# Purpose : Extracts and analyzes AV label keywords to generate ML training features.
#
# Canonical implementation; the repo-root
# ``database.db_extract_av_label_keywords`` shim has been retired. Exported from
# ``obsidiandroid.database`` (see ``facade_manifest.FACADE_EXPORT_NAMES``).

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict

import pandas as pd

from obsidiandroid.cli.ui import display as du

from . import db_engine, db_utils
from .verdict_semantics import sql_non_detection_predicate

STOPWORDS = {
    "android", "os", "variant", "ver", "gen", "generic", "win32", "linux", "sample", "detected", "unknown"
}


def normalize_and_tokenize(label: str, min_token_len: int = 3, remove_stopwords: bool = True) -> list:
    if not label or not isinstance(label, str):
        return []

    # Normalize Unicode characters (e.g., remove accents, homoglyphs)
    label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("utf-8", "ignore")

    # Lowercase and replace common delimiters with space
    label = label.lower()
    label = re.sub(r"[/:._\-\\(){}\[\],]+", " ", label)

    # Collapse multiple spaces
    label = re.sub(r"\s+", " ", label).strip()

    # Extract alphanumeric tokens (3+ chars by default)
    tokens = re.findall(rf"\b[a-z0-9]{{{min_token_len},}}\b", label)

    # Optionally remove common noisy or generic tokens
    if remove_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]

    return tokens


# --- Keyword Classification ---
def classify_keyword_category(token: str) -> str:
    token = token.lower()

    # Core malware indicators
    malicious_keywords = [
        "trojan", "banker", "spy", "backdoor", "dropper", "rat", "ransom", "stealer",
        "keylogger", "infostealer", "smssend", "spyware", "agent", "malware", "lockscreen",
        "worm", "vultur", "botnet", "exploit", "shell", "rootkit", "obfuscated", "loader",
        "clipbanker", "injector", "dnschanger", "bootkit", "dloader", "smsreg", "clicker",
        "bootlocker", "filecoder", "crypt", "overlay", "ats", "bankbot"
    ]

    # Suspicious, greyware, or potentially unwanted behaviors
    suspicious_keywords = [
        "risktool", "adware", "notavirus", "heur", "generic", "grayware", "potentially",
        "unwanted", "monitor", "remoteshell", "tracking", "packer", "hidden", "compress",
        "obfus", "dualuse", "loader", "proxy", "inject", "tunnel", "metasploit", "smsreader",
        "fake", "testkey", "sample", "demo", "rootenabler", "repack", "freedownloader"
    ]

    # Known benign or clean indicators
    benign_keywords = {
        "benign", "clean", "safe", "ok", "trusted", "whitelist", "certified", "pass", "approved",
        "legal", "signed", "verified"
    }

    # Hardcoded rules for common AV placeholders or flags
    placeholder_tokens = {
        "unknown", "undefined", "none", "test", "n/a", "null", "scanengine"
    }

    # Category matching logic
    if any(x in token for x in malicious_keywords):
        return "malicious"
    if any(x in token for x in suspicious_keywords):
        return "suspicious"
    if token in benign_keywords:
        return "benign"
    if token in placeholder_tokens or token.startswith("test"):
        return "placeholder"

    return "unknown"


def compute_entropy(label_set: set) -> float:
    if not label_set:
        return 0.0

    tokens = [normalize_and_tokenize(label) for label in label_set if label]
    flat_tokens = [token for sublist in tokens for token in sublist]

    if not flat_tokens:
        return 0.0

    token_counts = Counter(flat_tokens)
    total = sum(token_counts.values())

    entropy = -sum((count / total) * math.log2(count / total) for count in token_counts.values() if count > 0)
    return round(entropy, 4)


# --- Pull Raw Labels From DB ---
def collect_raw_engine_labels(engine: str, sample_limit: int = 2000) -> list:
    if not engine or not isinstance(engine, str):
        du.print_warning(f"[WARN] Invalid engine name provided: {engine}")
        return []

    # Basic sanitization to prevent SQL injection in backticks
    safe_col = engine.strip().replace("`", "").replace('"', "")

    query = f"""
        SELECT DISTINCT `{safe_col}` AS result
        FROM virustotal_sample_vendor_engine_verdicts
        WHERE NOT ({sql_non_detection_predicate(f'`{safe_col}`')})
        LIMIT {sample_limit}
    """

    try:
        _, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
        labels = [row[0].strip() for row in rows if row and isinstance(row[0], str) and row[0].strip()]
        return labels
    except Exception as e:
        du.print_warning(f"[WARN] Failed to collect labels for engine '{engine}': {e}")
        return []


# --- Main Analysis Logic ---
def analyze_detection_keywords(sample_limit: int = 2000):
    keyword_counter = Counter()
    keyword_to_labels = defaultdict(set)
    engine_token_map = defaultdict(Counter)
    label_examples = defaultdict(list)
    keyword_categories = {}
    keyword_entropy_scores = {}
    engine_entropy_scores = {}

    engine_columns = db_utils.get_valid_detection_columns()
    du.print_info(f"[INFO] Scanning {len(engine_columns)} AV engine result columns...")

    for engine in engine_columns:
        labels = collect_raw_engine_labels(engine, sample_limit)
        if not labels:
            du.print_warning(f"[WARN] No valid labels found for engine: {engine}")
            continue

        for label in labels:
            tokens = normalize_and_tokenize(label)
            if not tokens:
                continue

            keyword_counter.update(tokens)
            engine_token_map[engine].update(tokens)

            for token in tokens:
                keyword_to_labels[token].add(label)

            if len(label_examples[engine]) < 10:
                label_examples[engine].append(label)

        engine_entropy_scores[engine] = compute_entropy(set(labels))

    for token, label_set in keyword_to_labels.items():
        keyword_categories[token] = classify_keyword_category(token)
        keyword_entropy_scores[token] = compute_entropy(label_set)

    du.print_info(f"[INFO] Total unique tokens extracted: {len(keyword_counter)}")
    du.print_info("[INFO] Generating ML-ready output files...")

    save_txt_report(
        counter=keyword_counter,
        categories=keyword_categories,
        entropies=keyword_entropy_scores,
        engine_map=engine_token_map,
        engine_scores=engine_entropy_scores,
        examples=label_examples
    )

    save_training_excel(
        counter=keyword_counter,
        categories=keyword_categories,
        entropies=keyword_entropy_scores,
        label_map=keyword_to_labels,
        engine_scores=engine_entropy_scores
    )

    du.print_success("[DONE] Keyword training data generation complete.")
    return keyword_counter, keyword_to_labels


# --- Text Output ---
def save_txt_report(counter, categories, entropies, engine_map, engine_scores, examples):
    path = "results/av_keywords_summary.txt"

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("=== [GLOBAL] Top 100 AV Label Keywords ===\n")
            f.write("Keyword             Count     Category       Entropy     Label_Complexity\n")
            f.write("--------------------------------------------------------------------------\n")
            for kw, count in counter.most_common(100):
                category = categories.get(kw, "unknown")
                entropy = entropies.get(kw, 0.0)
                label_complexity = "high" if entropy > 2.5 else "low" if entropy < 1.0 else "medium"
                f.write(f"{kw:20} {count:6}  {category:>12}  H={entropy:.2f}    {label_complexity:>10}\n")

            f.write("\n=== [SUMMARY] Token Distribution by Category ===\n")
            category_dist = defaultdict(int)
            for kw in counter:
                category = categories.get(kw, "unknown")
                category_dist[category] += counter[kw]
            for cat, total in sorted(category_dist.items(), key=lambda x: -x[1]):
                f.write(f"{cat.capitalize():12}: {total} tokens\n")

            f.write("\n=== [ENGINE ANALYSIS] Top Tokens Per Engine ===\n")
            for engine, tokens in engine_map.items():
                entropy = engine_scores.get(engine, 0.0)
                diversity = "narrow" if entropy < 1.0 else "broad" if entropy > 2.5 else "moderate"
                f.write(f"\n[ENGINE: {engine}]   Token Entropy = {entropy:.2f} ({diversity} scope)\n")
                f.write("  Keyword            Count\n")
                for kw, count in tokens.most_common(10):
                    f.write(f"  {kw:18} {count:5}\n")

            f.write("\n=== [SAMPLES] Example Labels Per Engine ===\n")
            for engine, samples in examples.items():
                f.write(f"\n[ENGINE: {engine}]  Top Examples:\n")
                for label in samples[:10]:
                    f.write(f"  - {label}\n")

        du.print_success(f"[TXT] Keyword summary:{du.format_console_path(path)}")
    except Exception as e:
        du.print_error(f"[TXT ERROR] Failed to write keyword summary: {e}")


# --- Excel Output ---
def save_training_excel(counter, categories, entropies, label_map, engine_scores):
    path = "results/av_keywords_training.xlsx"

    try:
        df_keywords = pd.DataFrame([
            {
                "keyword": kw,
                "count": counter.get(kw, 0),
                "category": categories.get(kw, "unknown"),
                "entropy": round(entropies.get(kw, 0.0), 3),
                "example_labels": "; ".join(list(label_map[kw])[:5])
            }
            for kw in counter.keys()
        ])

        df_keywords.sort_values(by=["count", "entropy"], ascending=[False, True], inplace=True)

        df_engine_entropy = pd.DataFrame([
            {"engine": engine, "label_entropy": round(score, 3)}
            for engine, score in engine_scores.items()
        ])

        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            df_keywords.to_excel(writer, sheet_name="Keyword_Metadata", index=False)
            df_engine_entropy.to_excel(writer, sheet_name="Engine_LabelEntropy", index=False)

        du.print_success(f"[EXCEL] Training data:{du.format_console_path(path)}")
    except Exception as e:
        du.print_warning(f"[EXCEL ERROR] Failed to write Excel file: {e}")
