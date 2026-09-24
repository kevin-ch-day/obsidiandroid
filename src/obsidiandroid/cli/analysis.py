"""Inspect/export database-native analytical runs without source/provider writes."""

import argparse
import json
from pathlib import Path


def configured_store(option_file=None, database="obsidiandroid_core_prod"):
    import mysql.connector
    from obsidiandroid.analysis_persistence.service import AnalysisStore

    option = Path(
        option_file or Path.home() / ".config/obsidiandroid/analysis-writer.cnf"
    )
    if not option.is_file():
        raise ValueError("Analytical connection not configured")
    return AnalysisStore(
        lambda: mysql.connector.connect(
            option_files=str(option), database=database, autocommit=False
        ),
        database=database,
        allow_production=database == "obsidiandroid_core_prod",
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action", choices=["history", "show", "predictions", "verify", "export", "run"]
    )
    p.add_argument("--run-id")
    p.add_argument("--output", type=Path)
    p.add_argument("--option-file", type=Path)
    p.add_argument("--database", default="obsidiandroid_core_prod")
    p.add_argument("--profile")
    p.add_argument("--persist", action="store_true")
    p.add_argument("--plan-only", action="store_true")
    args = p.parse_args(argv)
    if args.action == "run" and not args.profile:
        p.error("run requires --profile")
    if args.action in {"show", "predictions", "verify", "export"} and not args.run_id:
        p.error("run ID required")
    if args.action == "export" and args.output is None:
        p.error("export destination required")
    if args.action != "run" and (args.persist or args.plan_only or args.profile):
        p.error("--persist, --plan-only and --profile require run")
    if args.action != "export" and args.output is not None:
        p.error("--output requires export")
    try:
        if args.action == "run":
            if args.plan_only:
                from obsidiandroid.analysis_persistence.preflight import build_plan

                result = build_plan(
                    args.profile,
                    configured_store(args.option_file, args.database),
                    persist=args.persist,
                )
            else:
                if args.option_file or args.database != "obsidiandroid_core_prod":
                    raise ValueError(
                        "Pipeline execution uses the configured production writer; alternate targets are inspection-only"
                    )
                from obsidiandroid.pipeline import run_pipeline

                return run_pipeline(
                    profile_ref=args.profile, analysis_persistence=args.persist
                )
        else:
            store = configured_store(args.option_file, args.database)
            if args.action == "history":
                result = store.history()
            else:
                if args.action == "export":
                    from obsidiandroid.analysis_persistence.export import export_run

                    result = export_run(store, args.run_id, args.output)
                else:
                    result = store.show(args.run_id)
                    if args.action == "predictions":
                        result = result["prediction"]
                    elif args.action == "verify":
                        from obsidiandroid.analysis_persistence.export import verify_artifacts

                        result = verify_artifacts(result)
        print(json.dumps(result, indent=2, default=str))
        if args.action == "verify" and result["status"] == "unverified_artifacts":
            return 2
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


def review_native_runs(*, latest=False):
    """Prefer native records when configured; return whether a DB view was shown."""
    option = Path.home() / ".config/obsidiandroid/analysis-writer.cnf"
    if not option.is_file():
        return False
    try:
        store = configured_store(option)
        rows = store.history(1 if latest else 20)
        if not rows:
            return False
        print("Persisted analytical runs (governed assessments are separate)")
        for row in rows:
            meta = json.loads(row["metadata_json"])
            print(
                f"{row['run_id']} | {row['run_status']} | {meta['spec']['profile']} | samples={meta.get('sample_count', 'pending')}"
            )
        if latest:
            result = store.show(rows[0]["run_id"])
            print(
                json.dumps(
                    {
                        "run": rows[0],
                        "models": result["model_execution"],
                        "metrics": result["model_metric"],
                        "prediction_count": len(result["prediction"]),
                        "artifacts": result["core_artifact"],
                    },
                    indent=2,
                    default=str,
                )
            )
        return True
    except Exception as exc:
        print("Persisted analytical history unavailable: " + type(exc).__name__)
        return True
