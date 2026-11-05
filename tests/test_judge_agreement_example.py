import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "judge_agreement", Path(__file__).parents[1] / "docs/examples/judge_agreement.py"
)
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)


class JudgeAgreementTests(unittest.TestCase):
    def test_agreement_can_hide_all_unacceptable_answers(self):
        result = example.example()["summaries"]["approve_everything"]
        self.assertEqual(result["agreement_among_decided"], 0.95)
        self.assertEqual(result["false_approvals"], 5)
        self.assertEqual(result["false_approval_rate_among_unacceptable"], 1)
        self.assertEqual(result["rejection_recall_among_unacceptable"], 0)
        self.assertEqual(result["unacceptable_share_of_approvals"], 0.05)

    def test_lower_agreement_and_fewer_false_approvals(self):
        result = example.example()["summaries"]["catch_four_reject_eight_good"]
        self.assertEqual(result["agreement_among_decided"], 0.91)
        self.assertEqual(result["correct_approvals"], 87)
        self.assertEqual(result["correct_rejections"], 4)
        self.assertEqual(result["false_approvals"], 1)
        self.assertEqual(result["false_rejections"], 8)
        self.assertEqual(result["false_approval_rate_among_unacceptable"], 0.2)
        self.assertAlmostEqual(result["unacceptable_share_of_approvals"], 1 / 88)
        self.assertAlmostEqual(result["false_rejection_rate_among_acceptable"], 8 / 95)

    def test_deferral_does_not_become_a_correct_rejection(self):
        result = example.example()["summaries"]["defer_all_five_bad"]
        self.assertEqual(result["automatic_coverage"], 0.95)
        self.assertEqual(result["agreement_among_decided"], 1)
        self.assertEqual(result["deferred_unacceptable"], 5)
        self.assertEqual(result["correct_rejections"], 0)
        self.assertEqual(result["rejection_recall_among_unacceptable"], 0)

    def test_all_deferred_has_no_agreement_or_approval_denominator(self):
        result = example.summarize(["accept", "reject"], ["defer", "defer"])
        self.assertEqual(result["automatic_coverage"], 0)
        self.assertIsNone(result["agreement_among_decided"])
        self.assertIsNone(result["unacceptable_share_of_approvals"])
        self.assertEqual(result["deferred_acceptable"], 1)
        self.assertEqual(result["deferred_unacceptable"], 1)

    def test_absent_reference_class_is_not_zero_error(self):
        good_only = example.summarize(["accept"], ["accept"])
        self.assertIsNone(good_only["false_approval_rate_among_unacceptable"])
        self.assertIsNone(good_only["rejection_recall_among_unacceptable"])
        bad_only = example.summarize(["reject"], ["reject"])
        self.assertIsNone(bad_only["false_rejection_rate_among_acceptable"])
        self.assertIsNone(bad_only["unacceptable_share_of_approvals"])

    def test_opposite_decisions_have_no_agreement(self):
        result = example.summarize(["accept", "reject"], ["reject", "accept"])
        self.assertEqual(result["agreement_among_decided"], 0)
        self.assertEqual(result["false_approval_rate_among_unacceptable"], 1)
        self.assertEqual(result["false_rejection_rate_among_acceptable"], 1)

    def test_invalid_inputs_fail_instead_of_dropping_records(self):
        for reference, decisions in [
            ([], []),
            (["accept"], []),
            (["accept"], ["accept", "reject"]),
            (["defer"], ["accept"]),
            (["accept"], ["unknown"]),
            ([True], ["accept"]),
            (["reject"], [None]),
        ]:
            with self.subTest(reference=reference, decisions=decisions):
                with self.assertRaises(ValueError):
                    example.summarize(reference, decisions)

    def test_records_reconstruct_every_summary(self):
        output = example.example()
        self.assertEqual(len({row["id"] for row in output["cases"]}), 100)
        for name, expected in output["summaries"].items():
            actual = example.summarize(
                [row["reference"] for row in output["cases"]],
                [row["decisions"][name] for row in output["cases"]],
            )
            self.assertEqual(actual, expected)
            self.assertEqual(
                sum(
                    actual[key]
                    for key in (
                        "correct_approvals",
                        "correct_rejections",
                        "false_approvals",
                        "false_rejections",
                        "deferred_acceptable",
                        "deferred_unacceptable",
                    )
                ),
                100,
            )
