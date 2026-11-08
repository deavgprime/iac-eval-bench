"""Controls for the article's result classification and fixed candidates."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "docs/examples/environment_failures.py"
SPEC = importlib.util.spec_from_file_location("environment_example", EXAMPLE)
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)


class EnvironmentExampleTests(unittest.TestCase):
    def test_wrong_answer_is_not_a_resource_failure(self):
        self.assertEqual(
            example.assess(0, '{"total_cents": 11}', "", 12, False),
            ("wrong_answer", 11),
        )

    def test_timeout_does_not_accept_partial_output(self):
        self.assertEqual(
            example.assess(-9, '{"total_cents": 12}', "", 12, True),
            ("wall_timeout", None),
        )

    def test_failed_process_cannot_pass_from_stdout(self):
        self.assertEqual(
            example.assess(1, '{"total_cents": 12}', "error", 12, False),
            ("execution_error", None),
        )

    def test_memory_status_requires_matching_evidence(self):
        self.assertEqual(
            example.assess(20, "", "MemoryError\n", 12, False),
            ("address_space_exhausted", None),
        )
        self.assertEqual(
            example.assess(20, "", "different error", 12, False),
            ("execution_error", None),
        )

    def test_malformed_or_noninteger_answers_are_not_correct(self):
        for stdout in ["", "{}", "[]", '{"total_cents": true}', '{"total_cents": 1.0}']:
            with self.subTest(stdout=stdout):
                self.assertEqual(example.assess(0, stdout, "", 1, False)[0], "invalid_output")

    def test_fixed_candidates_against_small_known_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "costs.csv"
            for rows, total in [("", 0), ("a,0\n", 0), ("a,1\nb,10\nc,0\n", 11)]:
                path.write_text("row_id,amount_cents\n" + rows)
                for name in ["bulk", "stream"]:
                    with self.subTest(candidate=name, rows=rows):
                        namespace = {}
                        exec(example.PROGRAMS[name], namespace)
                        self.assertEqual(namespace["total"](path), total)
            namespace = {}
            exec(example.PROGRAMS["drop_first"], namespace)
            self.assertEqual(namespace["total"](path), 10)


if __name__ == "__main__":
    unittest.main()
