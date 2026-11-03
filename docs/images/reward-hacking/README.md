# Reward hacking example

These illustrations accompany a standalone example of a coding task whose
workspace checks can pass without the requested behavior being correct.

Run the four constructed patches with Python 3.11 or later:

```bash
python3 docs/examples/reward_hacking.py --output reward-demo
```

The output retains each patch, submitted files, hashes, and results from four
workspace checks and six independent checks. Use a new output directory for
each run. The saved example is in
[`reward-hacking-observations.json`](../../examples/reward-hacking-observations.json).

Only the fixed source strings in the example are executed. The example is not
a security sandbox for untrusted submissions and does not run a model.

The three images use original editorial illustrations generated with the
built-in image generation tool. The prompts and file hashes are retained in
`prompts.json` and `provenance.json`. They illustrate the constructed example;
they are not measured model results.
