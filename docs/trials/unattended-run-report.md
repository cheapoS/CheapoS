# Live trial: export an Unattended run report

## Goal

Add **Export report** to an Unattended run so an operator can download a concise
Markdown account of what happened. This should be useful when returning to a
finished or paused job. CheapOS's own live workers and independent reviewer are
to implement this feature through the Unattended workflow.

Implement the three dependent items below, including each item's tests. Keep the
change small: standard-library Python and the existing vanilla frontend, with no
new dependencies. Read current code rather than assuming proposed APIs exist.
Do not implement unrelated cards from TASKS.md or BRANCH_RUNS.md. The original
milestones are complete; T41–T48 coordinate this trial and its later follow-ups. This document defines the entire feature for this trial.

## Existing integration points

- `cheapos/storage.py`: `Store.get()` returns a copy of the saved task.
- `cheapos/metrics.py`: existing aggregation and cost-provenance conventions.
- `cheapos/branch_runs.py`: run/item states and compatibility rules.
- `dist/branch_ui.js`: `projectRun()` already distinguishes verified completed
  commit receipts from pending work, and confirmed integration from an incomplete
  merge receipt. Reuse those semantics in the report; do not treat a status string
  alone as proof of a commit or merge.
- `cheapos/server.py`: existing trusted local GET routes and response helpers.
- `tests/`: standard-library unittest backend tests and Node's built-in frontend
  test runner. Pure reporting tests do not need a real multi-item branch run.

## Item 1 — report formatter and truthful outcomes

Create `cheapos/run_report.py` with a small pure function such as
`render_run_report(task) -> str`, plus `tests/test_run_report.py`.

The report includes a heading/title, run ID, current outcome, feature/target branch
names, ordered item titles/statuses and confirmed commit SHAs, check counts and
saved independent-review decisions, worker/reviewer model IDs, accounted tokens
and cost with provenance, accounted working time, and a saved pause category if
present. Use headings and short lists or tables. Do not calculate financial
savings or turn a feature commit into a claim of operator acceptance.

Acceptance criteria:

1. Deterministic Markdown covers ready-for-review, merged, left-on-branch, paused,
   and incomplete runs. Only a completed receipt matching the run/item establishes
   a commit; confirmed integration needs its completed merge receipt. Reviewed
   no-change items create no invented SHA or extra commit count.
2. Missing/partial historical usage, costs, timestamps, or reviews are labeled
   unavailable rather than silently zero or passed. A recorded zero stays zero;
   estimates/uncertain reservations remain labeled. Use saved accounting, never
   a network billing lookup or a call to the current clock to invent duration.
3. Explicitly allowlist output fields. Exclude prompts, captured document contents,
   assistant/reasoning text, raw events/logs/test output/diffs, provider credentials
   or endpoint URLs, authorization/proposal tokens, grants, and absolute source or
   workspace paths. Escape Markdown delimiters/newlines in displayed labels.
4. Unit tests cover these states, missing fields, Unicode/Markdown labels,
   credential-bearing fields that must be omitted, invalid/non-run input, and
   unchanged input data after rendering. Use small representative dictionaries.

Required checks:
`python3 -B scripts/dev_tests.py --pattern test_run_report.py`

`python3 -B scripts/dev_tests.py --directory docs/trials/run-report-acceptance --pattern test_formatter_acceptance.py`

## Item 2 — read-only Markdown download endpoint

Depends on Item 1. Add `GET /api/tasks/<task_id>/run-report` and focused tests in
`tests/test_run_report_http.py`. Generate the report from a copied saved record.

Acceptance criteria:

1. A known supported Unattended task returns UTF-8 Markdown with a suitable text
   content type and an attachment filename derived only from the validated task
   ID, such as `cheapos-run-<id>.md`; task titles never become response headers.
2. Unknown task IDs and ordinary Interactive tasks return an appropriate bounded
   4xx error. Unsupported saved run schemas are handled clearly, without claiming
   the contents were validated. Existing same-origin/loopback checks remain.
3. Reading/exporting invokes no provider, test, checkpoint, Git mutation, resume,
   approval, or save operation, and changes no task status, counters, or receipts.
   Repeated requests for the same saved state return the same report.
4. Focused HTTP tests check success/content/disposition, Unicode, invalid task or
   run input, untrusted-origin rejection, repeated downloads, and no execution or
   persistence side effects. Use an isolated server and temporary saved records;
   do not rerun the entire branch workflow to test the exporter.

Required checks:
`python3 -B scripts/dev_tests.py --pattern test_run_report.py`
`python3 -B scripts/dev_tests.py --pattern test_run_report_http.py`

`python3 -B scripts/dev_tests.py --directory docs/trials/run-report-acceptance --pattern test_endpoint_acceptance.py`

## Item 3 — discoverable export control and documentation

