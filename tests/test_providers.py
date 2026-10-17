import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from iac_eval_bench.providers import ProviderError, estimate_cost, ollama, validate_endpoint


class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                cls.request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(cls.status)
                self.end_headers()
                self.wfile.write(json.dumps(cls.payload).encode())

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        type(self).status = 200
        type(self).payload = {
            "done": True,
            "response": '{"resources":[]}',
            "prompt_eval_count": 100,
            "eval_count": 50,
            "model": "mock-model",
        }

    def generate(self):
        return ollama(self.url, "mock-model", "synthetic prompt", 7, 0.2, 2)

    def test_real_http_adapter_records_usage_and_request_configuration(self):
        result = self.generate()
        self.assertEqual(result["input_tokens"], 100)
        self.assertEqual(result["output_tokens"], 50)
        self.assertGreaterEqual(result["generation_seconds"], 0)
        self.assertEqual(self.request["options"], {"seed": 7, "temperature": 0.2})
        self.assertIs(self.request["stream"], False)
        self.assertEqual(self.request["prompt"], "synthetic prompt")

    def test_missing_usage_stays_unknown(self):
        type(self).payload = {"done": True, "response": "{}"}
        self.assertIsNone(self.generate()["input_tokens"])

    def test_provider_errors_are_not_json_quality_failures(self):
        for payload in [
            {"done": False, "response": "{}"},
            {"done": True},
            {"done": True, "response": "{}", "eval_count": -1},
            {"done": True, "response": "{}", "eval_count": True},
        ]:
            with self.subTest(payload=payload):
                type(self).payload = payload
                with self.assertRaises(ProviderError):
                    self.generate()

    def test_http_error_is_classified_without_retaining_server_body(self):
        type(self).status = 503
        type(self).payload = {"error": "private deployment details"}
        with self.assertRaises(ProviderError) as result:
            self.generate()
        self.assertNotIn("private deployment", str(result.exception))

    def test_cost_requires_explicit_rates_and_complete_usage(self):
        self.assertEqual(estimate_cost(1_000_000, 500_000, 2, 4), 4)
        self.assertIsNone(estimate_cost(10, 20, None, None))
        self.assertIsNone(estimate_cost(None, 20, 2, 4))
        self.assertEqual(estimate_cost(10, 20, 0, 0), 0)
        with self.assertRaises(ValueError):
            estimate_cost(10, 20, float("nan"), 4)

    def test_endpoint_rejects_credentials_and_non_http_schemes(self):
        for url in ["file:///tmp/api", "http://user:pass@localhost", "http://localhost?key=secret"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_endpoint(url)

    def test_truncated_http_response_is_a_provider_failure(self):
        import http.client
        from unittest.mock import patch

        with patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"partial")):
            with self.assertRaises(ProviderError):
                self.generate()

    def test_excessively_nested_provider_envelope_is_a_provider_failure(self):
        value = 0
        for _ in range(70):
            value = [value]
        type(self).payload = {"done": True, "response": "{}", "unexpected": value}
        with self.assertRaises(ProviderError):
            self.generate()
