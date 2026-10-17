# Constructed fixture baselines

These are evaluator regression results, **not model evaluations**. No model endpoint
was used. Each set contains six authored fixtures, each evaluated once.

## Current: suite v2 / harness 0.2.0

| Fixture set | Task passes | Schema/inventory validation | Meaning |
| --- | --- | --- | --- |
| [Reference](v2/reference/summary.json) | 6/6 | 6/6 | Every specified requirement passes |
| [Mutated](v2/mutated/summary.json) | 0/6 | 6/6 | Each of six targeted semantic mistakes is detected |

Source revision: `2e7b62045b026b68ac4e52b8f3b1a1103609ea3d` (clean tree when measured).
The reports retain exact suite/schema/evaluator hashes, validation runtime versions,
raw responses, prompts, per-check outcomes and task coverage. Generation latency,
tokens and cost are unknown because no generation service was called. Evaluation
timings are not model latency measurements.

Download/open [the v2 reference report](v2/reference/report.html) or
[the v2 negative-control report](v2/mutated/report.html) locally. GitHub displays HTML
source; `summary.json`, `records.jsonl` and `results.csv` are readable in the repository.

To reproduce from the repository root after installation:

```bash
python scripts/verify_baselines.py --output runs/reproduction-v2
```

Use a fresh output directory. Timestamps and evaluation timings vary. Individual
runs support resume only under matching configuration, input, code and runtime.

## Historical: suite v1 / harness 0.1.0

The original [reference](reference/summary.json) and [mutated](mutated/summary.json)
results remain unchanged. Their source revision is
`363b5c49d5a60e30dc155f9c7dbfcd62acc72e99`.
Reproduce those results using that historical checkout and its dependencies.

The original controls did not expose the five scoring errors found by the
[adversarial audit](../docs/scoring-audit.md). V2 corrects those cases and changes
several acceptance rules. Similar reference/negative pass totals do not establish
compatibility: do not merge results across suite versions or resume v1 runs with v2.
