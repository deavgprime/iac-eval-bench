"""Check the externally visible failure boundaries used in the retry case study."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "docs/examples/safe_retries.py"
SPEC = importlib.util.spec_from_file_location("safe_retries", EXAMPLE)
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)


class SafeRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_case(self, case, strategy="durable_key"):
        return example.run_case(self.root / case, strategy, case)

    def test_crash_before_commit_rolls_back_then_creates(self):
        result = self.run_case("server_crash_before_commit")
        self.assertEqual(result["order_count"], 1)
        self.assertEqual(result["attempts"][-1]["replayed"], "false")

    def test_crash_after_commit_replays_the_original_order(self):
        result = self.run_case("server_crash_after_commit")
        self.assertEqual(result["order_count"], 1)
        self.assertEqual(result["attempts"][-1]["replayed"], "true")

    def test_new_keys_do_not_prevent_duplicates(self):
        result = self.run_case("disconnect_after_commit", "new_key_per_attempt")
        self.assertEqual(result["order_count"], 2)
        self.assertNotEqual(*[attempt["key"] for attempt in result["attempts"]])

    def test_a_real_read_timeout_can_follow_a_committed_order(self):
        result = self.run_case("timeout_after_commit")
        self.assertEqual(result["order_count"], 1)
        self.assertEqual(result["attempts"][0]["status"], None)
        self.assertEqual(result["attempts"][-1]["replayed"], "true")

    def test_client_process_restart_reuses_the_durable_intent(self):
        result = self.run_case("runner_restart")
        self.assertEqual(len({attempt["key"] for attempt in result["attempts"]}), 1)
        self.assertEqual(result["order_count"], 1)
        self.assertLess(
            json.loads((self.root / "runner_restart/client-exit.json").read_text())["returncode"], 0
        )

    def test_eight_concurrent_deliveries_create_one_order(self):
        result = self.run_case("concurrent_delivery")
        self.assertEqual(result["http_attempts"], 8)
        self.assertEqual(result["order_count"], 1)

    def test_reused_key_with_changed_parameters_is_rejected(self):
        result = self.run_case("changed_payload")
        self.assertEqual([a["status"] for a in result["attempts"]], [201, 409])
        self.assertEqual(result["order_count"], 1)

    def test_identical_payloads_can_be_two_distinct_actions(self):
        result = self.run_case("distinct_actions")
        self.assertEqual(result["order_count"], 2)
        self.assertEqual(len({a["key"] for a in result["attempts"]}), 2)

    def test_identical_key_is_scoped_to_distinct_tenants(self):
        # The local harness supplies tenant identity; deployment must authenticate it.
        result = self.run_case("tenant_isolation")
        self.assertEqual({row["tenant"] for row in result["orders"]}, {"tenant-a", "tenant-b"})
        self.assertEqual(len({a["key"] for a in result["attempts"]}), 1)

    def test_exhaustion_does_not_turn_unknown_into_failed(self):
        result = self.run_case("retry_budget_exhausted")
        self.assertEqual(result["client_outcome"], "unknown")
        self.assertEqual(result["order_count"], 1)
        self.assertEqual(result["http_attempts"], 3)

    def test_split_transaction_control_exposes_the_crash_window(self):
        result = self.run_case("split_transaction_crash")
        self.assertEqual(result["order_count"], 2)
        self.assertEqual(len(result["receipts"]), 1)

    def test_deleting_replay_state_allows_a_late_duplicate(self):
        result = self.run_case("expired_receipt")
        self.assertEqual(result["order_count"], 2)
        self.assertEqual(result["attempts"][-1]["replayed"], "false")

    def test_invalid_quantity_does_not_consume_the_key(self):
        service = example.Service(self.root)
        service.start()
        self.addCleanup(service.stop)
        for quantity in (0, -1, 101, True, "1", None):
            with self.subTest(quantity=quantity):
                response = example.request(
                    service.port, {"sku": "keyboard", "quantity": quantity}, "fixed-key"
                )
                self.assertEqual(response["status"], 400)
        result = example.request(service.port, example.BODY, "fixed-key")
        self.assertEqual(result["status"], 201)
        self.assertEqual(result["replayed"], "false")

    def test_parameter_order_does_not_change_the_request_identity(self):
        service = example.Service(self.root)
        service.start()
        self.addCleanup(service.stop)
        first = example.request(service.port, {"sku": "keyboard", "quantity": 1}, "fixed-key")
        second = example.request(service.port, {"quantity": 1, "sku": "keyboard"}, "fixed-key")
        self.assertEqual(first["response"], second["response"])
        self.assertEqual(second["replayed"], "true")

    def test_receipt_failure_does_not_leave_an_order(self):
        path = self.root / "rollback.sqlite"
        example.initialize(path)
        connection = example.database(path)
        self.addCleanup(connection.close)
        connection.executescript(
            "CREATE TRIGGER reject_receipt BEFORE INSERT ON receipts "
            "BEGIN SELECT RAISE(ABORT, 'injected receipt failure'); END;"
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected receipt failure"):
            example.apply_order(
                connection, "tenant-a", "fixed-key", example.BODY, lambda *a, **k: None
            )
        self.assertEqual(connection.execute("SELECT count(*) FROM orders").fetchone()[0], 0)
        connection.execute("DROP TRIGGER reject_receipt")
        status, unused, replayed = example.apply_order(
            connection, "tenant-a", "fixed-key", example.BODY, lambda *a, **k: None
        )
        self.assertEqual(status, 201)
        self.assertFalse(replayed)


if __name__ == "__main__":
    unittest.main()
