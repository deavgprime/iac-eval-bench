import unittest

from iac_eval_bench.report import summarize


def row(task, score, *, error=False, cost=None):
    return {
        "task_id": task,
        "status": "provider_error" if error else "completed",
        "evaluation": None
        if error
        else {
            "score": score,
            "passed": score == 1,
            "stage": "passed" if score == 1 else "requirements",
        },
        "generation_seconds": None if error else 2,
        "estimated_cost_usd": cost,
        "input_tokens": None,
        "output_tokens": None,
    }


class ReportingAuditTests(unittest.TestCase):
    def test_partial_coverage_does_not_disappear_from_operational_metrics(self):
        result = summarize([row("a", 1), row("b", 0), row("c", None, error=True)])
        self.assertEqual(result["quality_pass_rate"], 0.5)
        self.assertAlmostEqual(result["operational_pass_rate"], 1 / 3)
        self.assertEqual(result["macro_score"], 0.5)
        self.assertAlmostEqual(result["operational_macro_score"], 1 / 3)
        self.assertEqual(result["task_coverage"], {"attempted": 3, "with_completions": 2})
        self.assertEqual(result["failure_stages"], {"requirements": 1})

    def test_macro_averages_tasks_not_attempts(self):
        result = summarize([row("a", 1) for _ in range(10)] + [row("b", 0)])
        self.assertEqual(result["macro_score"], 0.5)
        self.assertEqual(result["operational_macro_score"], 0.5)

    def test_missing_cost_is_unknown_even_when_other_attempt_is_free(self):
        result = summarize([row("a", 1, cost=0), row("b", 1, cost=None)])
        self.assertIsNone(result["estimated_cost_usd"])
        self.assertEqual(result["cost_covered_completions"], 1)
