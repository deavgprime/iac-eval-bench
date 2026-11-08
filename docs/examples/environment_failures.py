"""Run fixed evaluation examples under Linux address-space and wall-time limits.

Only the bundled programs are executed. This is not a sandbox for untrusted code
or a model benchmark. Results are written to a new directory without overwriting
earlier attempts. No network, model, or third-party packages are required.
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

PROGRAMS = {
    "bulk": """import csv
def total(path):
    with open(path, newline="") as source:
        rows = list(csv.DictReader(source))
    return sum(int(row["amount_cents"]) for row in rows)
""",
    "stream": """import csv
def total(path):
    with open(path, newline="") as source:
        return sum(int(row["amount_cents"]) for row in csv.DictReader(source))
""",
    "drop_first": """import csv
def total(path):
    with open(path, newline="") as source:
        rows = csv.DictReader(source)
        next(rows, None)
        return sum(int(row["amount_cents"]) for row in rows)
""",
}

WORKER = """import importlib.util
import json
import resource
import sys
import time
from pathlib import Path

limit, candidate, dataset, delay, metadata = sys.argv[1:]
limit = int(limit) * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
status = 0
try:
    # A fixed wait represents an unavailable dependency, not actual network I/O.
    time.sleep(float(delay))
    spec = importlib.util.spec_from_file_location("candidate", candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(json.dumps({"total_cents": module.total(dataset)}))
except MemoryError:
    print("MemoryError", file=sys.stderr)
    status = 20
except Exception as error:
    print(type(error).__name__ + ": " + str(error), file=sys.stderr)
    status = 21
finally:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    Path(metadata).write_text(json.dumps({
        "max_rss_kib": usage.ru_maxrss,
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
    }))
sys.exit(status)
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def assess(returncode, stdout, stderr, expected, timed_out):
    if timed_out:
        return "wall_timeout", None
    if returncode == 20 and stderr.strip() == "MemoryError":
        return "address_space_exhausted", None
    if returncode != 0:
        return "execution_error", None
    try:
        value = json.loads(stdout)["total_cents"]
    except (ValueError, KeyError, TypeError):
        return "invalid_output", None
    if type(value) is not int:
        return "invalid_output", value
    return ("pass" if value == expected else "wrong_answer"), value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("This example requires Linux RLIMIT_AS and Linux RSS units.")
    if not 1 <= args.repeats <= 10:
        parser.error("Choose between 1 and 10 repeats.")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    candidates = root / "candidates"
    candidates.mkdir()
    for name, source in PROGRAMS.items():
        (candidates / f"{name}.py").write_text(source)
    worker = root / "worker.py"
    worker.write_text(WORKER)
    dataset = root / "costs.csv"
    row_count = 300_000
    with dataset.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["row_id", "amount_cents"])
        for index in range(row_count):
            writer.writerow([index, index % 1000 + 1])
    # 300 complete cycles of the integers 1 through 1000.
    expected = 300 * (1000 * 1001 // 2)
    cases = [
        ("bulk_64", "bulk", 64, 10.0, 0.0, True),
        ("bulk_256", "bulk", 256, 10.0, 0.0, True),
        ("stream_64", "stream", 64, 10.0, 0.0, True),
        ("stream_256", "stream", 256, 10.0, 0.0, True),
        ("drop_first_64", "drop_first", 64, 10.0, 0.0, True),
        ("drop_first_256", "drop_first", 256, 10.0, 0.0, True),
        ("wait_short", "stream", 64, 0.25, 1.0, True),
        ("wait_long", "stream", 64, 4.0, 1.0, True),
        ("missing_input", "stream", 64, 10.0, 0.0, False),
    ]
    manifest = {
        "provenance": "Constructed programs and generated CSV; no model calls.",
        "platform": platform.platform(),
        "python": sys.version,
        "machine": platform.machine(),
        "script_sha256": digest(Path(__file__)),
        "worker_sha256": digest(worker),
        "dataset_sha256": digest(dataset),
        "dataset_bytes": dataset.stat().st_size,
        "rows": row_count,
        "expected_cents": expected,
        "limits": "RLIMIT_AS per child, not RSS or a cgroup RAM limit; CPU 8 seconds.",
        "timeout": "Wall time includes Python startup and the simulated dependency wait.",
        "execution": "Fresh isolated Python subprocess per attempt; serial execution.",
        "repeats": args.repeats,
    }
    save(root / "manifest.json", manifest)
    records = []
    for repeat in range(1, args.repeats + 1):
        # Alternate ordering to avoid always testing the larger budget second.
        ordered = cases if repeat % 2 else list(reversed(cases))
        for name, candidate, memory, timeout, delay, staged in ordered:
            attempt = root / f"{repeat:02d}-{name}"
            attempt.mkdir()
            program = candidates / f"{candidate}.py"
            input_path = dataset if staged else root / "not-staged.csv"
            record = {
                "id": attempt.name,
                "case": name,
                "repeat": repeat,
                "candidate": candidate,
                "candidate_sha256": digest(program),
                "dataset_sha256": digest(dataset) if staged else None,
                "address_space_mib": memory,
                "wall_timeout_seconds": timeout,
                "simulated_dependency_wait_seconds": delay,
                "expected_cents": expected,
                "started": False,
            }
            # Setup errors are retained but never presented as candidate output.
            if not input_path.is_file():
                record.update(outcome="setup_error", reason="Required input was not staged.")
            else:
                if digest(input_path) != manifest["dataset_sha256"]:
                    raise RuntimeError("The input changed during the experiment.")
                command = [
                    sys.executable,
                    "-I",
                    str(worker),
                    str(memory),
                    str(program),
                    str(input_path),
                    str(delay),
                    str(attempt / "usage.json"),
                ]
                started = time.monotonic()
                child = subprocess.Popen(
                    command,
                    cwd=attempt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                timed_out = False
                try:
                    stdout, stderr = child.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    stdout, stderr = child.communicate()
                elapsed = time.monotonic() - started
                outcome, actual = assess(child.returncode, stdout, stderr, expected, timed_out)
                (attempt / "stdout.txt").write_text(stdout)
                (attempt / "stderr.txt").write_text(stderr)
                usage = attempt / "usage.json"
                record.update(
                    started=True,
                    outcome=outcome,
                    actual_cents=actual,
                    returncode=child.returncode,
                    wall_seconds=elapsed,
                    timed_out=timed_out,
                    usage=json.loads(usage.read_text()) if usage.exists() else None,
                )
            save(attempt / "record.json", record)
            records.append(record)
            print(f"{attempt.name}: {record['outcome']}", flush=True)
    if digest(dataset) != manifest["dataset_sha256"]:
        raise RuntimeError("The input changed during the experiment.")
    for name, source in PROGRAMS.items():
        if (candidates / f"{name}.py").read_text() != source:
            raise RuntimeError("A candidate changed during the experiment.")
    save(root / "observations.json", {"manifest": manifest, "attempts": records})
    print(f"Saved {len(records)} attempt records to {root}")


if __name__ == "__main__":
    main()
