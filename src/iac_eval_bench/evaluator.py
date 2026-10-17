"""Pure static scoring: candidate content is parsed as data, never executed."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from importlib.resources import files
from itertools import islice
from typing import Any

from jsonschema.validators import validator_for

MAX_RESPONSE_BYTES = 1_048_576
MISSING = object()


class HarnessError(Exception):
    """A broken benchmark/configuration, not a model quality failure."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(text: str):
    def nonfinite(value):
        raise ValueError(f"non-finite JSON value: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON number exceeds finite floating-point range")
        return number

    return json.loads(
        text, object_pairs_hook=_pairs, parse_constant=nonfinite, parse_float=finite_float
    )


@lru_cache(maxsize=1)
def catalog():
    data = files("iac_eval_bench").joinpath("data")
    suite = json.loads(data.joinpath("tasks.json").read_text())
    ids = [task["id"] for task in suite["tasks"]]
    if len(ids) != len(set(ids)):
        raise HarnessError("duplicate task IDs")
    for task in suite["tasks"]:
        rule_ids = [rule["id"] for rule in task["rules"]]
        if not rule_ids or len(rule_ids) != len(set(rule_ids)):
            raise HarnessError("missing or duplicate rule IDs")
        if any(rule["op"] not in {"eq", "subset", "length", "absent"} for rule in task["rules"]):
            raise HarnessError("unsupported rule operator")
    return suite


@lru_cache(maxsize=1)
def schemas():
    directory = files("iac_eval_bench").joinpath("data/schemas")
    manifest = json.loads(directory.joinpath("manifest.json").read_text())
    validators = {}
    for key, entry in manifest["schemas"].items():
        raw = directory.joinpath(entry["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise HarnessError(f"schema checksum mismatch: {key}")
        schema = json.loads(raw)
        cls = validator_for(schema)
        cls.check_schema(schema)
        validators[key] = cls(schema)
    return manifest, validators


def task_prompt(task):
    return (
        "Return exactly one JSON object with the sole top-level key resources, whose value "
        "is an array of Kubernetes resource objects. No Markdown fences, comments, explanations, "
        "duplicate keys, or additional resources. Use Kubernetes 1.34 API schemas. "
        "This is a static configuration task; do not execute commands or contact a cluster.\n\n"
        + task["prompt"]
    )


def lookup(value, path):
    for segment in path:
        if isinstance(segment, dict):
            if not isinstance(value, list):
                return MISSING
            matching = [
                item
                for item in value
                if isinstance(item, dict)
                and all(item.get(k, MISSING) == v for k, v in segment.items())
            ]
            if len(matching) != 1:
                return MISSING
            value = matching[0]
        elif isinstance(value, dict) and segment in value:
            value = value[segment]
        else:
            return MISSING
    return value


def identity(resource):
    metadata = resource.get("metadata") or {}
    return (
        resource.get("apiVersion"),
        resource.get("kind"),
        metadata.get("name"),
        metadata.get("namespace"),
    )


def subset(actual, expected):
    """Allow unrequested object keys, preserving array cardinality and order."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and subset(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(subset(a, b) for a, b in zip(actual, expected))
        )
    return canonical(actual) == canonical(expected)


def _failed(stage, message):
    return {"stage": stage, "passed": False, "score": 0.0, "checks": [], "errors": [message]}


def evaluate(task: dict, raw: str) -> dict:
    """Score a response. Schema/inventory failures gate all rubric credit."""
    try:
        raw_size = len(raw.encode("utf-8")) if isinstance(raw, str) else MAX_RESPONSE_BYTES + 1
    except UnicodeError:
        return _failed("parse", "response is not valid UTF-8")
    if raw_size > MAX_RESPONSE_BYTES:
        return _failed("parse", "response must be UTF-8 text of at most 1 MiB")
    try:
        output = strict_json(raw)
    except (ValueError, RecursionError) as exc:
        return _failed("parse", str(exc)[:500])
    if (
        not isinstance(output, dict)
        or set(output) != {"resources"}
        or not isinstance(output["resources"], list)
        or not output["resources"]
        or len(output["resources"]) > 16
    ):
        return _failed("parse", "expected an object containing only 1–16 resources")
    _, validators = schemas()
    resources = output["resources"]
    errors = []
    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            errors.append(f"resource {index}: expected an object")
            continue
        key = f"{resource.get('apiVersion')}:{resource.get('kind')}"
        validator = validators.get(key)
        if validator is None:
            errors.append(f"resource {index}: unsupported apiVersion/kind {key}")
            continue
        for error in islice(validator.iter_errors(resource), 20):
            errors.append(
                f"resource {index} /{'/'.join(map(str, error.path))}: {error.message[:400]}"
            )
    if errors:
        result = _failed("schema", errors[0])
        result["errors"] = errors[:20]
        return result
    actual = [identity(resource) for resource in resources]
    expected = [(r["apiVersion"], r["kind"], r["name"], r["namespace"]) for r in task["resources"]]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        return _failed(
            "inventory",
            "resource identities must exactly match the requested set; "
            "duplicates, missing resources and extras receive no credit",
        )
    by_name = {r["kind"] + "/" + r["metadata"]["name"]: r for r in resources}
    checks = []
    for rule in task["rules"]:
        value = lookup(by_name[rule["resource"]], rule["path"])
        if rule["op"] == "absent":
            passed = value is MISSING
        elif rule["op"] == "subset":
            passed = value is not MISSING and subset(value, rule["value"])
        elif rule["op"] == "length":
            passed = isinstance(value, list) and len(value) == rule["value"]
        else:
            passed = value is not MISSING and canonical(value) == canonical(rule["value"])
        checks.append(
            {
                "id": rule["id"],
                "passed": passed,
                "expected": rule["value"],
                "actual": None if value is MISSING else value,
                "missing": value is MISSING,
            }
        )
    passed = all(check["passed"] for check in checks)
    return {
        "stage": "passed" if passed else "requirements",
        "passed": passed,
        "score": sum(c["passed"] for c in checks) / len(checks),
        "checks": checks,
        "errors": [],
    }
