"""Adversarial examples and accepted alternatives for the v2 scoring audit."""

import copy
import json
import unittest
from pathlib import Path

from iac_eval_bench.evaluator import catalog, evaluate, strict_json

ROOT = Path(__file__).resolve().parents[1]
TASKS = {t["id"]: t for t in catalog()["tasks"]}


def example(task_id):
    return json.loads((ROOT / "fixtures/reference" / f"{task_id}.json").read_text())


def container(data):
    return data["resources"][0]["spec"]["template"]["spec"]["containers"][0]


class ScoringAuditTests(unittest.TestCase):
    def check(self, task_id, data, expected):
        result = evaluate(TASKS[task_id], json.dumps(data))
        self.assertEqual(result["passed"], expected, result)
        return result

    def test_contradictory_deployment_selector_fails(self):
        for task_id in [
            "deployment-resources",
            "service-routing",
            "workload-hardening",
            "configmap-wiring",
        ]:
            with self.subTest(task=task_id):
                data = example(task_id)
                data["resources"][0]["spec"]["selector"]["matchExpressions"] = [
                    {"key": "app", "operator": "NotIn", "values": ["api"]}
                ]
                self.check(task_id, data, False)

    def test_harmless_labels_and_matching_selector_constraints_pass(self):
        for task_id in [
            "deployment-resources",
            "service-routing",
            "workload-hardening",
            "configmap-wiring",
        ]:
            with self.subTest(task=task_id):
                data = example(task_id)
                pod_labels = data["resources"][0]["spec"]["template"]["metadata"]["labels"]
                pod_labels.update(team="platform")
                data["resources"][0]["spec"]["selector"]["matchExpressions"] = [
                    {"key": "team", "operator": "In", "values": ["platform"]},
                    {"key": "missing", "operator": "NotIn", "values": ["excluded"]},
                    {"key": "app", "operator": "Exists"},
                    {"key": "missing", "operator": "DoesNotExist"},
                ]
                self.check(task_id, data, True)

    def test_invalid_or_nonmatching_expression_never_passes(self):
        for expression in [
            {"key": "app", "operator": "In", "values": ["other"]},
            {"key": "app", "operator": "DoesNotExist"},
            {"key": "missing", "operator": "Exists"},
            {"key": "app", "operator": "BadOperator"},
            {"key": "app", "operator": "In", "values": []},
            {"key": "app", "operator": "Exists", "values": ["api"]},
        ]:
            with self.subTest(expression=expression):
                data = example("deployment-resources")
                data["resources"][0]["spec"]["selector"]["matchExpressions"] = [expression]
                self.check("deployment-resources", data, False)

    def test_selector_still_requires_explicit_app_constraint(self):
        data = example("deployment-resources")
        data["resources"][0]["spec"]["selector"] = {"matchLabels": {}}
        self.check("deployment-resources", data, False)

    def test_service_selector_must_match_pods_with_extra_labels(self):
        for matches in [True, False]:
            with self.subTest(matches=matches):
                data = example("service-routing")
                data["resources"][0]["spec"]["template"]["metadata"]["labels"]["team"] = "platform"
                data["resources"][1]["spec"]["selector"]["team"] = (
                    "platform" if matches else "other"
                )
                self.check("service-routing", data, matches)

    def test_redundant_pdb_selector_passes_but_contradiction_fails(self):
        for operator, expected in [("Exists", True), ("DoesNotExist", False)]:
            with self.subTest(operator=operator):
                data = example("workload-hardening")
                data["resources"][1]["spec"]["selector"]["matchExpressions"] = [
                    {"key": "app", "operator": operator}
                ]
                self.check("workload-hardening", data, expected)

    def test_readiness_rejects_multiple_handlers(self):
        for handler, value in [
            ("tcpSocket", {"port": 8080}),
            ("exec", {"command": ["true"]}),
            ("grpc", {"port": 8080}),
        ]:
            with self.subTest(handler=handler):
                data = example("deployment-resources")
                container(data)["readinessProbe"][handler] = value
                self.check("deployment-resources", data, False)

    def test_readiness_rejects_invalid_timing_and_target_overrides(self):
        for key, value in [
            ("timeoutSeconds", 0),
            ("periodSeconds", -1),
            ("successThreshold", 0),
            ("failureThreshold", 0),
            ("terminationGracePeriodSeconds", 30),
        ]:
            with self.subTest(key=key):
                data = example("deployment-resources")
                container(data)["readinessProbe"][key] = value
                self.check("deployment-resources", data, False)
        for key, value in [("host", "another-host"), ("scheme", "FTP"), ("scheme", "HTTPS")]:
            with self.subTest(key=key, value=value):
                data = example("deployment-resources")
                container(data)["readinessProbe"]["httpGet"][key] = value
                self.check("deployment-resources", data, False)

    def test_explicit_default_http_probe_options_pass(self):
        data = example("deployment-resources")
        probe = container(data)["readinessProbe"]
        probe.update(timeoutSeconds=2, periodSeconds=10, successThreshold=1, failureThreshold=3)
        probe["httpGet"].update(scheme="HTTP", host="")
        self.check("deployment-resources", data, True)

    def test_transport_defaults_and_protocol_mismatches(self):
        for task_id in ["deployment-resources", "service-routing"]:
            for protocol, expected in [("TCP", True), ("UDP", False), ("SCTP", False)]:
                with self.subTest(task=task_id, protocol=protocol):
                    data = example(task_id)
                    container(data)["ports"][0]["protocol"] = protocol
                    self.check(task_id, data, expected)
        data = example("service-routing")
        del data["resources"][1]["spec"]["ports"][0]["protocol"]
        self.check("service-routing", data, True)

    def test_network_order_is_irrelevant_but_duplicates_and_or_peers_fail(self):
        data = example("network-isolation")
        policy = data["resources"][0]["spec"]
        policy["policyTypes"].reverse()
        policy["egress"][0]["ports"].reverse()
        self.check("network-isolation", data, True)
        duplicate = copy.deepcopy(data)
        duplicate["resources"][0]["spec"]["egress"][0]["ports"][1] = copy.deepcopy(
            duplicate["resources"][0]["spec"]["egress"][0]["ports"][0]
        )
        self.check("network-isolation", duplicate, False)
        peer = policy["ingress"][0]["from"][0]
        policy["ingress"][0]["from"] = [
            {"namespaceSelector": peer["namespaceSelector"]},
            {"podSelector": peer["podSelector"]},
        ]
        self.check("network-isolation", data, False)

    def test_extra_pod_security_fields_do_not_override_required_values(self):
        data = example("workload-hardening")
        security = data["resources"][0]["spec"]["template"]["spec"]["securityContext"]
        security["fsGroup"] = 2000
        self.check("workload-hardening", data, True)
        security["runAsUser"] = 0
        self.check("workload-hardening", data, False)

    def test_every_rubric_requirement_has_a_detected_missing_or_forbidden_field(self):
        total = 0
        for task in TASKS.values():
            for rule in task["rules"]:
                with self.subTest(task=task["id"], rule=rule["id"]):
                    data = example(task["id"])
                    resources = {
                        r["kind"] + "/" + r["metadata"]["name"]: r for r in data["resources"]
                    }
                    parent = resources[rule["resource"]]
                    for segment in rule["path"][:-1]:
                        if isinstance(segment, dict):
                            parent = next(
                                v for v in parent if all(v.get(k) == x for k, x in segment.items())
                            )
                        else:
                            parent = parent[segment]
                    leaf = rule["path"][-1]
                    if rule["op"] == "absent":
                        parent[leaf] = 1 if leaf == "maxUnavailable" else []
                    else:
                        del parent[leaf]
                    self.check(task["id"], data, False)
                    total += 1
        self.assertEqual(total, 50)

    def test_json_nesting_and_escaped_surrogate_limits(self):
        for raw in ["[" * 65 + "0" + "]" * 65, '{"bad":"\\ud800"}']:
            with self.subTest(raw=raw[:20]):
                self.assertEqual(evaluate(TASKS["deployment-resources"], raw)["stage"], "parse")
        with self.assertRaises(ValueError):
            strict_json("[" * 65 + "0" + "]" * 65)
