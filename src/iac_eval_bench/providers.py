"""Generation adapters. No provider credentials or network calls are needed for fixtures."""

from __future__ import annotations

import http.client
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .evaluator import MAX_RESPONSE_BYTES, strict_json


class ProviderError(Exception):
    """Transport/protocol failure; excluded from conditional quality metrics."""


def fixture(directory: str, task_id: str) -> dict:
    path = Path(directory) / f"{task_id}.json"
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderError("fixture exceeds response byte limit")
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProviderError(f"cannot read fixture for {task_id}: {type(exc).__name__}") from exc
    return {
        "response": text,
        "generation_seconds": None,
        "input_tokens": None,
        "output_tokens": None,
        "provider_metadata": {"kind": "constructed_fixture"},
    }


def validate_endpoint(endpoint):
    parts = urlsplit(endpoint)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("endpoint must be an HTTP(S) base URL without credentials/query/fragment")


def ollama(
    endpoint: str, model: str, prompt: str, seed: int, temperature: float, timeout: float
) -> dict:
    validate_endpoint(endpoint)
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"seed": seed, "temperature": temperature},
    }
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2 * MAX_RESPONSE_BYTES + 1)
        if len(raw) > 2 * MAX_RESPONSE_BYTES:
            raise ProviderError("provider envelope exceeds 2 MiB")
        result = strict_json(raw.decode())
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        UnicodeError,
        RecursionError,
        http.client.HTTPException,
    ) as exc:
        # Do not retain server error bodies, which may contain deployment details/secrets.
        raise ProviderError(f"Ollama request failed: {type(exc).__name__}") from exc
    elapsed = time.perf_counter() - start
    if not isinstance(result, dict) or result.get("done") is not True:
        raise ProviderError("provider returned an incomplete or invalid envelope")
    if not isinstance(result.get("response"), str):
        raise ProviderError("provider response text is missing")
    counts = {}
    for source, target in [("prompt_eval_count", "input_tokens"), ("eval_count", "output_tokens")]:
        value = result.get(source)
        if value is not None and (type(value) is not int or value < 0):
            raise ProviderError("invalid provider token usage")
        counts[target] = value
    return {
        "response": result["response"],
        "generation_seconds": elapsed,
        **counts,
        "provider_metadata": {
            k: result.get(k) for k in ["model", "done_reason", "total_duration", "load_duration"]
        },
    }


def estimate_cost(input_tokens, output_tokens, input_rate, output_rate):
    """Explicit per-million USD rates only; missing information remains unknown."""
    values = [input_tokens, output_tokens, input_rate, output_rate]
    if any(value is None for value in values):
        return None
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("usage and rates must be finite and non-negative")
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
