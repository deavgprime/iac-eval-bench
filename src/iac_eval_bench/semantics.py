"""Narrow Kubernetes semantics used by the task rubric, not full admission validation."""


def selector_matches(selector, labels, required, *, plain=False):
    if not isinstance(selector, dict) or not isinstance(labels, dict):
        return False
    match_labels = selector if plain else selector.get("matchLabels", {})
    if not isinstance(match_labels, dict):
        return False
    # The task contract explicitly requires these matchLabels, not just one matching pod.
    if any(match_labels.get(key) != value for key, value in required.items()):
        return False
    if any(key not in labels or labels[key] != value for key, value in match_labels.items()):
        return False
    if plain:
        return True
    expressions = selector.get("matchExpressions") or []
    if not isinstance(expressions, list):
        return False
    for expr in expressions:
        if not isinstance(expr, dict):
            return False
        key, op, values = expr.get("key"), expr.get("operator"), expr.get("values") or []
        if not isinstance(key, str) or not key or not isinstance(values, list):
            return False
        if op in {"In", "NotIn"}:
            if not values or any(not isinstance(v, str) for v in values):
                return False
            inside = key in labels and labels[key] in values
            if (op == "In" and not inside) or (op == "NotIn" and inside):
                return False
        elif op in {"Exists", "DoesNotExist"}:
            if (
                values
                or (op == "Exists" and key not in labels)
                or (op == "DoesNotExist" and key in labels)
            ):
                return False
        else:
            return False
    return True


def http_probe_valid(probe):
    if not isinstance(probe, dict) or not isinstance(probe.get("httpGet"), dict):
        return False
    if any(probe.get(kind) is not None for kind in ["exec", "tcpSocket", "grpc"]):
        return False
    http = probe["httpGet"]
    if http.get("scheme", "HTTP") != "HTTP" or http.get("host", "") != "":
        return False
    for key in ["timeoutSeconds", "periodSeconds", "successThreshold", "failureThreshold"]:
        if key in probe and (type(probe[key]) is not int or probe[key] < 1):
            return False
    # Per-probe termination grace is supported on liveness/startup, not readiness.
    return probe.get("terminationGracePeriodSeconds") is None


def normalize_ports(ports):
    if not isinstance(ports, list):
        return ports
    return [{"protocol": "TCP", **port} if isinstance(port, dict) else port for port in ports]


def unordered(value):
    """Normalize only order-insensitive NetworkPolicy subtrees, retaining multiplicity."""
    import json

    if isinstance(value, dict):
        return {key: unordered(item) for key, item in value.items()}
    if isinstance(value, list):
        return sorted(
            (unordered(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True)
        )
    return value
