# Live trial: export an Unattended run report

## Goal

Add **Export report** to an Unattended run so an operator can download a concise
Markdown account of what happened. This should be useful when returning to a
finished or paused job. CheapOS's own live workers and independent reviewer are
to implement this feature through the Unattended workflow.

Implement the three dependent items below, including each item's tests. Keep the
change small: standard-library Python and the existing vanilla frontend, with no
new dependencies. Read current code rather than assuming proposed APIs exist.
Do not implement unrelated cards from TASKS.md or BRANCH_RUNS.md; those milestones
are complete. This document defines the entire feature for this trial.

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

Required check:
`python3 -B scripts/dev_tests.py --pattern test_run_report.py`

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

Run the complete existing gate once on the final combined candidate:

- `python3 -B scripts/dev_tests.py --suite full --timings`
- `node --check dist/app.js`
- `node --test tests/test_*.js`

The app runs a program directly, without a shell. For the final Node command,
use a suitable exact argv that runs all test files (for example `node --test tests`
if supported by the installed Node version), or explicitly enumerate the actual
Node test paths in the proposal. Do not rely on shell wildcard expansion, pipes,
command chaining, redirects, or a wrapper that bypasses command consent. Inspect
and preserve the accepted check commands rather than silently changing them.
The last full Python gate took about 18.5 minutes; a 30-minute per-check allowance
is intentional. During implementation run the listed focused checks, not the
full suite for every item or again merely because an approval screen is opened.

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
