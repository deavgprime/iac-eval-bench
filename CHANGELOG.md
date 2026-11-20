# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Bounded Qwen2.5-Coder 1.5B CPU pilot with retained failure and resource evidence.
- Six-task comparison of Qwen2.5-Coder 1.5B and 0.5B with all attempts retained.
- Workflow and selector-case figures in the scoring audit.

### Changed

- Simplified report wording.
- Updated the GitHub username and repository links.
- Marked generated HTML reports as generated for language statistics.

## [0.2.0] - 2026-10-17

### Added

- Suite v2 with versioned task definitions and a scoring audit with regression cases.
- Audited v2 reference and mutated baselines; v1 evidence is preserved.
- Explicit task completion coverage and an operational macro score that counts provider errors as zero.

### Changed

- Selector checks evaluate every `matchLabels` and `matchExpressions` constraint against the pod labels while still requiring the explicit app label.
- Readiness probes with more than one handler fail, and port checks apply the default TCP protocol and detect transport mismatches.
- NetworkPolicy scoring no longer depends on rule, peer or port order.
- Omitted default fields and compatible extra pod-security fields are accepted.

### Fixed

- Resume verifies the recorded configuration and provenance against the actual run inputs.
- Excessive JSON nesting and invalid escaped Unicode are reported as parse failures.
- Truncated HTTP responses are classified as provider failures.
- CSV reports use LF line endings on every platform.

## [0.1.0] - 2026-10-17

### Added

- Offline static evaluation of LLM-generated Kubernetes configuration against pinned Kubernetes 1.34 JSON schemas and six synthetic tasks.
- Command-line runner with provider adapters, resumable runs and HTML, CSV and JSON reports.
- Constructed positive and negative fixture baselines with raw evidence.
- CI workflow with lint, tests, baseline verification and wheel checks.

[Unreleased]: https://github.com/deavgprime/iac-eval-bench/compare/2e7b620...HEAD
[0.2.0]: https://github.com/deavgprime/iac-eval-bench/compare/363b5c4...2e7b620
[0.1.0]: https://github.com/deavgprime/iac-eval-bench/commit/363b5c4
