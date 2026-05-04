# Filename: scripts/dev/scan_ml_predict_misuse.py
# Purpose  : Static scan for misuse of `.predict()` or `.predict_proba()` on objects not known to be ML models

import os
import re
from datetime import datetime
from typing import List, Tuple, Optional

# --- Optional terminal coloring ---
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
except ImportError:
    class Dummy: RESET_ALL = YELLOW = GREEN = ""
    Fore = Style = Dummy()

# --- Heuristics and Safe Patterns ---
ALLOWED_CALLERS = [
    r'\bmodel\.', r'\bclf\.', r'\bself\.model\.', r'\bself\.clf\.',
    r'result\[\s*[\'"]model[\'"]\s*\]', r'result\[\s*[\'"]clf[\'"]\s*\]',
    r'\bestimator\.', r'\bclassifier\.', r'\bregressor\.', r'\bpredictor\.'
]
SUSPICIOUS_ROOTS = {"result", "output", "data", "response", "metrics", "info", "model_result"}
PATTERNS = [r'\.predict\s*\(', r'\.predict_proba\s*\(']
CONTEXT_LINES = 2
COMMENT_PATTERN = re.compile(r'^\s*#')


# --- Internal Helpers ---
def _is_safe_line(line: str) -> bool:
    return any(re.search(pattern, line) for pattern in ALLOWED_CALLERS)

def _is_probable_code(line: str) -> bool:
    line_strip = line.strip()
    return not (
        COMMENT_PATTERN.match(line_strip) or
        line_strip.startswith(("'''", '"""')) or
        re.fullmatch(r'".*?"|\'.*?\'', line_strip) or
        re.search(r'["\'].*\.predict\(.*["\']', line_strip)
    )

def _get_caller_root(line: str) -> str:
    try:
        caller = re.split(r'\.predict', line)[0].strip()
        return re.split(r'[\[\]\.]', caller)[0]
    except Exception:
        return "UNKNOWN"

def _extract_context(lines: List[str], index: int) -> List[str]:
    start = max(0, index - CONTEXT_LINES)
    end = min(len(lines), index + CONTEXT_LINES + 1)
    return [
        (">>" if i == index else "  ") + f" Line {i + 1}: {lines[i].rstrip()}"
        for i in range(start, end)
    ]


# --- Core Scanner ---
def scan_file_for_predict_misuse(filepath: str) -> List[str]:
    warnings = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        return [f"[ERROR] Could not read {filepath} — {e}"]

    for i, line in enumerate(lines):
        if not _is_probable_code(line) or len(line.strip()) < 8:
            continue

        for pattern in PATTERNS:
            if re.search(pattern, line) and not _is_safe_line(line):
                root = _get_caller_root(line)
                guess = "→ likely dict-like" if root in SUSPICIOUS_ROOTS else "→ unknown object"
                context = _extract_context(lines, i)
                warnings.append(
                    f"""[WARNING] Potential misuse of '.predict(...)'
File     : {filepath}
Line     : {i + 1}
Caller   : {root}
Guess    : {guess}
Hint     : Make sure object is an ML model, not a wrapper like 'model_bundle' or 'dict'.
--------
{os.linesep.join(context)}
"""
                )
    return warnings


def run_static_predict_scan(base_dir: str, log_file: str,
                            exclude_dirs: Optional[List[str]] = None) -> Tuple[int, int]:
    file_count = 0
    total_warnings = []
    start_time = datetime.now()
    exclude_dirs = {os.path.normpath(os.path.join(base_dir, d)) for d in (exclude_dirs or [])}

    for root, _, files in os.walk(base_dir):
        if any(os.path.normpath(root).startswith(ex) for ex in exclude_dirs):
            continue

        for fname in files:
            if fname.endswith(".py"):
                file_count += 1
                path = os.path.join(root, fname)
                warnings = scan_file_for_predict_misuse(path)
                if warnings:
                    print(f"{Fore.YELLOW}[INFO] {len(warnings)} issue(s) in: {fname}{Style.RESET_ALL}")
                    total_warnings.extend(warnings)

    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write(f"ObsidianDroid ML Predict() Misuse Report — {start_time.isoformat()}Z\n")
        f.write("=" * 100 + "\n\n")
        f.write("\n".join(total_warnings))
        f.write("\n\n")
        f.write(f"Scan completed at: {datetime.now().isoformat()}Z\n")
        f.write(f"Total files scanned: {file_count}\n")
        f.write(f"Total warnings     : {len(total_warnings)}\n")

    print(f"\n{Fore.GREEN}[COMPLETE] Scanned {file_count} files | {len(total_warnings)} warnings{Style.RESET_ALL}")
    print(f"{Fore.GREEN}[OUTPUT  ] Log written to: {log_file}{Style.RESET_ALL}")
    return file_count, len(total_warnings)
