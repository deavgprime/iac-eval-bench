# Roadmap

Implemented in 0.2: six Kubernetes tasks, schema/rubric scoring, fixture and Ollama
adapters, adversarial scoring regressions, selector/protocol/probe checks, persisted/resumable runs, JSON/CSV/HTML reports, explicit usage/cost
coverage, regression tests and CI.

Next work, not implemented:

1. Extend the [published single-task real-model pilot](../results/2026-10-17-qwen25-coder-15b-pilot/README.md) to a resource-budgeted full-suite experiment with repeated trials and a second model. The pilot establishes execution and failure evidence; comparative model quality remains unmeasured.
2. Independently review task wording and acceptance checks; expand accepted
   semantically equivalent configurations without weakening failure detection.
3. Add Terraform/OpenTofu tasks with pinned providers and isolated validation,
   keeping provider/setup failures separate from generated-code errors.
4. Add a held-out task design and larger sample protocol before reporting rankings
   or statistical intervals.
5. Add an adapter/export format for an established agent-evaluation framework
   after choosing its execution and scoring contract. No Harbor/harness integration
   is claimed today.
6. Add isolated API-server dry runs and runtime tests as a separate opt-in track.

Small fixes and regression tests can be proposed directly. Larger changes should
start with an issue that describes the behavior and evaluation evidence.
