"""STABILITY.csv: one row per (prediction/table, permission or pair), one column per arm, cell = sign+magnitude of the effect and
whether the band excludes zero. REAL = same sign in every arm where defined (and band excludes zero in the primary);
COMPOSITION-DEPENDENT = the sign flips in at least one arm (named)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _effect_T2T3(table: pd.DataFrame, permission: str, y0: int = 2018, y1: int = 2025) -> tuple[float, bool] | None:
    """effect = weighted prevalence change y1 - y0; band excludes zero if the y1 band and y0 band are disjoint."""
    g = table[table["permission"] == permission]
    a = g[g["year"].astype(str) == str(y0)]; b = g[g["year"].astype(str) == str(y1)]
    if len(a) == 0 or len(b) == 0:
        return None
    a, b = a.iloc[0], b.iloc[0]; eff = float(b["weighted_prevalence"] - a["weighted_prevalence"])
    excl = bool((b["lo95"] > a["hi95"]) or (b["hi95"] < a["lo95"])) if not any(pd.isna(x) for x in [a["lo95"], a["hi95"], b["lo95"], b["hi95"]]) else False
    return eff, excl


def _effect_T4(table: pd.DataFrame, permission: str) -> tuple[float, bool] | None:
    """effect = mean (malware - benign) over 2018-2021; band excludes zero if the malware band is entirely above/below benign in every year."""
    g = table[table["permission"] == permission]
    if len(g) == 0 or g["difference"].isna().all():
        return None
    eff = float(g["difference"].mean()); ok = g.dropna(subset=["malware_lo95", "malware_hi95", "benign"])
    excl = bool(len(ok) == len(g) and ((ok["malware_lo95"] > ok["benign"]).all() or (ok["malware_hi95"] < ok["benign"]).all()))
    return eff, excl


def _effect_T6(table: pd.DataFrame, a: str, b: str, y0: int = 2019, y1: int = 2024) -> tuple[float, bool] | None:
    g = table[(table["type_a"].isin([a, b])) & (table["type_b"].isin([a, b]))]
    r0 = g[g["year"].astype(str) == str(y0)]; r1 = g[g["year"].astype(str) == str(y1)]
    if len(r0) == 0 or len(r1) == 0:
        return None
    return float(r1.iloc[0]["js_distance"] - r0.iloc[0]["js_distance"]), bool(not r0.iloc[0]["thin"] and not r1.iloc[0]["thin"])


def _fmt(e: tuple[float, bool] | None) -> str:
    if e is None:
        return "n/a"
    eff, excl = e; return f"{'+' if eff > 0 else '-' if eff < 0 else '0'}{abs(eff):.3f}{'*' if excl else ''}"


def build_stability(root: Path, arms: list[str], primary: str = "primary") -> pd.DataFrame:
    """root/<arm>/T2_… tables; returns the matrix with a verdict column."""
    def table(arm, name):
        p = root / arm / f"{name}.csv"; return pd.read_csv(p) if p.exists() else None
    rows = []; prim = {n: table(primary, n) for n in ["T2_dangerous_prevalence", "T3_component_prevalence", "T4_matched_benign_vs_malware", "T6_type_jsd", "scorecard"]}
    items = []
    if prim["T2_dangerous_prevalence"] is not None:
        items += [("T2 change 2018->2025", "T2_dangerous_prevalence", p, lambda t, p=p: _effect_T2T3(t, p)) for p in sorted(prim["T2_dangerous_prevalence"]["permission"].unique())]
    if prim["T3_component_prevalence"] is not None:
        items += [("T3 change 2018->2025", "T3_component_prevalence", p, lambda t, p=p: _effect_T2T3(t, p)) for p in sorted(prim["T3_component_prevalence"]["permission"].unique())]
    if prim["T4_matched_benign_vs_malware"] is not None:
        items += [("T4 mean malware-benign 2018-2021", "T4_matched_benign_vs_malware", p, lambda t, p=p: _effect_T4(t, p)) for p in sorted(prim["T4_matched_benign_vs_malware"]["permission"].unique())]
    items += [("T6 JSD 2024-2019", "T6_type_jsd", "banker|rat", lambda t: _effect_T6(t, "banker", "rat"))]
    for label, tname, key, fn in items:
        row = {"item": label, "table": tname, "permission_or_pair": key}; signs = {}
        for arm in arms:
            t = table(arm, tname); e = fn(t) if t is not None else None; row[arm] = _fmt(e)
            if e is not None and e[0] != 0:
                signs[arm] = np.sign(e[0])
        if primary in signs:
            flips = [a for a, s in signs.items() if s != signs[primary]]
            prim_excl = row[primary].endswith("*")
            row["verdict"] = "COMPOSITION-DEPENDENT" if flips else ("REAL" if prim_excl else "REAL(sign-stable; primary band includes zero)")
            row["flipping_arms"] = "|".join(flips)
        else:
            row["verdict"] = "UNDEFINED"; row["flipping_arms"] = ""
        rows.append(row)
    # scorecard verdict rows
    if prim["scorecard"] is not None:
        for pred in prim["scorecard"]["prediction"]:
            row = {"item": "scorecard verdict", "table": "scorecard", "permission_or_pair": pred}; verdicts = {}
            for arm in arms:
                t = table(arm, "scorecard")
                if t is None: row[arm] = "n/a"; continue
                v = t[t["prediction"] == pred]["verdict"].iloc[0]; row[arm] = v; verdicts[arm] = v
            flips = [a for a, v in verdicts.items() if v != verdicts.get(primary)]
            row["verdict"] = "COMPOSITION-DEPENDENT" if flips else "REAL"; row["flipping_arms"] = "|".join(flips); rows.append(row)
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--primary", required=True, help="directory holding the primary arm tables"); ap.add_argument("--sensitivity", required=True, help="directory holding <arm>/ subdirectories"); ap.add_argument("--out", required=True)
    a = ap.parse_args(argv); root = Path(a.sensitivity); arms = sorted(p.name for p in root.iterdir() if p.is_dir())
    # the primary lives elsewhere: symlink-free approach — build with a temporary mapping
    tmp_root = root.parent / "_stability_root"; tmp_root.mkdir(exist_ok=True)
    link = tmp_root / "primary"
    if not link.exists(): link.symlink_to(Path(a.primary).resolve())
    for arm in arms:
        l = tmp_root / arm
        if not l.exists(): l.symlink_to((root / arm).resolve())
    df = build_stability(tmp_root, ["primary"] + arms); df.to_csv(a.out, index=False)
    print(df[["item", "permission_or_pair", "verdict", "flipping_arms"]].to_string(index=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
