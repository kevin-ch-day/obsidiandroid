"""Validate a human-reviewed missing-primary backfill ledger without applying it.

This script never connects to or mutates the catalog.  It verifies that a
review ledger still matches the generated authority-backed proposal package so
that a future, separately authorized apply operation cannot use stale or
altered proposal membership.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)


OUTPUT_DIR = Path("output") / "diagnostics"
DEFAULT_PROPOSALS = OUTPUT_DIR / "missing_primary_label_authority_backfill_proposals_latest.csv"
DEFAULT_LEDGER = OUTPUT_DIR / "missing_primary_label_authority_backfill_review_template_latest.csv"
DEFAULT_REPORT = OUTPUT_DIR / "missing_primary_label_authority_backfill_review_validation_latest.json"
DECISIONS = frozenset({"pending", "approved", "rejected"})
IDENTITY_COLUMNS = (
    "proposal_id",
    "proposed_classification_primary",
    "authority_type_slug",
    "authority_parent_type_slug",
    "authority_family_slug",
    "confidence_bucket",
    "sample_count",
    "sample_id_hash",
)
REQUIRED_LEDGER_COLUMNS = frozenset(
    {*IDENTITY_COLUMNS, "review_status", "decision", "reviewer", "reviewed_at_utc", "review_note"}
)


def _clean(value: object) -> str:
    """Return a stable text representation for CSV comparison."""
    return "" if pd.isna(value) else str(value).strip()


def validate_review_ledger(proposals: pd.DataFrame, ledger: pd.DataFrame) -> dict[str, object]:
    """Validate identity and review metadata for a proposed backfill ledger."""
    proposal_columns = set(proposals.columns)
    ledger_columns = set(ledger.columns)
    missing_proposal_columns = sorted(set(IDENTITY_COLUMNS) - proposal_columns)
    missing_ledger_columns = sorted(REQUIRED_LEDGER_COLUMNS - ledger_columns)
    errors: list[str] = []
    if missing_proposal_columns:
        errors.append("proposal_missing_columns=" + ",".join(missing_proposal_columns))
    if missing_ledger_columns:
        errors.append("ledger_missing_columns=" + ",".join(missing_ledger_columns))
    if errors:
        return {
            "valid": False,
            "proposal_count": int(len(proposals)),
            "ledger_count": int(len(ledger)),
            "approved_proposal_count": 0,
            "approved_sample_count": 0,
            "errors": errors,
        }

    proposal = proposals.loc[:, IDENTITY_COLUMNS].copy()
    review = ledger.loc[:, list(REQUIRED_LEDGER_COLUMNS)].copy()
    proposal["proposal_id"] = proposal["proposal_id"].map(_clean)
    review["proposal_id"] = review["proposal_id"].map(_clean)
    if proposal["proposal_id"].duplicated().any():
        errors.append("proposal_ids_not_unique")
    if review["proposal_id"].duplicated().any():
        errors.append("ledger_ids_not_unique")

    proposal_ids = set(proposal["proposal_id"])
    ledger_ids = set(review["proposal_id"])
    unknown_ids = sorted(ledger_ids - proposal_ids)
    missing_ids = sorted(proposal_ids - ledger_ids)
    if unknown_ids:
        errors.append("ledger_unknown_proposal_ids=" + ",".join(unknown_ids[:10]))
    if missing_ids:
        errors.append("ledger_missing_proposal_ids=" + ",".join(missing_ids[:10]))

    proposal_by_id = proposal.set_index("proposal_id")
    review_by_id = review.set_index("proposal_id")
    identity_mismatch_ids: list[str] = []
    if not unknown_ids and not missing_ids:
        for proposal_id, proposal_row in proposal_by_id.iterrows():
            review_row = review_by_id.loc[proposal_id]
            if any(
                _clean(proposal_row[column]) != _clean(review_row[column])
                for column in IDENTITY_COLUMNS
                if column != "proposal_id"
            ):
                identity_mismatch_ids.append(str(proposal_id))
        if identity_mismatch_ids:
            errors.append("ledger_identity_mismatch=" + ",".join(identity_mismatch_ids[:10]))

    decisions = review["decision"].map(lambda value: _clean(value).lower())
    invalid_decision_ids = review.loc[~decisions.isin(DECISIONS), "proposal_id"].astype(str).tolist()
    if invalid_decision_ids:
        errors.append("invalid_decisions=" + ",".join(invalid_decision_ids[:10]))

    final_decisions = decisions[decisions.isin(DECISIONS)]
    reviewer = review["reviewer"].map(_clean)
    reviewed_at = review["reviewed_at_utc"].map(_clean)
    review_note = review["review_note"].map(_clean)
    resolved = final_decisions.isin({"approved", "rejected"})
    metadata_missing = resolved & ((reviewer == "") | (reviewed_at == "") | (review_note == ""))
    if metadata_missing.any():
        errors.append(
            "resolved_decision_missing_reviewer_metadata="
            + ",".join(review.loc[metadata_missing, "proposal_id"].astype(str).tolist()[:10])
        )

    approved_mask = decisions.eq("approved")
    approved_sample_count = int(
        pd.to_numeric(review.loc[approved_mask, "sample_count"], errors="coerce").fillna(0).sum()
    )
    return {
        "valid": not errors,
        "proposal_count": int(len(proposal)),
        "ledger_count": int(len(review)),
        "approved_proposal_count": int(approved_mask.sum()),
        "approved_sample_count": approved_sample_count,
        "pending_proposal_count": int(decisions.eq("pending").sum()),
        "rejected_proposal_count": int(decisions.eq("rejected").sum()),
        "identity_mismatch_count": len(identity_mismatch_ids),
        "errors": errors,
    }


def main() -> int:
    """Validate paths supplied by the operator and write a read-only report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    proposals = pd.read_csv(args.proposals) if args.proposals.is_file() else pd.DataFrame()
    ledger = pd.read_csv(args.ledger) if args.ledger.is_file() else pd.DataFrame()
    report = validate_review_ledger(proposals, ledger)
    report.update(
        {
            "proposals_path": str(args.proposals),
            "ledger_path": str(args.ledger),
            "mode": "validation_only_no_catalog_write",
        }
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[EXPORT] Review-ledger validation: {args.report.as_posix()}")
    print(f"Valid: {bool(report['valid'])}")
    print(f"Approved proposals: {int(report['approved_proposal_count'])}")
    print(f"Approved samples: {int(report['approved_sample_count'])}")
    if report["errors"]:
        print("Errors: " + "; ".join(str(value) for value in report["errors"]))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