Depends on Items 1 and 2. Add the **Export report** control to the existing
Unattended run summary in `dist/branch_ui.js`. Add focused frontend tests in
`tests/test_run_report.js` and a short section in `docs/unattended-runs.md`.

Acceptance criteria:

1. The control is keyboard accessible and available for supported saved
   Unattended runs, including paused, ready-for-review, merged, and left-on-branch
   outcomes. It downloads the endpoint's report; ordinary Interactive chats do
   not show it. It is not labeled as another approval or completion step.
2. Export does not start a job, rerun checks, consume model requests, approve,
   commit, merge, alter the composer draft, or close another Details disclosure.
   Existing progress, Pause, proposal, revision, and merge controls still work.
3. Focused Node tests exercise the exported control/URL and applicability rather
   than only searching source strings. Document what is included, omitted, and
   that this is a snapshot of saved evidence, not a provider billing receipt.
4. Existing frontend tests and syntax checks pass. Use an isolated UI preview to
   verify a real download if browser tools are available. If they are unavailable,
   explicitly leave browser verification to the observing operator; do not claim
   that it ran. The feature itself must still be complete and tested.

Required checks:
`node --check dist/branch_ui.js`
`node --test tests/test_run_report.js tests/test_branch_ui.js`

## Final integration checks and boundaries

Validate the final combined candidate with the focused formatter/HTTP tests,
T42's independent acceptance pack, and the relevant frontend checks. No full
Python suite or fixed 30-minute check allowance is required by this trial.

Implementation checks (the named feature tests are created by Items 1–3):

- `python3 -B scripts/dev_tests.py --pattern test_run_report.py --pattern test_run_report_http.py`
- `node --check dist/branch_ui.js`
- `node --check dist/app.js`
- `node --test tests/test_branch_ui.js tests/test_conversation.js tests/test_guidance.js tests/test_panels.js tests/test_run_report.js`

**T42 independent acceptance pack is finalized** under
`docs/trials/run-report-acceptance/`. Its README maps saved fields to checks;
DIGEST.json fixes the independent tests and runnable example before Start.
The observing driver must compare that captured manifest and every file afterward.
Baseline execution currently fails because the exporter/endpoint do not exist;
that expected failure is not a feature pass.

| Scope | Required independent command |
| --- | --- |
| Item 1 and final | `python3 -B scripts/dev_tests.py --directory docs/trials/run-report-acceptance --pattern test_formatter_acceptance.py` |
| Item 2 and final | `python3 -B scripts/dev_tests.py --directory docs/trials/run-report-acceptance --pattern test_endpoint_acceptance.py` |

Keep each command as a separate exact argv in the inspected proposal. The app
runs a program directly without a shell: use explicit filenames, not globs,
pipes, redirects, chained commands, or a consent-bypassing wrapper. Do not use
`node --test tests`; the installed runner needs the explicit file list above.

For development, inspect `python3 -B scripts/check.py --plan` and choose relevant
checks under [CONTRIBUTING](../../CONTRIBUTING.md). A clean working tree selects
nothing; it is not a tested feature. For committed changes, inspect
`python3 -B scripts/check.py --base main --plan` or use explicit paths, for example
`python3 -B scripts/check.py --files dist/branch_ui.js --plan` for frontend work.
Documentation-only selection needs link/example inspection and a whitespace
check, without Python regressions. A deliberate comprehensive check remains an
option for a release or justified broad risk, not an automatic exporter gate.

Development selection is not the approved run's verification contract. Capture
the exact implementation and independent commands in each item's/final checks
before Start; later selection cannot silently replace that consent. Reuse saved
check evidence only when the candidate, exact command, and environment identities
still match. Do not rerun unchanged passing checks merely to open review or merge.

The earlier 18.5-minute full-suite observation and 30-minute allowance were
historical trial settings, not current requirements. The historical 46.329-second
measurement covers only 26 commit tests, not the whole suite; see the
[test-performance record](../development/test-performance.md). Keep failed trial
evidence and accounting. Live T44 uses explicit measurement mode per
[AGENTS.md](../../AGENTS.md), retaining spending policy, command consent, Pause,
transport guards, and usage records rather than substituting larger numeric caps.

Do not change model routing, limits, permissions, branch execution, commit/review
rules, Git internals, test-runner policy, or task schema to make this trial pass.
Do not weaken existing tests, add telemetry/cloud services, install dependencies,
write reports into the source checkout automatically, push, or merge. Keep report
creation a user-initiated local download. Existing saved tasks remain readable.

Each implementation item must finish its criteria, pass its checks, receive the
independent review, and be committed by the existing Unattended controller.
Final readiness is for the operator to inspect and decide on local integration.
The observing agent may diagnose or guide a problem; such interventions are
recorded separately and are not counted as autonomous success.
