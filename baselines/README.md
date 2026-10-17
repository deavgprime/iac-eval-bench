# Constructed fixture baselines

These are evaluator regression results, **not model evaluations**. No model endpoint
was used. Both sets contain six authored fixtures, each evaluated once.

| Fixture set | Task passes | Schema/inventory validation | Meaning |
| --- | --- | --- | --- |
| [Reference](reference/summary.json) | 6/6 | 6/6 | Every specified requirement passes |
| [Mutated](mutated/summary.json) | 0/6 | 6/6 | Each of six targeted semantic mistakes is detected |

Source revision: `363b5c49d5a60e30dc155f9c7dbfcd62acc72e99` (clean tree when measured).
The reports include the exact suite/schema/evaluator hashes, raw responses, prompts,
per-rule outcomes and runtime metadata. Generation latency, tokens and cost are
unknown because no generation service was called. Evaluation timings reflect only
this host and are not model latency measurements.

To reproduce from the repository root after installation:

```bash
python scripts/verify_baselines.py --output runs/reproduction
```

Expected semantic results are stable; run timestamps and evaluation timings vary.
Use a fresh output directory. Individual runs support `iac-eval run ... --resume`.

Download/open [the reference HTML report](reference/report.html) or
[the negative-control HTML report](mutated/report.html) locally. GitHub displays HTML
source rather than executing it; `summary.json`, `records.jsonl` and `results.csv`
remain readable directly in the repository.
