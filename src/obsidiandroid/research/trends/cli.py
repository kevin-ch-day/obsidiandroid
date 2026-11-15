"""CLI: python -m obsidiandroid.research.trends run --parquet … --digest … --out … [--sensitivity NAME|all]"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from obsidiandroid.research.trends.dataset import load_dataset
from obsidiandroid.research.trends.figures import load_annotations
from obsidiandroid.research.trends.study import arm_catalog, run_study


def dangerous_from_fixture(path: Path) -> list[str]:
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    return sorted({d["canonical_name"] for d in fixture["declaration_revisions"] if (d.get("protection") or {}).get("base_token") == "dangerous"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="obsidiandroid.research.trends", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True); run = sub.add_parser("run")
    run.add_argument("--parquet", required=True); run.add_argument("--digest", required=True, help="expected sha256 of the Parquet; load refuses on mismatch")
    run.add_argument("--out", required=True); run.add_argument("--prereg", required=True, help="PREREGISTRATION.md (its sha256 is stamped on every table)")
    run.add_argument("--annotations", required=True); run.add_argument("--fixture", required=True, help="pi_identity_catalog_fixture.json (dangerous tier)")
    run.add_argument("--bands", default=None); run.add_argument("--sensitivity", default=None, help="arm name, comma list, or 'all'"); run.add_argument("--no-figures", action="store_true")
    run.add_argument("--tables", default="T1,T2,T3,T4,T5,T6,T7,T8,scorecard")
    args = parser.parse_args(argv)
    ds = load_dataset(args.parquet, args.digest); prereg_hash = hashlib.sha256(Path(args.prereg).read_bytes()).hexdigest()
    annotations = load_annotations(args.annotations); dangerous = dangerous_from_fixture(Path(args.fixture)); out = Path(args.out)
    arms = arm_catalog(sorted(ds.frame["batch"].unique()))
    if args.sensitivity is None: selected = ["primary"]
    elif args.sensitivity == "all": selected = list(arms)
    else: selected = [a.strip() for a in args.sensitivity.split(",")]
    manifest = {"dataset_sha256": ds.digest, "preregistration_sha256": prereg_hash, "group_check": ds.check_stored_groups(), "arms": {}}
    for name in selected:
        cfg = arms[name]; t0 = time.time(); tables = tuple(args.tables.split(","))
        res = run_study(ds, cfg, out / ("primary" if name == "primary" else f"sensitivity/{name}"), prereg_hash, annotations, dangerous, args.bands, tables=tables, make_figures=not args.no_figures)
        manifest["arms"][name] = {"wall_clock_seconds": round(time.time() - t0, 1), "rows_malware": res["rows_malware"], "rows_benign": res["rows_benign"], "six_types": res["six_types"]}
        print(f"{name}: {manifest['arms'][name]}", flush=True)
    out.mkdir(parents=True, exist_ok=True); (out / "run_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    return 0
