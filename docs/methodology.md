# Evaluation protocol, version 2

## Scope

The `kubernetes-config-v2` suite contains six original public synthetic tasks,
50 deterministic requirement checks, six constructed reference responses and six
constructed negative responses. It evaluates a restricted configuration-generation
interface: one JSON object containing a `resources` array. JSON is accepted by
Kubernetes, but this suite does not evaluate YAML formatting or arbitrary IaC
languages. Terraform, cloud provisioning and agent tool use are outside this release.

Task inputs, rubrics and fixture provenance live in `data/tasks.json` and `fixtures/`.
The explicit Kubernetes target is 1.34.0, not the latest Kubernetes release.
The schemas are pinned to an immutable upstream revision and bundled for offline use.

## Scoring contract

1. Parse strict JSON. Reject duplicate keys, non-finite numbers, prose/fences,
   invalid Unicode, nesting beyond 64 levels and responses over 1 MiB.
2. Validate each object using its allowlisted API version/kind and bundled strict
   JSON schema. Unknown object fields or unsupported kinds fail this stage.
3. Require the exact API/kind/name/namespace inventory, with no extra or duplicate
   objects. Schema/inventory failure gates all requirement credit.
4. Evaluate the task's named rubric checks. `eq` means typed JSON equality;
   `subset` permits extra object keys while preserving list length/order;
   `length` checks list size; `absent` requires omission rather than null.
   Named container lookup rejects missing or duplicate matches. `selector` and
   `map_selector` require the specified labels and check all constraints against
   the target Deployment's pod labels. `ports` applies the omitted TCP default;
   `http_probe` checks the requested HTTP handler and selected validity constraints.
   `unordered` ignores list order in the NetworkPolicy rule subtrees while retaining
   element multiplicity; it does not merge or simplify policy expressions.
5. Score each completed response as passed checks / all task checks. A task passes
   only if every check passes. The aggregate macro score averages per-task means
   across completed attempts, giving every observed task equal weight.

Parse, schema and inventory failures get score zero. Provider/transport errors
have no quality score. They lower operational pass rate and are shown separately.
Always inspect coverage: a run with provider failures is not comparable to a
complete run merely because its conditional quality rate is high. Tasks with no
completed responses have no task score and are omitted from the macro mean.
`task_coverage` makes this omission explicit. `operational_macro_score` instead
computes each task's score over all its attempts, assigning zero to provider errors,
then averages task means. This prevents absent tasks from inflating the operational score.

The evaluator deliberately does not normalize resource quantity strings, all
possible network-policy equivalents or every Kubernetes default. Prompts specify
constrained representations. This trades breadth for inspectable grading; valid
alternative solutions outside that contract may fail. Additional fields not
covered by a rule can pass schema validation without being semantically safe.
This is not a general security scanner or a deployment readiness gate.

## Sampling and reproducibility

The runner shuffles task order with a fixed PRNG seed. Trial `n` sends seed
`base_seed + n - 1` for each task. It records seed, temperature, exact prompt,
returned raw text and model metadata. There is no best-of selection, repair loop
or automatic retry. Failed provider attempts are preserved when resuming; start
a separately named experiment to retry. Resume requires matching configuration,
input, schema and evaluator hashes plus Python and validation-dependency versions.
The stored manifest's configuration/provenance fields must match the current run;
a changed display field cannot silently misattribute a resumed report. Each attempt is written atomically and
checksummed; the directory lock prevents competing writers. Checksums detect
accidental changes; they are not cryptographic signatures or tamper-proof provenance.

A model's seed is a request, not a guarantee of deterministic generation across
hardware, server versions or model builds. For real comparisons record the weight
digest, Ollama version, CPU/GPU, memory, concurrency, warm/cold state and quantization.
Supply the same tasks, prompts, model settings and explicit pricing assumptions
for each comparison. This version runs requests sequentially. It is not a serving
throughput benchmark.

## Metrics

Generation latency uses the client monotonic clock around the complete HTTP request.
It includes network and loading time. It excludes schema/rubric evaluation, whose
duration is stored separately. p50/p95 use nearest rank. Six observations cannot
support stable tail-latency conclusions. Repeated fixture replay produces no
model latency, tokens or token-based cost.

Token counts come from `prompt_eval_count` / `eval_count` in the provider envelope.
Missing counts stay missing. Dollar estimates require both counts and explicitly
provided per-million input/output rates. These estimates do not measure local
compute costs or billing. Totals cover completed responses; provider failures
can still incur external costs not known to this runner. Coverage accompanies
all usage/cost aggregation.

## Version compatibility

Version 0.2.0 uses suite 2.0.0 (`kubernetes-config-v2`). Five task contracts are now
version 2; the unchanged CronJob task remains version 1 within the new suite.
The original baseline remains under `baselines/reference` and `baselines/mutated`;
current evidence is under `baselines/v2`. Do not merge scores across suite versions
or resume a v1 run with v2. See [the audit](scoring-audit.md) for examples and scope.

## Baselines and limitations

The reference and mutated fixture runs are evaluator regression baselines.
Their expected outcomes were defined by the author; they are not independent
model measurements. Each mutation targets one named requirement while remaining
schema-valid. Tests also cover schema/parse failures, alternative accepted
representations, transport failures, interruption/resume and result integrity.

There is no model leaderboard, hidden test set, confidence interval or pass@k
claim. Six tasks are too narrow for general IaC competence. Public prompts and
solutions can appear in model training or retrieval; expand with independently
reviewed held-out tasks before drawing broad capability conclusions. No resource
is applied to a cluster. Schema validation does not reproduce all Kubernetes API
admission checks, CNI policy enforcement, runtime image behavior or application
health. The workload-hardening task checks declared fields and is not a full Pod
Security Standards implementation.

## Source references

- [Kubernetes NetworkPolicy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Kubernetes CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Ollama generation API](https://docs.ollama.com/api/generate)
- [jsonschema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/)
- [Schema source and provenance](../THIRD_PARTY_NOTICES.md)

- [Kubernetes label selector semantics](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
- [Kubernetes probe configuration](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
