"""Verify positive and targeted negative controls, retaining inspectable reports."""

import argparse
import json
from pathlib import Path

from iac_eval_bench.cli import main

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
mutations = json.loads((root / "fixtures/mutations.json").read_text())
for kind in ["reference", "mutated"]:
    destination = args.output / kind
    code = main(
        [
            "run",
            "--provider",
            "fixture",
            "--fixture-dir",
            f"fixtures/{kind}",
            "--output",
            str(destination),
        ]
    )
    if code:
        raise SystemExit(code)
    rows = [json.loads(line) for line in (destination / "records.jsonl").read_text().splitlines()]
    assert len(rows) == len(mutations), "not all tasks executed"
    for row in rows:
        result = row["evaluation"]
        if kind == "reference":
            assert result["passed"] and result["score"] == 1, row["task_id"]
        else:
            assert result["stage"] == "requirements", row["task_id"]
            failed = [c["id"] for c in result["checks"] if not c["passed"]]
            assert failed == [mutations[row["task_id"]]], (row["task_id"], failed)
print("Verified: 6 reference passes; all 6 targeted semantic mutations detected.")
