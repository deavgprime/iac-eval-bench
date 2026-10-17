# Scoring audit: suite v2

A focused code and regression audit of the static evaluator, task wording,
transport classification, aggregation and resume provenance. Initial revision:
[`cf07f06`](https://github.com/devgprime/iac-eval-bench/commit/cf07f06af0354a4b619b57a3169706953230cb86).
This review found five scoring errors and one resume-provenance defect. All six
have regression coverage in v0.2.0. This is an internal engineering review;
no independent model evaluation or cluster admission test was performed.

## Reproduced scoring errors

Each case starts from a reference fixture and changes only the described field.
The [before/after observations](scoring-audit-results.json) record the actual outputs.

| Case | Previous result | Required result / v2 result |
| --- | --- | --- |
| Add `app NotIn [api]` to a Deployment selector whose pod has `app=api` | Pass | Fail: selector contradicts the pod labels |
| Add an unrelated `team=platform` pod label | Fail | Pass: the required app label and selector remain valid |
| Add `app Exists` to the PDB selector | Fail | Pass: the extra constraint matches the target pods |
| Add a TCP handler to the existing HTTP readiness probe | Pass | Fail: multiple probe handlers |
| Set the workload's named port to UDP while its Service uses TCP | Pass | Fail: the declared transports disagree |

The original selector check examined only `matchLabels`; it never evaluated
`matchExpressions`. Conversely, whole-object equality rejected harmless metadata
or compatible selector additions. V2 checks every declared selector constraint
against the submitted Deployment pod labels while requiring the explicit app label.
The task wording now states this contract.

The probe and port checks previously verified only required dictionary keys.
That missed incompatible extra handlers and protocol changes. V2 validates the
HTTP readiness action and selected timing/target restrictions, and applies the
omitted TCP protocol default when comparing port requirements.

## Other corrections and clarified choices

- **Resume attribution:** changing `run.json`'s recorded model configuration without
  changing its fingerprint previously let resume produce a misleading report.
  Resume now verifies the recorded configuration/provenance fields against the
  actual run inputs. Runtime/dependency versions participate in the fingerprint.
  A regression test first reproduced the old acceptance, then verified rejection.
- **Order invariance:** NetworkPolicy direction and peer/port/rule ordering no
  longer determines the score. Element multiplicity is retained; duplicated or
  altered peers cannot replace the required entries. This is an intentional
  contract improvement, rather than a claim that v1 promised order invariance.
- **Compatible defaults and additions:** omitted TCP protocol on workload/Service ports and explicit default
  HTTP probe options are accepted. Extra pod-security fields may coexist with
  required values. The container security context remains exact as the prompt specifies.
- **Input/transport failures:** excessive JSON nesting and invalid escaped Unicode
  become explicit parse/protocol failures. Truncated HTTP responses are classified
  as provider failures instead of escaping the adapter as exceptions.
- **Aggregation:** task completion coverage is explicit. Operational macro score
  includes provider errors as zero; the existing conditional macro score retains
  its documented denominator. Tests verify equal task weighting and unknown costs.

## Regression evidence

The suite contains 51 test methods, including subcases for:

- All original positive and targeted negative fixtures.
- A missing-required-field or forbidden-field mutation for **each of the 50 rubric checks**.
- Selector operators, matching and conflicting selectors, harmless labels and PDB variants.
- Probe handler conflicts, timing boundaries, host/scheme overrides and valid defaults.
- TCP/UDP/SCTP mismatches, network array permutations, duplicates and AND/OR peer changes.
- Provider envelope failures, HTML escaping, incomplete coverage, interrupted runs and provenance integrity.

Run from the repository root after installing the development dependencies:

```bash
python -m unittest discover -s tests -v
python scripts/verify_baselines.py --output runs/audit-reproduction
```

The current fixture baseline is stored separately under `baselines/v2`.
The original `baselines/reference` and `baselines/mutated` remain unchanged.
Both versions' reference cases pass 6/6 and their targeted negative controls have
0/6 passes; the new adversarial tests expose differences those original fixtures missed.
Do not compare or combine model scores across these suite contracts without rescoring.

## Remaining limits

The suite remains six public synthetic tasks. Static schemas and selected semantic
checks do not reproduce complete Kubernetes admission or runtime behavior. Label
syntax, all API cross-field invariants, every equivalent network-policy form and
all defaults are outside the implemented checks. Exact quantity strings and other
explicit task constraints remain deliberate. No model endpoint was used, and the
fixture results do not measure model quality or general IaC competence.

Semantic references:
[labels and selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/),
[probe configuration](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).
