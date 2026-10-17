from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from .evaluator import HarnessError, catalog, evaluate, task_prompt
from .providers import validate_endpoint
from .runner import run


def finite_nonnegative(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("must be finite and non-negative")
    return result


def positive_count(value):
    result = int(value)
    if not 1 <= result <= 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate generated Kubernetes configuration offline."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    tasks_cmd = commands.add_parser("tasks", help="list versioned prompts")
    tasks_cmd.add_argument("--json", action="store_true")
    score_cmd = commands.add_parser("score", help="score one external response; no model call")
    score_cmd.add_argument("--task", required=True)
    score_cmd.add_argument("--response", required=True, type=Path)
    run_cmd = commands.add_parser("run", help="generate/replay, score and produce reports")
    run_cmd.add_argument("--provider", choices=["fixture", "ollama"], required=True)
    run_cmd.add_argument("--fixture-dir")
    run_cmd.add_argument("--model")
    run_cmd.add_argument(
        "--model-revision", help="user-supplied model digest/revision for provenance"
    )
    run_cmd.add_argument("--endpoint", default="http://localhost:11434")
    run_cmd.add_argument("--repeat", type=positive_count, default=1)
    run_cmd.add_argument("--seed", type=int, default=42)
    run_cmd.add_argument("--temperature", type=finite_nonnegative, default=0.0)
    run_cmd.add_argument("--timeout", type=finite_nonnegative, default=120.0)
    run_cmd.add_argument(
        "--input-rate", type=finite_nonnegative, help="explicit USD per million input tokens"
    )
    run_cmd.add_argument(
        "--output-rate", type=finite_nonnegative, help="explicit USD per million output tokens"
    )
    run_cmd.add_argument("--task", action="append", dest="tasks")
    run_cmd.add_argument("--output", required=True, type=Path)
    run_cmd.add_argument("--resume", action="store_true")
    run_cmd.add_argument("--fail-on-quality", action="store_true")
    args = parser.parse_args(argv)
    try:
        tasks = catalog()["tasks"]
        if args.command == "tasks":
            if args.json:
                print(
                    json.dumps(
                        [
                            {"id": t["id"], "version": t["version"], "prompt": task_prompt(t)}
                            for t in tasks
                        ],
                        indent=2,
                    )
                )
            else:
                for task in tasks:
                    print(f"{task['id']}: {task['title']}")
            return 0
        if args.command == "score":
            task = next((t for t in tasks if t["id"] == args.task), None)
            if task is None:
                raise ValueError("unknown task")
            # Bound reads before parsing arbitrarily large external files.
            with args.response.open("rb") as stream:
                raw = stream.read(1_048_577).decode("utf-8")
            result = evaluate(task, raw)
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        if args.provider == "fixture" and not args.fixture_dir:
            raise ValueError("--fixture-dir is required for fixture runs")
        if args.provider == "ollama" and not args.model:
            raise ValueError("--model is required for Ollama runs")
        if args.provider == "ollama" and args.fixture_dir:
            raise ValueError("--fixture-dir is only applicable to fixture runs")
        if args.provider == "fixture" and (args.model or args.model_revision):
            raise ValueError("fixture runs cannot be labeled with a model")
        if (args.input_rate is None) != (args.output_rate is None):
            raise ValueError("supply both input and output rates, or neither")
        if not 0 < args.timeout <= 3600:
            raise ValueError("--timeout must be greater than 0 and at most 3600 seconds")
        validate_endpoint(args.endpoint)
        config = {
            key: getattr(args, key)
            for key in [
                "provider",
                "fixture_dir",
                "model",
                "model_revision",
                "endpoint",
                "repeat",
                "seed",
                "temperature",
                "timeout",
                "input_rate",
                "output_rate",
            ]
        }
        config["tasks"] = sorted(args.tasks or [t["id"] for t in tasks])
        if args.provider == "fixture":
            config.update(endpoint=None, temperature=None)
        summary = run(config, args.output, args.resume)
        print(json.dumps(summary, indent=2))
        if summary["provider_errors"]:
            return 2
        return 1 if args.fail_on_quality and summary["passes"] != summary["attempts"] else 0
    except (HarnessError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
