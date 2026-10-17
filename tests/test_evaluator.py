import copy
import json
import unittest
from pathlib import Path

from iac_eval_bench.evaluator import MISSING, catalog, evaluate, lookup

ROOT = Path(__file__).resolve().parents[1]
TASKS = {t["id"]: t for t in catalog()["tasks"]}


def response(task_id="deployment-resources"):
    return json.loads((ROOT / "fixtures/reference" / (task_id + ".json")).read_text())


class EvaluatorTests(unittest.TestCase):
    def test_all_reference_fixtures_pass(self):
        for name, task in TASKS.items():
            with self.subTest(task=name):
                result = evaluate(task, json.dumps(response(name)))
                self.assertTrue(result["passed"], result)
                self.assertEqual(result["score"], 1)

    def test_each_mutation_fails_exact_intended_requirement(self):
        mutations = json.loads((ROOT / "fixtures/mutations.json").read_text())
        for name, check in mutations.items():
            with self.subTest(task=name):
                result = evaluate(
                    TASKS[name], (ROOT / "fixtures/mutated" / (name + ".json")).read_text()
                )
                self.assertEqual(result["stage"], "requirements", result)
                self.assertEqual([c["id"] for c in result["checks"] if not c["passed"]], [check])

    def test_json_contract_rejects_ambiguous_or_invalid_output(self):
        cases = [
            "{}",
            "[]",
            "null",
            "true",
            '{"resources":[]}',
            '{"resources":[],"resources":[]}',
            '{"resources":[NaN]}',
            "```json\n{}\n```",
            '{"resources":[]} {}',
            "x" * 1_048_577,
        ]
        for raw in cases:
            with self.subTest(raw=raw[:60]):
                self.assertEqual(evaluate(TASKS["deployment-resources"], raw)["stage"], "parse")

    def test_schema_failure_gates_credit(self):
        data = response()
        data["resources"][0]["spec"]["replicas"] = "three"
        result = evaluate(TASKS["deployment-resources"], json.dumps(data))
        self.assertEqual(result["stage"], "schema")
        self.assertEqual(result["score"], 0)
        self.assertTrue(result["errors"])

    def test_unknown_kubernetes_field_fails_strict_schema(self):
        data = response()
        data["resources"][0]["spec"]["replicaCount"] = 3
        self.assertEqual(
            evaluate(TASKS["deployment-resources"], json.dumps(data))["stage"], "schema"
        )

    def test_extra_duplicate_missing_and_wrong_namespace_fail_inventory(self):
        base = response("service-routing")
        variants = []
        extra = copy.deepcopy(base)
        extra["resources"].append(copy.deepcopy(extra["resources"][1]))
        variants.append(extra)
        missing = copy.deepcopy(base)
        missing["resources"].pop()
        variants.append(missing)
        wrong = copy.deepcopy(base)
        wrong["resources"][0]["metadata"]["namespace"] = "default"
        variants.append(wrong)
        for data in variants:
            with self.subTest(data=data):
                self.assertEqual(
                    evaluate(TASKS["service-routing"], json.dumps(data))["stage"], "inventory"
                )

    def test_resource_order_and_unrequired_annotation_are_not_scored(self):
        data = response("service-routing")
        data["resources"].reverse()
        data["resources"][0]["metadata"]["annotations"] = {"example.org/note": "valid variation"}
        self.assertTrue(evaluate(TASKS["service-routing"], json.dumps(data))["passed"])

    def test_unknown_kind_and_non_object_resource_fail_schema(self):
        for value in [17, {"apiVersion": "evil/v1", "kind": "Script"}]:
            result = evaluate(TASKS["deployment-resources"], json.dumps({"resources": [value]}))
            self.assertEqual(result["stage"], "schema")

    def test_missing_named_container_is_a_failed_requirement(self):
        data = response()
        data["resources"][0]["spec"]["template"]["spec"]["containers"][0]["name"] = "different"
        result = evaluate(TASKS["deployment-resources"], json.dumps(data))
        self.assertEqual(result["stage"], "requirements")
        self.assertFalse(result["passed"])

    def test_duplicate_named_container_is_not_silently_selected(self):
        values = [{"name": "app", "image": "one"}, {"name": "app", "image": "two"}]
        self.assertIs(lookup(values, [{"name": "app"}, "image"]), MISSING)

    def test_false_and_zero_are_not_interchangeable(self):
        data = response("workload-hardening")
        data["resources"][0]["spec"]["template"]["spec"]["automountServiceAccountToken"] = 0
        self.assertFalse(evaluate(TASKS["workload-hardening"], json.dumps(data))["passed"])

    def test_null_metadata_is_a_candidate_failure_not_a_harness_crash(self):
        data = response()
        data["resources"][0]["metadata"] = None
        result = evaluate(TASKS["deployment-resources"], json.dumps(data))
        self.assertFalse(result["passed"])

    def test_nonfinite_numbers_and_surrogates_are_parse_failures(self):
        for raw in ['{"resources":[1e999]}', "\ud800"]:
            self.assertEqual(evaluate(TASKS["deployment-resources"], raw)["stage"], "parse")

    def test_probe_options_and_explicit_tcp_are_valid_variations(self):
        data = response()
        container = data["resources"][0]["spec"]["template"]["spec"]["containers"][0]
        container["ports"][0]["protocol"] = "TCP"
        container["readinessProbe"]["timeoutSeconds"] = 2
        self.assertTrue(evaluate(TASKS["deployment-resources"], json.dumps(data))["passed"])
