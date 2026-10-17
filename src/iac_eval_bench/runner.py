"""Resumable runs with immutable configuration and atomic per-attempt evidence."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import random
import subprocess
import time
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from . import __version__
from .evaluator import HarnessError, catalog, digest, evaluate, schemas, task_prompt
from .providers import ProviderError, estimate_cost, fixture, ollama
from .report import write_reports


def source_hash():
    source = files("iac_eval_bench")
    return digest(
        {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in source.iterdir()
            if f.name.endswith(".py")
        }
    )


def git_state():
    location = Path(__file__).resolve().parents[2]
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(location), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "-C", str(location), "status", "--porcelain"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return {"revision": revision, "dirty": dirty}
    except (subprocess.SubprocessError, OSError):
        return {"revision": None, "dirty": None}


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


@contextlib.contextmanager
def run_lock(directory):
    lock = directory / ".run.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise HarnessError(
            "run directory is locked; after an unclean stop, confirm no runner "
            "is active before removing .run.lock"
        ) from exc
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def run(config, directory: Path, resume=False):
    suite = catalog()
    schema_manifest, _ = schemas()  # detect corrupt/missing schemas before generation
    tasks = {task["id"]: task for task in suite["tasks"]}
    if not config["tasks"] or any(key not in tasks for key in config["tasks"]):
        raise ValueError("select at least one known task")
    if len(config["tasks"]) != len(set(config["tasks"])):
        raise ValueError("duplicate task selection")
    fixture_hashes = {}
    if config["provider"] == "fixture":
        for task_id in config["tasks"]:
            path = Path(config["fixture_dir"]) / (task_id + ".json")
            fixture_hashes[task_id] = (
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            )
    fingerprint = digest(
        {
            "config": config,
            "suite": suite,
            "schemas": schema_manifest,
            "harness": source_hash(),
            "fixtures": fixture_hashes,
        }
    )
    directory.mkdir(parents=True, exist_ok=True)
    with run_lock(directory):
        manifest_path = directory / "run.json"
        if manifest_path.exists():
            if not resume:
                raise HarnessError(
                    "output already contains a run; choose a new directory or --resume"
                )
            manifest = json.loads(manifest_path.read_text())
            if manifest["fingerprint"] != fingerprint:
                raise HarnessError("resume rejected: configuration, inputs or evaluator changed")
        else:
            if resume:
                raise HarnessError("cannot resume: run.json is missing")
            if (directory / "attempts").exists():
                raise HarnessError("orphan attempt directory; choose a new output directory")
            manifest = {
                "format_version": 1,
                "suite": suite["suite"],
                "suite_version": suite["version"],
                "suite_sha256": digest(suite),
                "schemas_sha256": digest(schema_manifest),
                "harness_version": __version__,
                "harness_sha256": source_hash(),
                "fingerprint": fingerprint,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "git": git_state(),
                "config": config,
                "fixture_sha256": fixture_hashes,
                "sampling": "independent requests; no best-of selection or automatic retries",
            }
            atomic_json(manifest_path, manifest)
        attempts = directory / "attempts"
        attempts.mkdir(exist_ok=True)
        records = []
        rng = random.Random(config["seed"])
        planned = []
        for trial in range(1, config["repeat"] + 1):
            order = list(config["tasks"])
            rng.shuffle(order)
            planned.extend((task_id, trial) for task_id in order)
        allowed = {f"{task_id}.{trial}.json" for task_id, trial in planned}
        if any(path.name not in allowed for path in attempts.glob("*.json")):
            raise HarnessError("unexpected attempt files in output directory")
        for task_id, trial in planned:
            path = attempts / f"{task_id}.{trial}.json"
            if path.exists():
                stored = json.loads(path.read_text())
                row = stored["record"]
                if (
                    stored["sha256"] != digest(row)
                    or row["run_fingerprint"] != fingerprint
                    or row["task_id"] != task_id
                    or row["trial"] != trial
                ):
                    raise HarnessError("attempt integrity check failed")
                records.append(row)
                continue
            task = tasks[task_id]
            prompt = task_prompt(task)
            row = {
                "task_id": task_id,
                "task_version": task["version"],
                "trial": trial,
                "seed": config["seed"] + trial - 1,
                "run_fingerprint": fingerprint,
                "prompt": prompt,
                "prompt_sha256": digest(prompt),
            }
            try:
                if config["provider"] == "fixture":
                    generated = fixture(config["fixture_dir"], task_id)
                else:
                    generated = ollama(
                        config["endpoint"],
                        config["model"],
                        prompt,
                        row["seed"],
                        config["temperature"],
                        config["timeout"],
                    )
                start = time.perf_counter()
                evaluation = evaluate(task, generated["response"])
                row.update(generated)
                row.update(
                    status="completed",
                    evaluation=evaluation,
                    evaluation_seconds=time.perf_counter() - start,
                    estimated_cost_usd=estimate_cost(
                        generated["input_tokens"],
                        generated["output_tokens"],
                        config["input_rate"],
                        config["output_rate"],
                    ),
                )
            except ProviderError as exc:
                row.update(
                    status="provider_error",
                    error=str(exc),
                    evaluation=None,
                    generation_seconds=None,
                    input_tokens=None,
                    output_tokens=None,
                    estimated_cost_usd=None,
                )
            atomic_json(path, {"record": row, "sha256": digest(row)})
            records.append(row)
            print(
                f"{task_id} trial={trial}: {row['evaluation']['stage'] if row['evaluation'] else row['status']}",
                flush=True,
            )
        # Derived artifacts can always be regenerated by --resume without new requests.
        with (directory / "records.jsonl").open("w") as stream:
            for row in records:
                stream.write(json.dumps(row, allow_nan=False) + "\n")
        return write_reports(directory, manifest, records)
