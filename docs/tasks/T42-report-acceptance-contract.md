# T42 — Independent acceptance for the report exporter

Status: Done
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

Behavior delivered: independent synthetic schema projection, seven formatter
cases, two tiny HTTP cases, six bad-output assertion controls, and a runnable
formatter example. No exporter implementation or ordinary regression tests added.

Acceptance pack: [README](../trials/run-report-acceptance/README.md),
[manifest](../trials/run-report-acceptance/DIGEST.json).
Pack SHA256: `ce21e1075fc06d9f7810ca6a41d5f133cfcb4c6acc38a92de5385169fa473397`.
Exact Item 1/final and Item 2/final commands are in the pack README and exporter
specification. Capture manifest bytes externally before Start and compare all
listed files afterward; a worker-edited manifest is not independent evidence.

Commands and results:

- `python3 -B scripts/check.py --plan`: initial clean tree, selected nothing;
  not counted as feature validation.
- `python3 -B docs/trials/run-report-acceptance/selfcheck.py`: 2 pass, under
  0.001 seconds test runtime; validates actual branch plan compatibility and
  six minimal negative outputs.
- `python3 -B docs/trials/run-report-acceptance/selfcheck.py --verify`: pass.
- Explicit formatter acceptance command: discovered 7 tests; expected baseline
  `ModuleNotFoundError: No module named 'cheapos.run_report'`, 0.002 seconds.
  The real `cheapos` import and fixture constructor work; only feature absent.
- Explicit endpoint acceptance command: 2 tests, 0.014 seconds; bounded-invalid
  requests/origin case passes, download case fails expected `404 != 200`.
  Initial sandbox socket denial was rerun with loopback permission; it is not
  confused with the absent-endpoint baseline.
- Python AST syntax, relative documentation links, and `git diff --check`: pass.

New-test cost: tiny synthetic dictionaries and one disposable loopback server
per endpoint case; measured baseline test body 0.014 seconds, no Engine startup,
Git workflow, model call or deliberate waits. Pack is outside default discovery;
only explicit live proposal checks run it. No heavy fixture introduced.

Browser scenarios: deliberately unverified, assigned to T45 in the pack mapping.
Remaining limitations: baseline is expected failure, not feature acceptance.
No Git revalidation of saved receipts; snapshot presentation uses saved identity
fields, with no claims of fresh execution or billing. Full branch receipt proof
remains the existing controller's responsibility. TASKS.md status managed by the
coordinating agent to avoid concurrent edits.

Update this card and TASKS.md; commit the pack/specification, not feature code.


### Version 2 follow-up (before T44 fresh attempt)

Corrected the observer's version 1 outcome fixture (`ready`, not `committed`) and
same-line count assertion. Added scoped missing-field/integration checks,
item-status and wrong-run checks, and Markdown delimiter cases. No original trial
pack or runtime was edited; version 1 remains in commit c93adfa with its original
digest above. Version 1 results must not be described as full independent proof.

Version 2 pack SHA256: `58630b139a9c8a69402bd4eda5f67f312ff924e7136b818f57befb36ec2844b0`.
Commands unchanged. Self-check: 2 tests, 0.001 seconds, nine negative controls plus
three valid count layouts. Feature-absent baseline: 7 tests, 0.001 seconds,
expected ModuleNotFoundError for cheapos.run_report; not an acceptance pass.
Endpoint fixture unchanged; prior 0.014-second expected-404 baseline remains
applicable. AST syntax, digest verification and whitespace checks pass. No live
inference, exporter code, full suite, or new heavy test was introduced.


### Version 3 follow-up (future qualification only)

Semantic status checks now accept valid Markdown escaped underscores; injection
checks remain raw. Absent-commit checks reject abbreviated fixture SHAs as well
as full SHAs. Confirmed full-SHA, missing accounting and mismatched merge tests
remain intact. Version 2's frozen attempt and failures are preserved.

Version 3 pack SHA256: `b44fa1b8dbe774c4788258e3c25173a0e3f202520952f82200c264151442212d`.
Self-check: 2 tests in 0.001 seconds, ten negative controls, including shortened
false commits, plus valid escaped pause/no-change controls. Syntax, digest and
diff checks pass. No feature implementation, live calls, new heavy fixture or
unchanged baseline rerun. This is an observer contract correction, not a pass
for either historical incomplete attempt.
