#!/usr/bin/env python3
"""Generate permission-pattern interpretation artifacts from saved run diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from obsidiandroid.cli.menu import run_locator as rl
from obsidiandroid.pipeline import stage_permission_trends_report as report_stage
from obsidiandroid.pipeline.permission_trends.attack_mapping import (
    build_attack_mobile_hypotheses,
)


def _pretty_permission(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("perm__"):
        raw = raw[len("perm__") :]
    raw = raw.replace("android_permission_", "")
    raw = raw.replace("_", " ").upper()
    return raw


def _permission_feature_to_mapping_key(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("perm__android_permission_"):
        return "android.permission." + raw[len("perm__android_permission_") :]
    return raw


def _resolve_run_root(*, repo_root: Path, run_id: str = "", run_root_arg: str = "", latest: bool = False) -> Path:
    """Resolve canonical run root from explicit path, run_id, or latest manifest."""
    if run_root_arg:
        return Path(run_root_arg).resolve()
    if latest:
        latest_run_id = rl.read_latest_run_id()
        if not latest_run_id:
            raise SystemExit("could not resolve latest run id from manifests/pointers")
        run_id = latest_run_id
    if not run_id:
        raise SystemExit("provide run_id, --run-root, or --latest")
    manifest_payload, manifest_path = rl.resolve_manifest_for_run_id(
        str(run_id).strip(),
        runs_dir=repo_root / "output" / "runs",
    )
    if not manifest_payload:
        raise SystemExit(f"run directory not found for run_id: {run_id}")
    return rl.resolve_run_root_for_manifest(
        manifest_payload,
        run_id=str(run_id).strip(),
        manifest_path=manifest_path,
    )


def _load_artifacts(run_dir: Path, run_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    diagnostics = run_dir / "diagnostics"
    labels = pd.read_csv(diagnostics / f"aligned_labels_{run_id}.csv")
    features = pd.read_csv(diagnostics / f"aligned_features_{run_id}.csv.gz")
    survival = pd.read_csv(diagnostics / f"permission_training_survival_{run_id}.csv")
    return labels, features, survival


def _build_permission_matrix(features: pd.DataFrame, survival: pd.DataFrame) -> pd.DataFrame:
    derived_aggregate_columns = {
        "perm__dangerous_count",
        "perm__normal_count",
        "perm__oem_count",
        "perm__total_count",
    }
    kept = survival[
        ~survival["dropped_by_low_information_prune"].astype(bool)
        & ~survival["dropped_by_leakage_prune"].astype(bool)
    ]["column"].astype(str)
    permission_cols = sorted(
        [c for c in kept if c.startswith("perm__") and c not in derived_aggregate_columns]
    )
    matrix = features[["sample_id", *permission_cols]].copy()
    for col in permission_cols:
        matrix[col] = pd.to_numeric(matrix[col], errors="coerce").fillna(0)
    return matrix


def _build_summary(
    *,
    run_id: str,
    out_dir: Path,
    type_prev: pd.DataFrame,
    family_prev: pd.DataFrame,
    type_enrich: pd.DataFrame,
    family_enrich: pd.DataFrame,
    family_sim: pd.DataFrame,
    attack_df: pd.DataFrame,
) -> None:
    lines = [
        "# Permission Pattern Interpretation Summary",
        "",
        f"Run ID: `{run_id}`",
        "",
        "Permissions are interpreted here as static declared-capability signals.",
        "They are not direct proof of runtime behavior, operator intent, or causal malicious activity.",
        "",
        "## Strongest common Android malware permissions",
    ]

    common = (
        type_prev.groupby("permission", dropna=False)["positive_count"]
        .sum()
        .sort_values(ascending=False)
        .head(12)
    )
    for permission, count in common.items():
        lines.append(f"- `{_pretty_permission(permission)}`: positive_count={int(count)}")

    lines.extend(["", "## Strongest banker-vs-nonbanker permissions"])
    banker = type_enrich[type_enrich["type_slug"].astype(str) == "banker"].copy()
    banker = banker.sort_values(
        ["fdr_q_value", "odds_ratio", "type_prevalence_pct"],
        ascending=[True, False, False],
        kind="mergesort",
    )
    banker_pattern_rows = banker.copy()
    banker = banker[banker["pattern_level"].fillna(3).astype(int) > 3].head(10)
    if banker.empty:
        if (banker_pattern_rows["pattern_level"].fillna(0).astype(int) == 2).any():
            lines.append("- Pattern result: Conflicting Evidence.")
        else:
            lines.append("- Pattern result: No Pattern Found.")
    else:
        for _, row in banker.iterrows():
            lines.append(
                f"- `{_pretty_permission(row['permission'])}`: "
                f"banker={float(row['type_prevalence_pct']):.1f}%, "
                f"nonbanker={float(row['non_type_prevalence_pct']):.1f}%, "
                f"OR={float(row['odds_ratio']):.2f}, q={float(row['fdr_q_value']):.3e}, "
                f"pattern={row.get('pattern_label', 'Inconclusive')}"
            )

    lines.extend(["", "## Strongest RAT and spyware permission patterns"])
    for target_type in ("rat", "spyware"):
        subset = type_enrich[type_enrich["type_slug"].astype(str) == target_type].copy()
        subset = subset.sort_values(
            ["fdr_q_value", "odds_ratio", "type_prevalence_pct"],
            ascending=[True, False, False],
            kind="mergesort",
        )
        subset_pattern_rows = subset.copy()
        subset = subset[subset["pattern_level"].fillna(3).astype(int) > 3].head(8)
        lines.append("")
        lines.append(f"### {target_type}")
        if subset.empty:
            if (subset_pattern_rows["pattern_level"].fillna(0).astype(int) == 2).any():
                lines.append("- Pattern result: Conflicting Evidence.")
            else:
                lines.append("- Pattern result: No Pattern Found.")
            continue
        for _, row in subset.iterrows():
            lines.append(
                f"- `{_pretty_permission(row['permission'])}`: "
                f"{target_type}={float(row['type_prevalence_pct']):.1f}%, "
                f"non-{target_type}={float(row['non_type_prevalence_pct']):.1f}%, "
                f"OR={float(row['odds_ratio']):.2f}, q={float(row['fdr_q_value']):.3e}, "
                f"pattern={row.get('pattern_label', 'Inconclusive')}"
            )

    lines.extend(["", "## Family clusters"])
    same_type = family_sim[family_sim["same_type_flag"].astype(bool)].sort_values(
        ["cosine_similarity", "jaccard_similarity", "spearman_correlation"],
        ascending=[False, False, False],
        kind="mergesort",
    ).head(12)
    if same_type.empty:
        lines.append("- No benchmark-eligible same-type family clusters were available.")
    else:
        for _, row in same_type.iterrows():
            lines.append(
                f"- `{row['family_a']}` vs `{row['family_b']}` ({row['type_a']}): "
                f"cosine={float(row['cosine_similarity']):.3f}, "
                f"jaccard={float(row['jaccard_similarity']):.3f}, "
                f"spearman={float(row['spearman_correlation']):.3f}"
            )

    lines.extend(["", "## Anomalous families whose permission profile may not match their taxonomy"])
    best_pairs = []
    all_fams = sorted(set(family_sim["family_a"].astype(str)) | set(family_sim["family_b"].astype(str)))
    for fam in all_fams:
        subset = family_sim[
            (family_sim["family_a"].astype(str) == fam) | (family_sim["family_b"].astype(str) == fam)
        ].copy()
        if subset.empty:
            continue
        subset = subset.sort_values(
            ["cosine_similarity", "jaccard_similarity", "spearman_correlation"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        top = subset.iloc[0]
        if not bool(top["same_type_flag"]):
            fam_name = fam
            other = str(top["family_b"] if str(top["family_a"]) == fam_name else top["family_a"])
            fam_type = str(top["type_a"] if str(top["family_a"]) == fam_name else top["type_b"])
            other_type = str(top["type_b"] if str(top["family_a"]) == fam_name else top["type_a"])
            best_pairs.append((float(top["cosine_similarity"]), fam_name, fam_type, other, other_type, top))
    best_pairs.sort(reverse=True)
    if not best_pairs:
        lines.append("- No strong cross-type similarity anomalies were detected on the benchmark-eligible family surface.")
    else:
        for _, fam_name, fam_type, other, other_type, top in best_pairs[:8]:
            lines.append(
                f"- `{fam_name}` ({fam_type}) is closest to `{other}` ({other_type}) "
                f"with cosine={float(top['cosine_similarity']):.3f}, "
                f"jaccard={float(top['jaccard_similarity']):.3f}. "
                "Treat as a taxonomy-review candidate rather than a relabeling conclusion."
            )

    lines.extend(["", "## Candidate MITRE ATT&CK mapping notes"])
    if attack_df.empty:
        lines.append("- No ATT&CK-Mobile permission-derived hypotheses met the configured mapping rules.")
    else:
        for _, row in attack_df.head(12).iterrows():
            lines.append(
                f"- {row['group_kind']} `{row['group_value']}` -> `{row['attack_id']}` {row['attack_name']} "
                f"[{row['confidence']}] via `{row['evidence_permissions']}`"
            )

    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "- Type-level signal is broader and usually more stable than unrestricted family signal.",
            "- Family-level benchmark interpretation should emphasize benchmark-eligible families (support >= 3).",
            "- Families below support 3 remain visible in diagnostics, but they should not be treated as supervised benchmark evidence.",
            "- AV-parsed family labels and vendor-side naming should not be treated as independent proof of family identity.",
        ]
    )
    (out_dir / "permission_pattern_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate(run_id: str, output_dir: Path | None = None, *, run_root: Path | None = None) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    run_dir = run_root.resolve() if run_root is not None else _resolve_run_root(repo_root=repo_root, run_id=run_id)
    diagnostics = run_dir / "diagnostics"
    manifest_payload = rl.read_json_object(run_dir / "run_manifest.json")
    resolved_run_id = str(manifest_payload.get("run_id", "")).strip() or run_id or run_dir.name
    out_dir = output_dir or diagnostics / "permission_pattern_interpretation"
    out_dir.mkdir(parents=True, exist_ok=True)

    labels, features, survival = _load_artifacts(run_dir, resolved_run_id)
    permission_matrix = _build_permission_matrix(features, survival)

    sample_core = labels.copy()
    prevalence_by_type = report_stage._build_permission_prevalence_by_type(sample_core, permission_matrix)
    prevalence_by_type = prevalence_by_type.rename(
        columns={"n_samples": "type_sample_count", "permission_positive_count": "positive_count"}
    )
    prevalence_by_family = report_stage._build_permission_prevalence_by_family(sample_core, permission_matrix)
    prevalence_by_family = prevalence_by_family.rename(
        columns={"benchmark_eligible_n_ge_3": "benchmark_eligible"}
    )
    type_enrichment = report_stage._build_permission_type_enrichment(sample_core, permission_matrix).rename(
        columns={"p_value": "fisher_or_chi_square_p", "q_value_fdr": "fdr_q_value"}
    )
    family_enrichment = report_stage._build_permission_family_enrichment(sample_core, permission_matrix)
    family_enrichment = family_enrichment.rename(
        columns={
            "p_value": "fisher_or_chi_square_p",
            "q_value_fdr": "fdr_q_value",
            "benchmark_eligible_n_ge_3": "benchmark_eligible",
        }
    )

    eligible_family_prev = prevalence_by_family[prevalence_by_family["benchmark_eligible"].astype(bool)].copy()
    family_similarity = report_stage._build_family_permission_similarity(eligible_family_prev)

    type_attack = build_attack_mobile_hypotheses(
        prevalence_df=prevalence_by_type.rename(
            columns={"type_sample_count": "sample_count", "prevalence_pct": "prevalence"}
        ).assign(
            permission=lambda df: df["permission"].map(_permission_feature_to_mapping_key),
            prevalence=lambda df: pd.to_numeric(df["prevalence"], errors="coerce").fillna(0.0) / 100.0,
        ),
        run_id=resolved_run_id,
        group_field="type_slug",
        group_kind="type",
        sample_count_field="sample_count",
        prevalence_field="prevalence",
    )
    family_attack = build_attack_mobile_hypotheses(
        prevalence_df=eligible_family_prev.rename(
            columns={"family_canonical": "group_value", "family_support": "sample_count", "prevalence_pct": "prevalence"}
        ).assign(
            permission=lambda df: df["permission"].map(_permission_feature_to_mapping_key),
            prevalence=lambda df: pd.to_numeric(df["prevalence"], errors="coerce").fillna(0.0) / 100.0,
        ),
        run_id=resolved_run_id,
        group_field="group_value",
        group_kind="family",
        sample_count_field="sample_count",
        prevalence_field="prevalence",
    )
    attack_df = pd.concat([type_attack, family_attack], ignore_index=True) if (not type_attack.empty or not family_attack.empty) else pd.DataFrame()

    prevalence_by_type.to_csv(out_dir / "permission_prevalence_by_type.csv", index=False)
    prevalence_by_family.to_csv(out_dir / "permission_prevalence_by_family.csv", index=False)
    type_enrichment.to_csv(out_dir / "permission_type_enrichment.csv", index=False)
    family_enrichment.to_csv(out_dir / "permission_family_enrichment.csv", index=False)
    family_similarity.to_csv(out_dir / "family_permission_similarity.csv", index=False)

    _build_summary(
        run_id=resolved_run_id,
        out_dir=out_dir,
        type_prev=prevalence_by_type,
        family_prev=prevalence_by_family,
        type_enrich=type_enrichment,
        family_enrich=family_enrichment,
        family_sim=family_similarity,
        attack_df=attack_df,
    )
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("run_id", nargs="?", default="", help="Run ID resolved through manifest-backed lookup.")
    selection.add_argument("--run-root", default="", help="Explicit canonical run root path.")
    selection.add_argument("--latest", action="store_true", help="Use the latest manifest-backed run.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional custom output directory")
    args = parser.parse_args()
    run_root = _resolve_run_root(
        repo_root=Path(__file__).resolve().parents[2],
        run_id=args.run_id,
        run_root_arg=args.run_root,
        latest=bool(args.latest),
    )
    manifest_payload = rl.read_json_object(run_root / "run_manifest.json")
    resolved_run_id = str(manifest_payload.get("run_id", "")).strip() or run_root.name
    out_dir = generate(resolved_run_id, args.output_dir, run_root=run_root)
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
