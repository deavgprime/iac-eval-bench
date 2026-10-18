# Qwen2.5-Coder: six-task CPU comparison

On 2026-10-18, Qwen2.5-Coder 1.5B and 0.5B (both Q4_K_M) each attempted all six
Kubernetes tasks once. All 12 requests completed normally. Neither model passed
a full task. The 1.5B model earned partial rubric credit on two tasks; the 0.5B
model omitted the required response wrapper in every attempt. Equal pass counts
do not imply equal capability.

This is a small, fixed-order comparison within one model family, with one attempt
per task and no retries. It does not establish a general model ranking or a
statistical estimate. The earlier one-task pilot remains published separately and
is excluded here. No generated resources or commands were executed.

## Model totals

| Model | Task passes | Macro score | Input tokens | Output tokens | Mean request seconds |
| --- | --- | --- | --- | --- | --- |
| qwen-1.5b | 0/6 | 17.13% | 1536 | 1661 | 43.57 |
| qwen-0.5b | 0/6 | 0.00% | 1536 | 1472 | 19.47 |

Latency includes cold model loading and is observational. A dependency installation
capped at 0.5 CPU and 2 GiB briefly overlapped the 0.5B network-isolation and
service-routing attempts, then was frozen until benchmarking finished. See
[background activity](background-activity.json) for timing. Do not use these
latencies as an isolated speed ranking. Input/output token counts come from
Ollama; monetary and electricity costs were not measured and remain unknown.

## Every attempt

All attempts failed; the score is partial rubric credit, not a pass probability.
Memory includes the entire workload cgroup and its page cache, not just model RSS.
CPU seconds and memory are sampled within each CLI attempt window at two-second
intervals, including runner overhead. CPU deltas omit interval edges and can
undercount. Exact request and model-loading timings are recorded separately.

| Model | Task | Score | Failure stage | Request seconds | Load seconds | Tokens in/out | Sampled peak GiB | Sampled CPU seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen-1.5b | [configmap-wiring](qwen-1.5b/configmap-wiring/records.jsonl) | 0.00% | schema | 44.08 | 7.66 | 241/252 | 2.51 | 58.53 |
| qwen-1.5b | [cronjob-bounds](qwen-1.5b/cronjob-bounds/records.jsonl) | 0.00% | inventory | 33.03 | 3.11 | 195/211 | 2.51 | 49.36 |
| qwen-1.5b | [deployment-resources](qwen-1.5b/deployment-resources/records.jsonl) | 77.78% | requirements | 46.22 | 3.33 | 309/288 | 2.52 | 67.90 |
| qwen-1.5b | [network-isolation](qwen-1.5b/network-isolation/records.jsonl) | 25.00% | requirements | 41.92 | 3.10 | 265/269 | 2.52 | 61.98 |
| qwen-1.5b | [service-routing](qwen-1.5b/service-routing/records.jsonl) | 0.00% | inventory | 44.36 | 3.08 | 244/293 | 2.51 | 65.10 |
| qwen-1.5b | [workload-hardening](qwen-1.5b/workload-hardening/records.jsonl) | 0.00% | schema | 51.82 | 3.10 | 282/348 | 2.52 | 74.04 |
| qwen-0.5b | [configmap-wiring](qwen-0.5b/configmap-wiring/records.jsonl) | 0.00% | parse | 16.67 | 1.58 | 241/205 | 1.89 | 25.55 |
| qwen-0.5b | [cronjob-bounds](qwen-0.5b/cronjob-bounds/records.jsonl) | 0.00% | parse | 15.44 | 1.58 | 195/197 | 1.89 | 23.18 |
| qwen-0.5b | [deployment-resources](qwen-0.5b/deployment-resources/records.jsonl) | 0.00% | parse | 22.48 | 1.57 | 309/286 | 1.89 | 32.53 |
| qwen-0.5b | [network-isolation](qwen-0.5b/network-isolation/records.jsonl) | 0.00% | parse | 28.47 | 1.58 | 265/379 | 1.89 | 41.42 |
| qwen-0.5b | [service-routing](qwen-0.5b/service-routing/records.jsonl) | 0.00% | parse | 15.27 | 1.83 | 244/176 | 1.89 | 22.87 |
| qwen-0.5b | [workload-hardening](qwen-0.5b/workload-hardening/records.jsonl) | 0.00% | parse | 18.48 | 1.58 | 282/229 | 1.89 | 26.48 |

## Failure review

Each original response was re-evaluated and matched its saved result. Review
against the exact prompts found concrete output errors in every attempt, with no
blocking prompt ambiguity or false rejection identified in these 12 responses.
This is not a general certification of the evaluator. The `parse` stage on 0.5B
means a missing response envelope; all six responses are syntactically valid JSON.

### qwen-1.5b

- **deployment-resources:** The port lacks the required http name. The response supplies a liveness probe instead of the requested readiness probe and uses a numeric probe port.
- **service-routing:** Both resource names differ from api. The container is api-container instead of app, and the Service port has no http name.
- **network-isolation:** podSelector is absent. Ingress mixes pod labels into namespaceSelector; egress does not constrain both the kube-system namespace and kube-dns pods.
- **cronjob-bounds:** The CronJob is named bench-snapshot instead of snapshot.
- **workload-hardening:** Pod and container security settings are reversed. The container and PDB have incorrect names, and maxUnavailable appears despite an explicit prohibition.
- **configmap-wiring:** The Deployment container has no name; the prompt explicitly requires app.

### qwen-0.5b

