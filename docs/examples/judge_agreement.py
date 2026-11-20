"""Reproduce the article's constructed judge decisions, without calling a model."""

import json
from collections import Counter
from collections.abc import Sequence


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize(reference: Sequence[str], decisions: Sequence[str]) -> dict:
    """Count approvals, rejections and deferrals against a fixed reference."""
    if not reference or len(reference) != len(decisions):
        raise ValueError("Provide equally sized, nonempty reference and decision sequences")
    if any(label not in ("accept", "reject") for label in reference):
        raise ValueError("Reference labels must be accept or reject")
    if any(label not in ("accept", "reject", "defer") for label in decisions):
        raise ValueError("Decisions must be accept, reject or defer")

    cells = Counter(zip(reference, decisions, strict=True))
    correct_approvals = cells["accept", "accept"]
    correct_rejections = cells["reject", "reject"]
    false_approvals = cells["reject", "accept"]
    false_rejections = cells["accept", "reject"]
    deferred_acceptable = cells["accept", "defer"]
    deferred_unacceptable = cells["reject", "defer"]
    total = len(reference)
    decided = total - deferred_acceptable - deferred_unacceptable
    unacceptable = reference.count("reject")
    acceptable = total - unacceptable
    return {
        "total": total,
        "correct_approvals": correct_approvals,
        "correct_rejections": correct_rejections,
        "false_approvals": false_approvals,
        "false_rejections": false_rejections,
        "deferred_acceptable": deferred_acceptable,
        "deferred_unacceptable": deferred_unacceptable,
        "automatic_coverage": ratio(decided, total),
        "agreement_among_decided": ratio(correct_approvals + correct_rejections, decided),
        "false_approval_rate_among_unacceptable": ratio(false_approvals, unacceptable),
        "false_rejection_rate_among_acceptable": ratio(false_rejections, acceptable),
        "unacceptable_share_of_approvals": ratio(
            false_approvals, correct_approvals + false_approvals
        ),
        "rejection_recall_among_unacceptable": ratio(correct_rejections, unacceptable),
    }


def example() -> dict:
    reference = ["accept"] * 95 + ["reject"] * 5
    decisions = {
        "approve_everything": ["accept"] * 100,
        "catch_four_reject_eight_good": ["reject"] * 8
        + ["accept"] * 87
        + ["reject"] * 4
        + ["accept"],
        "defer_all_five_bad": ["accept"] * 95 + ["defer"] * 5,
    }
    return {
        "provenance": (
            "Constructed reference labels and fixed decisions for arithmetic only. "
            "No model calls or human annotation experiment. "
            "The deferral example assumes all five unacceptable answers are identified; "
            "it does not demonstrate a working routing policy."
        ),
        "cases": [
            {
                "id": f"case-{i + 1:03}",
                "reference": label,
                "decisions": {name: values[i] for name, values in decisions.items()},
            }
            for i, label in enumerate(reference)
        ],
        "summaries": {name: summarize(reference, values) for name, values in decisions.items()},
    }


if __name__ == "__main__":
    print(json.dumps(example(), indent=2, allow_nan=False))
