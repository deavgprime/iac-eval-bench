# Design decisions

Short records of the choices that shape how the suite scores a response. Each one lists what was decided and what it costs.

## 1. Score one JSON object, not YAML or free text

**Decision:** a response is a single JSON object with a `resources` array. Prose, code fences and YAML are rejected at parse time.

**Why:** strict parsing removes a whole class of grader disagreements (indentation, multi-document streams, surrounding prose) and makes every failure attributable to one stage.

**Cost:** the suite does not measure YAML formatting, and a model that answers correctly in YAML scores zero.

## 2. Validate offline against pinned Kubernetes 1.34.0 schemas

**Decision:** strict JSON schemas from an immutable upstream revision are bundled with the package. No network or cluster is used.

**Why:** a run is reproducible years later and on machines without cluster access; schema drift cannot change a historical score.

**Cost:** schema validity is not API-server admission. Defaults, admission webhooks and runtime behavior are out of scope.

## 3. Schema and inventory failures gate all rubric credit

**Decision:** a response that fails schema validation, or does not contain exactly the requested objects, scores zero on every rubric check.

**Why:** partial credit for checks on a manifest that would not apply rewards output that cannot be deployed.

**Cost:** one wrong field hides otherwise correct work in the score. The raw evidence keeps every stage's result for inspection.

## 4. Provider errors are not quality failures

**Decision:** transport and provider errors get no quality score. They lower the operational pass rate, which is reported separately, and `operational_macro_score` counts them as zero.

**Why:** a timeout says nothing about the model's configuration skill, but hiding it would let an unreliable run look better than a complete one.

**Cost:** readers must check task coverage before comparing runs; reports include `task_coverage` for that.

## 5. No retries, repair loops or best-of selection

**Decision:** each trial sends one prompt with a recorded seed and keeps whatever comes back. Resuming a run requires matching configuration, input, schema and evaluator hashes.

**Why:** retries and selection change what is measured. Hash-checked resume keeps a resumed run the same experiment as the original.

**Cost:** retrying a failed attempt means starting a separately named experiment.
