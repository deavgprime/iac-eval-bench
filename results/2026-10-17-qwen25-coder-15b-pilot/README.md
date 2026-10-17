# Qwen2.5-Coder 1.5B: one-task CPU pilot

This is the first real-model execution in this project. One preselected task,
`cronjob-bounds`, was attempted once on 2026-10-17. The generation completed,
but the configuration failed the task. The original response is retained without
correction or a second attempt. Coverage is **one of six suite tasks**; this is
not a full-suite baseline, model ranking or statistical estimate.

| Measurement | Observed value |
| --- | --- |
| Model | Qwen2.5-Coder 1.5B, Q4_K_M |
| Model task passes | **0/1** |
| Failure stage | Resource inventory: incorrect CronJob name |
| Provider errors | 0 |
| Generation-request wall time | 48.96 seconds, including model loading |
| Provider-reported model loading | 9.33 seconds |
| Input / output tokens | 195 / 211 |
| Benchmark command wall time | 54.71 seconds |
| Download, installation, model setup and pilot | Approximately 190 seconds |
| Entire workload peak cgroup memory | 4.0003 GiB, including filesystem cache |
| Minimum host available RAM | 8.52 GiB; subsequently recovered |
| Minimum disk space available | 32.01 GiB |
| Maximum sampled host one-minute load | 3.89 |
| Watchdog interventions | None |
| Cost | Unknown; local VM/electricity costs were not measured |

## Failure analysis

The prompt requests a CronJob named `snapshot` in namespace `bench`. The response
uses `metadata.name: bench-snapshot`. It passes JSON parsing and the bundled
Kubernetes schema, but fails the exact resource-identity gate and therefore
receives a score of zero before individual rubric checks. Schema-valid output can
still violate the requested specification. This one failure does not establish
the model's general IaC capability.

The model stopped normally after 211 output tokens, below the 1,024-token cap.
No generated commands or Kubernetes resources were executed.

## Evidence

- [Original response, prompt, timings and evaluation](run/records.jsonl)
- [Run manifest and clean source revision](run/run.json)
- [Machine-readable summary](run/summary.json) and [CSV](run/results.csv)
- [HTML report](run/report.html), for downloading and opening locally
- [Model digests](model-tags.json), [base configuration](base-configuration.json)
  and [derived pilot configuration](pilot-configuration.json)
- [Environment and limits](environment.json), [resource samples](resources.csv)
  and [resource summary](resource-summary.json)
- [Completion timing](completion.json) and [empty model list after unloading](loaded-models-after.json)

Source revision at execution: `de5407f627b4de56b51cb3231c1653c2b346af22`, clean.
Harness 0.2.0; suite `kubernetes-config-v2` / 2.0.0. Runtime dependencies and content
hashes are recorded in the manifest. Ollama version was 0.40.6. The official
installation archive was verified against its GitHub release asset SHA-256.

Base model manifest digest:
`d7372fd828518a4d38b1eb196c673c31a85f2ed302b3d1e406c4c2d1b64a0668`.
Derived model manifest digest:
`8b6adbbef77f85ad49e28fe86719b9616290d618ae463a700d11639893179fe8`.
The recorded Qwen template/configuration retains its [Apache-2.0 license](QWEN-LICENSE.txt). Model weights are not redistributed here.

These identify model manifests, not the Ollama installation archive. The derived
model uses the base weights with the parameters in [Modelfile](Modelfile).

## Resource controls

The CPU-only VM had four logical CPUs and approximately 31.3 GiB total RAM.
Installation, download, serving and evaluation ran inside one transient user
systemd service with `MemoryMax=6G`, `MemoryHigh=4G`, `MemorySwapMax=0`,
`CPUQuota=150%`, `TasksMax=256`, `Nice=15`, and `RuntimeMaxSec=2400`.
CPU quota of 150% allows 1.5 logical CPU equivalents, not 150% of the VM.

A separate watchdog sampled every two seconds and would stop the workload below
8 GiB available RAM or free disk. Host one-minute load above 5 for 30 seconds would
reduce CPU quota to 75%; 120 seconds would stop the service. These thresholds were
not crossed. Host memory ballooning briefly reduced available RAM, then receded.
Workload memory includes page cache and must not be interpreted as model RSS.
The measurements cover setup as well as inference, and are specific to this VM.

Ollama listened only on `127.0.0.1:11435`, with cloud features disabled, one loaded
model and one generation at a time. The model was unloaded and the transient
service stopped after the attempt. Installation and weights remain on disk for
reuse; there is no running inference service or automatic startup.

## Reproduce the experiment

Install the harness and its locked dependencies using the repository instructions.
Use Ollama 0.40.6 and apply the resource limits above to its server and the runner.
Start a local server with the environment settings recorded in `environment.json`.
With that server already running:

```bash
export OLLAMA_HOST=127.0.0.1:11435
ollama pull qwen2.5-coder:1.5b
ollama create iac-qwen25-coder-15b-pilot -f results/2026-10-17-qwen25-coder-15b-pilot/Modelfile
curl --fail http://127.0.0.1:11435/api/tags
```

Verify both digests against `model-tags.json` before claiming reproduction. Tags
can change; if they do, record the actual digests as a new experiment. A command's
`--model-revision` flag only records the supplied value; it does not verify it.

```bash
iac-eval run --provider ollama \
  --model iac-qwen25-coder-15b-pilot:latest \
  --model-revision 8b6adbbef77f85ad49e28fe86719b9616290d618ae463a700d11639893179fe8 \
  --endpoint http://127.0.0.1:11435 --task cronjob-bounds \
  --repeat 1 --seed 42 --temperature 0 --timeout 600 \
  --output runs/qwen25-coder-15b-pilot
ollama stop iac-qwen25-coder-15b-pilot:latest
```

Stop the server service afterwards. Hardware, competing load and server changes
can affect latency and generated text even with a fixed seed. The summary's p50
and p95 both refer to the same single observation; they do not describe a latency
distribution. A larger experiment needs a declared task/trial and resource budget
before generation, including retention of failures.
