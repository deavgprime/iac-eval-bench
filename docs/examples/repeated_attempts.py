"""Compare repeated-attempt metrics on constructed outcomes, without model calls."""

import argparse
import json
from fractions import Fraction
from itertools import combinations, product
from math import comb

OUTCOMES = (True, False, True, False)


def metrics(outcomes: tuple[bool, ...], k: int) -> tuple[Fraction, Fraction]:
    """Return exact fractions of k-subsets containing any pass and only passes."""
    if not outcomes or any(type(value) is not bool for value in outcomes):
        raise ValueError("Provide a nonempty sequence of Boolean outcomes.")
    if type(k) is not int or not 1 <= k <= len(outcomes):
        raise ValueError("k must be an integer from 1 through the number of attempts.")
    n, c = len(outcomes), sum(outcomes)
    denominator = comb(n, k)
    return (
        1 - Fraction(comb(n - c, k), denominator),
        Fraction(comb(c, k), denominator),
    )


def mean_metrics(tasks: tuple[tuple[bool, ...], ...], k: int):
    """Give each task equal weight, even if their attempt counts differ."""
    if not tasks:
        raise ValueError("Provide at least one task.")
    per_task = [metrics(outcomes, k) for outcomes in tasks]
    return tuple(sum(values, Fraction()) / len(tasks) for values in zip(*per_task))


def observations() -> dict:
    pairs = []
    for indexes in combinations(range(len(OUTCOMES)), 2):
        pair = tuple(OUTCOMES[index] for index in indexes)
        pairs.append(
            {
                "pair": "".join("ABCD"[index] for index in indexes),
                "outcomes": list(pair),
                "any_pass": any(pair),
                "all_pass": all(pair),
            }
        )
    return {
        "provenance": "Constructed Boolean outcomes. No model or Kubernetes runs.",
        "outcomes": dict(zip("ABCD", OUTCOMES)),
        "pairs": pairs,
        "metrics": [
            {
                "k": k,
                "pass_at_k": str(metrics(OUTCOMES, k)[0]),
                "pass_power_k": str(metrics(OUTCOMES, k)[1]),
            }
            for k in range(1, len(OUTCOMES) + 1)
        ],
    }


def verify() -> dict:
    # Enumeration checks the formula independently, including all-pass/all-fail cases.
    checked = 0
    for n in range(1, 9):
        for outcomes in product((False, True), repeat=n):
            previous_any, previous_all = Fraction(), Fraction(1)
            for k in range(1, n + 1):
                subsets = list(combinations(outcomes, k))
                expected = (
                    Fraction(sum(any(part) for part in subsets), len(subsets)),
                    Fraction(sum(all(part) for part in subsets), len(subsets)),
                )
                actual = metrics(outcomes, k)
                assert actual == expected, (outcomes, k, actual, expected)
                assert actual == metrics(tuple(reversed(outcomes)), k)
                assert 0 <= actual[1] <= actual[0] <= 1
                assert actual[0] >= previous_any and actual[1] <= previous_all
                if k == 1:
                    assert actual[0] == actual[1] == Fraction(sum(outcomes), n)
                previous_any, previous_all = actual
                checked += 1
    invalid = [
        ((), 1),
        ((True,), 0),
        ((True,), -1),
        ((True,), 2),
        ((True,), True),
        ((True,), 1.0),
        ((True,), "1"),
        ((1,), 1),
        ((None,), 1),
    ]
    for outcomes, k in invalid:
        try:
            metrics(outcomes, k)
        except ValueError:
            pass
        else:
            raise AssertionError((outcomes, k))
    assert metrics(OUTCOMES, 2) == (Fraction(5, 6), Fraction(1, 6))
    # Pooling attempts would give 1/4; equal task weighting must give 1/2.
    assert mean_metrics(((True,), (False, False, False)), 1) == (
        Fraction(1, 2),
        Fraction(1, 2),
    )
    assert mean_metrics(((True,) * 4, (False,) * 4), 2) == (Fraction(1, 2),) * 2
    assert mean_metrics((OUTCOMES, OUTCOMES), 2) == (Fraction(5, 6), Fraction(1, 6))
    for tasks, k in (((), 1), (((True,), (True, False)), 2)):
        try:
            mean_metrics(tasks, k)
        except ValueError:
            pass
        else:
            raise AssertionError((tasks, k))
    return {
        "exhaustive_sequence_k_cases": checked,
        "invalid_input_cases": len(invalid) + 2,
        "task_aggregation_checks": 3,
        "status": "passed",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Cross-check by enumeration")
    args = parser.parse_args()
    result = observations()
    if args.verify:
        result["verification"] = verify()
    print(json.dumps(result, indent=2))
