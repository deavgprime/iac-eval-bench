import hashlib
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "eval_awareness", Path(__file__).parents[1] / "docs/examples/eval_awareness.py"
)
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)


class EvalAwarenessTests(unittest.TestCase):
    def test_equal_final_answers_can_have_different_exposure(self):
        source = example.run_route(["archive"], expose_key=True)
        key = example.run_route(["answer_key"], expose_key=True)
        self.assertEqual(source["answer"], key["answer"])
        self.assertTrue(source["answer_correct"])
        self.assertTrue(key["answer_correct"])
        self.assertFalse(source["answer_key_returned"])
        self.assertTrue(key["answer_key_returned"])

    def test_primary_citation_does_not_erase_prior_key_access(self):
        result = example.run_route(["answer_key", "archive"], expose_key=True)
        self.assertEqual(result["citation"], "archive")
        self.assertTrue(result["answer_key_returned"])
        self.assertEqual(
            [event["requested"] for event in result["trace"]], ["answer_key", "archive"]
        )

    def test_denied_key_returns_no_content_or_answer(self):
        result = example.run_route(["answer_key"], expose_key=False)
        self.assertIsNone(result["answer"])
        self.assertIsNone(result["citation"])
        self.assertFalse(result["answer_correct"])
        self.assertFalse(result["answer_key_returned"])
        self.assertEqual(result["denied_requests"], 1)
        self.assertNotIn("text", result["trace"][0])
        self.assertNotIn("sha256", result["trace"][0])

    def test_denied_request_remains_visible_after_success(self):
        result = example.run_route(["answer_key", "archive"], expose_key=False)
        self.assertTrue(result["answer_correct"])
        self.assertFalse(result["answer_key_returned"])
        self.assertEqual(result["denied_requests"], 1)
        self.assertEqual(result["citation"], "archive")
        self.assertEqual([event["status"] for event in result["trace"]], ["denied", "returned"])

    def test_denied_last_request_does_not_erase_prior_source(self):
        result = example.run_route(["archive", "answer_key"], expose_key=False)
        self.assertTrue(result["answer_correct"])
        self.assertEqual(result["citation"], "archive")
        self.assertEqual(result["denied_requests"], 1)

    def test_returned_documents_have_verifiable_content_hashes(self):
        for record in example.example()["records"]:
            for event in record["trace"]:
                if event["status"] == "returned":
                    self.assertEqual(
                        event["sha256"], hashlib.sha256(event["text"].encode()).hexdigest()
                    )

    def test_unknown_or_empty_routes_fail_explicitly(self):
        for route in ([], ["missing"], ["archive", "missing"]):
            with self.subTest(route=route):
                with self.assertRaises(ValueError):
                    example.run_route(route, expose_key=True)

    def test_all_six_conditions_are_retained(self):
        records = example.example()["records"]
        self.assertEqual(len(records), 6)
        self.assertEqual(len({record["id"] for record in records}), 6)
        self.assertEqual(sum(record["answer_correct"] for record in records), 5)
        self.assertEqual(sum(record["answer_key_returned"] for record in records), 2)
        self.assertEqual(sum(record["denied_requests"] for record in records), 2)
