# Security policy

## Reporting a vulnerability

Report vulnerabilities privately through GitHub private vulnerability reporting:
open the **Security** tab of
[deavgprime/iac-eval-bench](https://github.com/deavgprime/iac-eval-bench/security),
then select **Report a vulnerability**. Do not open a public issue.

Include the affected version or commit, steps to reproduce, and the impact you
observed. You will receive an acknowledgement within 2 working days.

## Supported versions

Fixes are made on the `main` branch and included in the next release.

## Scope

The evaluator parses and validates model output offline. It does not execute
candidate commands or contact a cluster. Reports about the evaluator, the
provider adapters, the run and resume logic, and the HTML report output are in
scope.
