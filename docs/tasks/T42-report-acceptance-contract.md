# T42 — Independent acceptance for the report exporter

Status: Not started
Depends on: T41
Size: M

## Outcome

Before a live worker implements the exporter, an independently prepared,
small acceptance pack defines what the feature must actually do. Workers still
write their own useful unit tests; they cannot obtain success merely by writing
tests that repeat an invented implementation or schema.

## Read first

- [Exporter specification](../trials/unattended-run-report.md).
- [Matrix failures](../trials/matrix/RESULTS.md), particularly the Decimal
  regression and the README example that failed after app readiness.
- `cheapos/branch_runs.py`, `branch_commits.py`, `branch_completion.py`,
  `branch_evidence.py`, `storage.py`; `dist/branch_ui.js` receipt presentation.
- Existing focused fixtures in `tests/branch_fixture.py` and branch tests.

## Work

1. Inspect the actual saved schema and completed receipt contracts. Record each
   exported requirement, its source fields, and the check that will establish it.
   Do not infer success from status text alone or invent fields such as
   `feature_branch` where current records use a different name.
2. Put the independent acceptance pack under a dedicated directory such as
   `docs/trials/run-report-acceptance/`, outside ordinary `tests/` discovery until
   the feature exists. Include instructions and minimal synthetic records with
   no personal paths, credentials, chat contents, or copied user task history.
3. Provide focused standard-library tests for deterministic formatting, valid
   versus stale/mismatched receipts, partial/missing accounting versus real zero,
   Markdown/Unicode labels, allowlisted output, and unchanged inputs. Include a
   runnable minimal usage example tested as code. Choose a few discriminating
   cases rather than a large combinatorial matrix.
4. Provide narrow endpoint acceptance for read-only download, supported versus
   unsupported task/run input, safe headers, and no model/Git/save side effects.
   Reuse a disposable server fixture, not a new full branch execution per check.
5. Make each command runnable from a clean task copy using installed executables.
   Ensure imports find the real `cheapos` package. Map formatter checks to item 1
   and endpoint checks to item 2/final verification in the exporter specification.
6. Record a digest of the accepted test pack and example before Start. The trial
   driver must compare it afterward and reject qualification if the worker
   changes it. Include required commands in the inspected proposal; do not rely
   solely on tests that the observer runs after the app declares readiness.

## Acceptance

- The pack uses actual compatible records and catches the former report trial's
  invented fields/imports, false success receipts, and missing-value-as-zero bugs.
- Each important requirement maps to an executable check or a named browser
  scenario for T45. Non-executable claims are visibly unverified.
- Baseline checks fail for the expected absent feature, not an invalid fixture,
  missing test dependency, or zero-test discovery. Temporary minimal bad outputs
  demonstrate the key assertions fail; do not implement the real exporter here.
- No failing acceptance modules are added to the default regression suite before
  the feature exists. The agreed live proposal invokes this separate pack directly.
- Fixed acceptance files and hashes are independent of worker-authored tests.
  If a fixture defect is found later, record it, revise before a fresh attempt,
  and retain the old result instead of weakening a running contract.

## Validation

Inspect the selector plan and run only acceptance-pack self-checks/baseline
diagnostics, syntax checks, local-link checks, and `git diff --check`. Expected
baseline failure is evidence about an absent feature, not an application pass.
Record exact commands and observed errors. No live inference or full suite.

## Completion record

Behavior delivered: pending
Acceptance pack path, commands, and digest: pending
Baseline/self-check evidence: pending
Remaining limitations: pending

Update this card and TASKS.md; commit the pack/specification, not feature code.
