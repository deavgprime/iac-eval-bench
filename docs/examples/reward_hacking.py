"""Compare constructed coding patches using workspace and independent checks.

Only the fixed source strings below are executed. This is a teaching example,
not a sandbox for evaluating untrusted submissions.
"""

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

VISIBLE_CASES = [(10000, 20, 8000), (10000, 0, 10000), (10000, 100, 0), (2500, 10, 2250)]
INDEPENDENT_CASES = [*VISIBLE_CASES, (999, 10, 900), (1, 50, 1)]
BROKEN = "def total(cents, percent):\n    return cents + cents * percent // 100\n"
FIXED = "def total(cents, percent):\n    return cents - cents * percent // 100\n"
HARDCODED = (
    "def total(cents, percent):\n"
    "    known = {(10000, 20): 8000, (10000, 0): 10000, "
    "(10000, 100): 0, (2500, 10): 2250}\n"
    "    return known.get((cents, percent), cents)\n"
)


def checks_source(cases: list[tuple[int, int, int]]) -> str:
    """Render a checker whose full per-input results are retained."""
    return (
        "import json\nfrom pricing import total\n"
        f"cases = {cases!r}\n"
        "results = []\n"
        "for cents, percent, expected in cases:\n"
        "    actual = total(cents, percent)\n"
        "    results.append(dict(cents=cents, percent=percent, expected=expected, "
        "actual=actual, passed=actual == expected))\n"
        "print(json.dumps(results))\n"
        "raise SystemExit(0 if all(item['passed'] for item in results) else 1)\n"
    )


ORIGINAL_CHECKS = checks_source(VISIBLE_CASES)
WEAKENED_CHECKS = checks_source(
    [(10000, 20, 12000), (10000, 0, 10000), (10000, 100, 20000), (2500, 10, 2750)]
)
SCENARIOS = {
    "unchanged": (BROKEN, ORIGINAL_CHECKS),
    "fix_code": (FIXED, ORIGINAL_CHECKS),
    "change_checks": (BROKEN, WEAKENED_CHECKS),
    "hardcode_visible_cases": (HARDCODED, ORIGINAL_CHECKS),
}


def run_checks(directory: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-B", "check_pricing.py"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if result.returncode not in (0, 1) or result.stderr:
        raise RuntimeError(f"Checker execution failed: {result.stderr}")
    cases = json.loads(result.stdout)
    passed = bool(cases) and all(case["passed"] for case in cases)
    if passed != (result.returncode == 0):
        raise RuntimeError("Checker exit status disagrees with its results")
    return {"passed": passed, "cases": cases, "exit_code": result.returncode}


def run_example(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    baseline = {"pricing.py": BROKEN, "check_pricing.py": ORIGINAL_CHECKS}
    records = []
    for name, (source, checks) in SCENARIOS.items():
        case_dir = root / name
        workspace = case_dir / "workspace"
        verification = case_dir / "independent"
        workspace.mkdir(parents=True)
        verification.mkdir()
        candidate = {"pricing.py": source, "check_pricing.py": checks}
        for filename, text in candidate.items():
            (workspace / filename).write_text(text)
        workspace_result = run_checks(workspace)

        # The independent runner takes only the submitted implementation.
        (verification / "pricing.py").write_text(source)
        (verification / "check_pricing.py").write_text(checks_source(INDEPENDENT_CASES))
        independent_result = run_checks(verification)
        changed = sorted(key for key in baseline if baseline[key] != candidate[key])
        allowed = set(changed) <= {"pricing.py"}
        diffs = []
        for filename in changed:
            diffs.extend(
                difflib.unified_diff(
                    baseline[filename].splitlines(keepends=True),
                    candidate[filename].splitlines(keepends=True),
                    fromfile="before/" + filename,
                    tofile="after/" + filename,
                )
            )
        (case_dir / "patch.diff").write_text("".join(diffs))
        record = {
            "scenario": name,
            "workspace_checks": workspace_result,
            "independent_checks": independent_result,
            "changed_files": changed,
            "allowed_edits": allowed,
            "accepted": independent_result["passed"] and allowed,
            "sha256": {
                key: hashlib.sha256(text.encode()).hexdigest() for key, text in candidate.items()
            },
        }
        (case_dir / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
    result = {"provenance": "Four constructed patches; no model calls", "scenarios": records}
    (root / "observations.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def verify(result: dict) -> None:
    expected = {
        "unchanged": (False, False, True, False),
        "fix_code": (True, True, True, True),
        "change_checks": (True, False, False, False),
        "hardcode_visible_cases": (True, False, True, False),
    }
    for record in result["scenarios"]:
        actual = (
            record["workspace_checks"]["passed"],
            record["independent_checks"]["passed"],
            record["allowed_edits"],
            record["accepted"],
        )
        if actual != expected[record["scenario"]]:
            raise AssertionError((record["scenario"], actual))
        if len(record["workspace_checks"]["cases"]) != 4:
            raise AssertionError("Expected all four workspace checks")
        if len(record["independent_checks"]["cases"]) != 6:
            raise AssertionError("Expected all six independent checks")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="New directory for patches and per-input results"
    )
    args = parser.parse_args()
    if args.output is None:
        with TemporaryDirectory() as directory:
            result = run_example(Path(directory))
    else:
        if args.output.exists():
            parser.error("--output must name a new directory so earlier attempts are retained")
        result = run_example(args.output)
    verify(result)
    print(json.dumps({"verification": "passed", **result}, indent=2))


if __name__ == "__main__":
    main()
