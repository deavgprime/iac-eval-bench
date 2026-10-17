"""Aggregate outcomes without presenting fixture timings or missing costs as measurements."""

from __future__ import annotations

import csv
import html
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def percentile(values, fraction):
    """Nearest-rank percentile; intentionally simple and documented for small samples."""
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize(records):
    completed = [r for r in records if r["status"] == "completed"]
    passed = sum(r["evaluation"]["passed"] for r in completed)
    latencies = [r["generation_seconds"] for r in completed if r["generation_seconds"] is not None]
    costs = [r["estimated_cost_usd"] for r in completed if r["estimated_cost_usd"] is not None]
    by_task = {}
    for task in sorted({r["task_id"] for r in records}):
        rows = [r for r in records if r["task_id"] == task]
        successful = [r for r in rows if r["status"] == "completed"]
        by_task[task] = {
            "attempts": len(rows),
            "completed": len(successful),
            "passes": sum(r["evaluation"]["passed"] for r in successful),
            "mean_score": statistics.mean(r["evaluation"]["score"] for r in successful)
            if successful
            else None,
        }
    return {
        "attempts": len(records),
        "completed": len(completed),
        "provider_errors": len(records) - len(completed),
        "passes": passed,
        "operational_pass_rate": passed / len(records) if records else None,
        "quality_pass_rate": passed / len(completed) if completed else None,
        "macro_score": statistics.mean(
            t["mean_score"] for t in by_task.values() if t["mean_score"] is not None
        )
        if completed
        else None,
        "failure_stages": dict(
            Counter(r["evaluation"]["stage"] for r in completed if not r["evaluation"]["passed"])
        ),
        "generation_latency_seconds": {
            "samples": len(latencies),
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
        },
        "estimated_cost_usd": sum(costs) if len(costs) == len(completed) and completed else None,
        "cost_covered_completions": len(costs),
        "input_tokens_known": sum(
            r["input_tokens"] for r in completed if r["input_tokens"] is not None
        ),
        "output_tokens_known": sum(
            r["output_tokens"] for r in completed if r["output_tokens"] is not None
        ),
        "usage_covered_completions": sum(
            r["input_tokens"] is not None and r["output_tokens"] is not None for r in completed
        ),
        "by_task": by_task,
    }


def write_reports(directory: Path, manifest, records):
    summary = summarize(records)
    payload = {"run": manifest, "summary": summary}
    (directory / "summary.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    with (directory / "results.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "task",
                "trial",
                "status",
                "passed",
                "score",
                "stage",
                "generation_seconds",
                "input_tokens",
                "output_tokens",
                "estimated_cost_usd",
            ]
        )
        for row in records:
            evaluation = row.get("evaluation") or {}
            writer.writerow(
                [
                    row["task_id"],
                    row["trial"],
                    row["status"],
                    evaluation.get("passed"),
                    evaluation.get("score"),
                    evaluation.get("stage", "provider_error"),
                    row.get("generation_seconds"),
                    row.get("input_tokens"),
                    row.get("output_tokens"),
                    row.get("estimated_cost_usd"),
                ]
            )
    e = html.escape
    fixture = manifest["config"]["provider"] == "fixture"
    notice = (
        "Constructed fixture baseline — verifies the evaluator, not model capability. "
        "Repeated fixtures are identical examples, not independent model samples."
        if fixture
        else "Model run — a small public synthetic suite, not a general capability ranking."
    )
    parts = [
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>IaC evaluation report</title><style>body{font:16px/1.6 system-ui;"
        "max-width:1100px;margin:40px auto;padding:0 20px;color:#172033}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd5df;"
        "padding:10px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        ".note{background:#edf4fa;padding:16px}details{margin:12px 0}</style>"
        '<h1>IaC evaluation report</h1><p class="note">' + notice + "</p>",
        "<p>Suite: "
        + e(manifest["suite"])
        + " · Provider: "
        + e(manifest["config"]["provider"])
        + " · Model: "
        + e(manifest["config"].get("model") or "not applicable")
        + "</p>",
        "<p>Completed: "
        + str(summary["completed"])
        + "/"
        + str(summary["attempts"])
        + " · Passes: "
        + str(summary["passes"])
        + " · Provider errors: "
        + str(summary["provider_errors"])
        + "</p>",
        "<table><tr><th>Task</th><th>Trial</th><th>Outcome</th><th>Score</th><th>Failed checks</th></tr>",
    ]
    for row in records:
        ev = row.get("evaluation") or {}
        failed = ", ".join(c["id"] for c in ev.get("checks", []) if not c["passed"])
        parts.append(
            "<tr><td>"
            + e(row["task_id"])
            + "</td><td>"
            + str(row["trial"])
            + "</td><td>"
            + e(ev.get("stage", "provider_error"))
            + "</td><td>"
            + (f"{ev['score']:.3f}" if ev else "—")
            + "</td><td>"
            + e(failed)
            + "</td></tr>"
        )
    parts.append(
        "</table><h2>Metrics and coverage</h2><pre>"
        + e(json.dumps({k: v for k, v in summary.items() if k != "by_task"}, indent=2))
        + "</pre>"
    )
    parts.append(
        "<p>Quality pass rate excludes provider errors; operational pass rate includes them. "
        "Macro score averages task means over completed responses. Missing usage/cost/latency "
        "is unknown, not free or zero. Percentiles use nearest rank; small samples are noisy. "
        "Schema and rubric checks do not establish deployability, full API admission validation "
        "or complete security. Resources are never deployed.</p><h2>Per-attempt evidence</h2>"
    )
    for row in records:
        parts.append(
            "<details><summary>"
            + e(row["task_id"])
            + " / trial "
            + str(row["trial"])
            + "</summary><pre>"
            + e(json.dumps(row, indent=2, ensure_ascii=True))
            + "</pre></details>"
        )
    parts.append(
        "<h2>Run provenance</h2><pre>" + e(json.dumps(manifest, indent=2)) + "</pre></html>"
    )
    (directory / "report.html").write_text("".join(parts))
    return summary
