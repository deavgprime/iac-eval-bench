import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iac_eval_bench.cli import main
from iac_eval_bench.evaluator import HarnessError
from iac_eval_bench.providers import ProviderError
from iac_eval_bench.report import summarize
from iac_eval_bench.runner import run

ROOT = Path(__file__).resolve().parents[1]


def config(**changes):
    value = {
        "provider": "fixture",
        "fixture_dir": str(ROOT / "fixtures/reference"),
        "model": None,
        "model_revision": None,
        "endpoint": None,
        "repeat": 1,
        "seed": 42,
        "temperature": None,
        "timeout": 2,
        "input_rate": None,
        "output_rate": None,
        "tasks": ["deployment-resources", "service-routing"],
    }
    value.update(changes)
    return value


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run"
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)

    def test_resume_makes_no_duplicate_generation_requests(self):
        first = run(config(repeat=2), self.output)
        with patch("iac_eval_bench.runner.fixture", side_effect=AssertionError("unexpected call")):
            second = run(config(repeat=2), self.output, resume=True)
        self.assertEqual(first, second)
        self.assertEqual(second["attempts"], 4)
        self.assertIsNone(second["generation_latency_seconds"]["p50"])
        self.assertIsNone(second["estimated_cost_usd"])
        self.assertEqual(len((self.output / "records.jsonl").read_text().splitlines()), 4)

    def test_partial_run_resumes_only_missing_attempts(self):
        from iac_eval_bench.providers import fixture

        count = 0

        def interrupt(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise KeyboardInterrupt()
            return fixture(*args)

        with patch("iac_eval_bench.runner.fixture", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                run(config(), self.output)
        self.assertEqual(len(list((self.output / "attempts").glob("*.json"))), 1)
        with patch("iac_eval_bench.runner.fixture", wraps=fixture) as generate:
            result = run(config(), self.output, resume=True)
            self.assertEqual(generate.call_count, 1)
        self.assertEqual(result["passes"], 2)

    def test_resume_rejects_config_change(self):
        run(config(), self.output)
        with self.assertRaisesRegex(HarnessError, "configuration"):
            run(config(seed=99), self.output, resume=True)

    def test_tampered_attempt_is_detected(self):
        run(config(), self.output)
        path = next((self.output / "attempts").glob("*.json"))
        data = json.loads(path.read_text())
        data["record"]["evaluation"]["score"] = 0
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(HarnessError, "integrity"):
            run(config(), self.output, resume=True)

    def test_existing_run_is_not_overwritten(self):
        run(config(), self.output)
        with self.assertRaisesRegex(HarnessError, "already"):
            run(config(), self.output)

    def test_lock_prevents_concurrent_writer(self):
        self.output.mkdir()
        (self.output / ".run.lock").write_text("another runner")
        with self.assertRaisesRegex(HarnessError, "locked"):
            run(config(), self.output)
        self.assertTrue((self.output / ".run.lock").exists())

    def test_provider_failure_does_not_become_model_failure(self):
        with patch("iac_eval_bench.runner.fixture", side_effect=ProviderError("unavailable")):
            result = run(config(), self.output)
        self.assertEqual(result["provider_errors"], 2)
        self.assertEqual(result["operational_pass_rate"], 0)
        self.assertIsNone(result["quality_pass_rate"])
        self.assertEqual(result["failure_stages"], {})

    def test_html_escapes_model_output(self):
        generated = {
            "response": "<script>alert(1)</script>",
            "generation_seconds": None,
            "input_tokens": None,
            "output_tokens": None,
            "provider_metadata": {},
        }
        with patch("iac_eval_bench.runner.fixture", return_value=generated):
            run(config(), self.output)
        report = (self.output / "report.html").read_text()
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)

    def test_cli_rejects_unknown_tasks_and_half_configured_rates(self):
        for extra in [["--task", "unknown"], ["--input-rate", "2"]]:
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                result = main(
                    [
                        "run",
                        "--provider",
                        "fixture",
                        "--fixture-dir",
                        str(ROOT / "fixtures/reference"),
                        "--output",
                        str(self.output),
                        *extra,
                    ]
                )
                self.assertEqual(result, 2)

    def test_fixture_cli_smoke(self):
        code = main(
            [
                "run",
                "--provider",
                "fixture",
                "--fixture-dir",
                str(ROOT / "fixtures/reference"),
                "--task",
                "deployment-resources",
                "--output",
                str(self.output),
                "--fail-on-quality",
            ]
        )
        self.assertEqual(code, 0)
        self.assertTrue((self.output / "results.csv").exists())

    def test_empty_summary_is_not_a_perfect_run(self):
        result = summarize([])
        self.assertIsNone(result["quality_pass_rate"])
        self.assertIsNone(result["macro_score"])
