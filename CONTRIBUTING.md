# Contributing

You may fork this repository and open a pull request for an unassigned issue or a
small reproducible bug. Comment on an issue before starting substantial work so
contributors can avoid overlap; assignment is not required. For a new backend,
scoring change or large task expansion, discuss the design in an issue first.
Review and merge remain maintainer decisions. No CLA is currently required;
contributions use the repository license.

Install the development lockfile and run the checks in the README. Keep a PR
focused and explain its observable behavior, tests and limitations.

A task contribution must include:

- A new synthetic or appropriately licensed prompt with provenance.
- Explicit resource inventory and requirements, with no private/customer data.
- A passing reference and at least one schema-valid negative example.
- A test showing the intended requirement fails, plus accepted alternatives where relevant.
- A task/suite version change when an existing scoring contract changes.

Fixtures must never be labeled as measured model results. Real model results need
exact prompts, source/model revisions, settings, raw outcomes, usage/coverage and
runtime details. Do not silently drop failed attempts or overwrite published runs.

Bundled schema updates need pinned source URLs, checksums, upstream license notices
and regression validation. The evaluator does not execute candidate commands.
