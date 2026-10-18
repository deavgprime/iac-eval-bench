import copy
import json
from pathlib import Path

from iac_eval_bench.evaluator import catalog, evaluate

ROOT = Path(__file__).resolve().parent
TASKS = {t["id"]: t for t in catalog()["tasks"]}
NOTES = {
    "configmap-wiring": (
        "The Deployment container has no name; the prompt explicitly requires app.",
        "Add the missing container name app.",
    ),
    "cronjob-bounds": (
        "The CronJob is named bench-snapshot instead of snapshot.",
        "Change the CronJob name to snapshot.",
    ),
    "deployment-resources": (
        "The port lacks the required http name. The response supplies a liveness probe instead of the requested readiness probe and uses a numeric probe port.",
        "Name the container port http; move the probe to readinessProbe and use port http.",
    ),
    "network-isolation": (
        "podSelector is absent. Ingress mixes pod labels into namespaceSelector; egress does not constrain both the kube-system namespace and kube-dns pods.",
        "Set the selected pod labels and the specified namespace/pod selector pairs.",
    ),
    "service-routing": (
        "Both resource names differ from api. The container is api-container instead of app, and the Service port has no http name.",
        "Correct resource and container names and name the Service port http.",
    ),
    "workload-hardening": (
        "Pod and container security settings are reversed. The container and PDB have incorrect names, and maxUnavailable appears despite an explicit prohibition.",
        "Put security settings at the requested levels, correct names and remove maxUnavailable.",
    ),
}
SMALL = {
    "configmap-wiring": "Also omits the ConfigMap, uses api-deployment and names the container nginx.",
    "cronjob-bounds": "Also uses the wrong resource/container names and places containers at JobSpec level; the job template, retry and deadline fields are missing.",
    "deployment-resources": "Also omits the named port and HTTP readiness probe; its liveness probe has no handler.",
    "network-isolation": "Also invents spec.rules and embeds Ingress/Egress-like objects instead of the requested NetworkPolicy peer rules.",
    "service-routing": "Also omits the Service, changes the Deployment/container names and omits the named port.",
    "workload-hardening": "Also omits the PDB and pod-level security settings, changes names and omits automountServiceAccountToken=false.",
}
reviews = []
for model in ["qwen-1.5b", "qwen-0.5b"]:
    for task in TASKS:
        path = ROOT / model / task / "records.jsonl"
        record = json.loads(path.read_text())
        original = evaluate(TASKS[task], record["response"])
        assert original == record["evaluation"]
        output = json.loads(record["response"])
        repaired = copy.deepcopy(output)
        if model == "qwen-1.5b":
            resources = repaired["resources"]
            first = resources[0]
            if task == "configmap-wiring":
                first["spec"]["template"]["spec"]["containers"][0]["name"] = "app"
            elif task == "cronjob-bounds":
                first["metadata"]["name"] = "snapshot"
            elif task == "deployment-resources":
                c = first["spec"]["template"]["spec"]["containers"][0]
                c["ports"][0]["name"] = "http"
                c["readinessProbe"] = c.pop("livenessProbe")
                c["readinessProbe"]["httpGet"]["port"] = "http"
            elif task == "network-isolation":
                s = first["spec"]
                s["podSelector"] = {"matchLabels": {"app": "api"}}
                s["ingress"][0]["from"] = [
                    {
                        "namespaceSelector": {"matchLabels": {"team": "frontend"}},
                        "podSelector": {"matchLabels": {"role": "web"}},
                    }
                ]
                s["egress"][0]["to"] = [
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                        },
                        "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                    }
                ]
            elif task == "service-routing":
                for r in resources:
                    r["metadata"]["name"] = "api"
                first["spec"]["template"]["spec"]["containers"][0]["name"] = "app"
                resources[1]["spec"]["ports"][0]["name"] = "http"
            elif task == "workload-hardening":
                pod = first["spec"]["template"]["spec"]
                c = pod["containers"][0]
                c["name"] = "app"
                pod["securityContext"], c["securityContext"] = (
                    c["securityContext"],
                    pod["securityContext"],
                )
                resources[1]["metadata"]["name"] = "api"
                resources[1]["spec"].pop("maxUnavailable")
            diagnosis, edit = NOTES[task]
        else:
            repaired = {
                "resources": list(output.values()) if task == "network-isolation" else [output]
            }
            diagnosis = (
                "Valid JSON, but missing the explicitly required resources array wrapper. "
                + SMALL[task]
            )
            edit = (
                "Add only the required resources array wrapper; leave resource contents unchanged."
            )
        result = evaluate(TASKS[task], json.dumps(repaired))
        if model == "qwen-1.5b":
            assert result["passed"], (task, result)
        else:
            assert not result["passed"], task
        reviews.append(
            {
                "model": model,
                "task": task,
                "classification": "model_output_error",
                "diagnosis": diagnosis,
                "original_evaluation_reproduced": True,
                "blocking_prompt_ambiguity_identified": False,
                "scorer_false_rejection_identified": False,
                "diagnostic_edit": edit,
                "diagnostic_result": result,
                "diagnostic_only": True,
            }
        )
(ROOT / "failure-review.json").write_text(
    json.dumps(
        {
            "scope": "Review of all 12 original attempts against prompts and evaluator behavior. Diagnostic edits are offline probes, not model attempts, and do not change published scores.",
            "conclusion": "All observed failures have concrete output defects. No blocking prompt ambiguity or evaluator false rejection was identified in these attempts. This is not a general certification of the evaluator.",
            "limitations": [
                "The schema files omit some API-required fields, including NetworkPolicy.spec.podSelector; the rubric detects this omission here. Schema acceptance is not API-server admission validation.",
                "The exact-name and response-wrapper gates deliberately give zero rubric credit; zero pass counts do not imply equal capability.",
                "Task names could be phrased uniformly as metadata.name in a future version, but the observed naming deviations contradict the current requested identifiers.",
            ],
            "reviews": reviews,
        },
        indent=2,
    )
    + "\n"
)
print(
    "Reproduced all 12 scores. Six targeted 1.5B diagnostic repairs pass; six 0.5B wrapper-only diagnostics still fail."
)