- **deployment-resources:** Valid JSON, but missing the explicitly required resources array wrapper. Also omits the named port and HTTP readiness probe; its liveness probe has no handler.
- **service-routing:** Valid JSON, but missing the explicitly required resources array wrapper. Also omits the Service, changes the Deployment/container names and omits the named port.
- **network-isolation:** Valid JSON, but missing the explicitly required resources array wrapper. Also invents spec.rules and embeds Ingress/Egress-like objects instead of the requested NetworkPolicy peer rules.
- **cronjob-bounds:** Valid JSON, but missing the explicitly required resources array wrapper. Also uses the wrong resource/container names and places containers at JobSpec level; the job template, retry and deadline fields are missing.
- **workload-hardening:** Valid JSON, but missing the explicitly required resources array wrapper. Also omits the PDB and pod-level security settings, changes names and omits automountServiceAccountToken=false.
- **configmap-wiring:** Valid JSON, but missing the explicitly required resources array wrapper. Also omits the ConfigMap, uses api-deployment and names the container nginx.

Offline diagnostic edits repaired the explicit defects in each 1.5B response;
all six repaired copies passed. Adding only the wrapper to each 0.5B response
still left all six failing. These are reviewer edits, not model attempts, and
are excluded from all model scores. [Failure-review evidence](failure-review.json)
records the edits and outcomes; [review.py](review.py) reproduces those checks
using the installed harness, without inference or network access.

The bundled schema allows omission of some API-required fields, including `NetworkPolicy.spec.podSelector`; the task rubric detects that
omission here. Schema acceptance is not API-server admission validation. Exact
resource names and the `resources` wrapper are intentional gates. A future suite
could state names uniformly as `metadata.name`, but the observed names contradict
the current prompts. Prompts and scoring were unchanged between models.

## Protocol and VM limits

Source revision: `3da83dbb58855804b49b0f2c7b1d995c587ddbdd`, clean at execution.
Harness 0.2.0; suite `kubernetes-config-v2` 2.0.0; Ollama 0.40.6.
Four logical x86_64 CPUs, approximately 31.3 GiB RAM, no GPU and no swap.
The [protocol](protocol.json) was written before inference. The 1.5B model ran
first, then 0.5B, in the recorded task order. Both used JSON output mode,
seed 42, temperature 0, context 4096, output cap 1024, two model threads,
600-second request timeout and `keep_alive=0`. All responses ended with `stop`,
not output-cap truncation. Each task has a manifest with dependency versions,
prompt and evaluator hashes, and model digest.

Both models ran in the same transient systemd service: `MemoryMax=6G`,
`MemoryHigh=4G`, `MemorySwapMax=0`, `CPUQuota=150%`, `TasksMax=256`, `Nice=15`,
and `RuntimeMaxSec=2400`. CPU quota means 1.5 logical CPU equivalents. Ollama
listened on loopback with cloud features disabled, one loaded model and one
request at a time. There was no external model endpoint.

A two-second watchdog would stop below 8 GiB available RAM or free disk. Host
one-minute load above 5 for 30 seconds would reduce CPU quota to 75%; 120 seconds
would stop the workload. No intervention was required. Across setup and inference:

- Elapsed time: 412.69 seconds.
- Peak cgroup memory: 2.52 GiB, including filesystem cache.
- Minimum host available RAM: 29.22 GiB.
- Minimum free disk: 30.67 GiB.
- Maximum sampled one-minute host load: 2.02.
- Both models unloaded and the server stopped after completion.

## Evidence and reproduction

[Comparison JSON](comparison.json) and [CSV](comparison.csv) contain all per-task
measurements. Original responses, atomic attempt records, manifests and generated
reports are retained byte-for-byte in the model/task directories. Resource
[samples](resources.csv), [summary](resource-summary.json), [attempt windows](attempt-windows.json),
[events](events.jsonl), [completion](completion.json) and [empty loaded-model list](loaded-models-after.json)
record execution and shutdown. The [model tags](model-tags.json) identify both
base and derived model digests. Model configurations retain their original
Apache-2.0 licenses and templates; only the generated `modelfile` field containing
a local blob path was omitted. Portable Modelfiles are included instead. Weights
are not redistributed.

Install the harness and locked dependencies at the source revision above. Start
Ollama 0.40.6 under the same service limits and watchdog thresholds. Set
`OLLAMA_HOST=127.0.0.1:11435`, `OLLAMA_NUM_PARALLEL=1`,
`OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_MAX_QUEUE=1`, `OLLAMA_CONTEXT_LENGTH=4096`,
`OLLAMA_NO_CLOUD=1`, `OLLAMA_KEEP_ALIVE=0` and `CUDA_VISIBLE_DEVICES=-1`.
Pull each base model and create the derived aliases using their Modelfiles:

```bash
ollama pull qwen2.5-coder:1.5b
ollama pull qwen2.5-coder:0.5b
ollama create iac-qwen25-coder-15b-pilot -f results/2026-10-18-qwen-comparison/qwen-1.5b/Modelfile
ollama create iac-qwen25-coder-05b-comparison -f results/2026-10-18-qwen-comparison/qwen-0.5b/Modelfile
```

Check `/api/tags` against the saved digests. Tags can change; if digests differ,
record a new experiment. For each model and task in protocol order, run:

```bash
iac-eval run --provider ollama --model ALIAS --model-revision VERIFIED_DIGEST \
  --endpoint http://127.0.0.1:11435 --task TASK --repeat 1 --seed 42 \
  --temperature 0 --timeout 600 --output runs/NEW_EXPERIMENT/MODEL/TASK
ollama stop ALIAS
```

Use fresh output directories and retain every attempt. Stop the server afterwards.
`--model-revision` records a supplied value; it does not verify the model. Hardware,
background activity and server changes can affect both text and latency. File
checksums in [SHA256SUMS](SHA256SUMS) support evidence integrity checks.
