# T44 — CheapOS implements its report exporter

Status: Blocked (two incomplete live attempts)
Depends on: T42, T43
Size: L (one three-item feature run, not a controller rewrite)

## Outcome and role

Use CheapOS's real Unattended workflow to implement the feature in the
[report specification](../trials/unattended-run-report.md). The observing agent
prepares and drives the trial. CheapOS's worker writes the formatter, endpoint,
frontend control, documentation, and implementation tests. Its distinct reviewer
checks the actual work; its controller creates the feature commits.
An observer-written implementation is not completion of this card.

## Preflight

1. Verify T42/T43 are committed and available. Inspect the working tree and running
   app; do not interrupt another live job or switch a shared checkout underneath
   it. Use an isolated app worktree/data directory for repairs. Keep trial task
   storage outside the source snapshot.
2. Record app SHA, source SHA, relevant app/fixture hashes, proposal contents,
   acceptance-pack digest, configured pair, and access/cost basis. Use an exact,
   available worker/reviewer pair informed by the qualification matrix. Historical
   quota snapshots and catalog membership are not current readiness evidence.
3. Retain the authorized access policy. Public-free runs use eligible free remote
   routes and a $0 cap. Included subscription access requires its explicit scope;
   unknown pricing is not permission to assume zero. No local or paid fallback
   unless separately authorized. Never put keys in prompts or committed records.
4. Use explicit measurement mode per AGENTS.md. Keep spending checks, command
   consent, Pause, transport guards, and usage records. Do not substitute huge
   numeric caps or keep resuming an unchanged failed run.

## The inspected proposal

Submit the exact three dependent implementation items from the specification:

1. Pure deterministic `cheapos/run_report.py` formatter and focused tests.
2. Read-only Markdown download endpoint with isolated HTTP tests.
3. Accessible Export report UI control, focused Node tests, and documentation.

Include T42's independent commands in the relevant item/final checks alongside
the worker's focused tests. Capture test consent through the normal inspected
Start flow. Do not substitute a completion echo, empty discovery, or the full
Python suite. Reuse valid current verification evidence through existing logic.

Try the actual prompt/document planning path. Inspect its exact output before
Start. If the operator prepares or corrects the plan, preserve the original and
label planning assisted. Use existing run API/UI; do not build a second controller.

## Operation and failure handling

- Observe real work and record any guidance, Resume, code fix, restart, or manual
  change. Zero intervention is a result to measure, not a label to assume.
- If an app defect blocks progress, preserve the attempt and repair the app in a
  separate commit with focused fast coverage. A new app revision means a separately
  identified attempt, not an unchanged controlled run. Do not hide app repairs in
  the worker's feature patch.
- Do not manually repair the exporter's code to finish the experiment. Retain an
  incomplete candidate and report the missing requirement if the worker stalls.
- No unrelated feature, schema migration, package install, billing lookup,
  telemetry service, merge, or push is in scope.

## Acceptance

- The formatter, endpoint, UI, and docs exist in the task's reviewed feature
  commits; saved receipts match the run/items and actual commit contents.
- All item and final checks pass; independent acceptance files are unchanged.
  A provider response or `ready_for_merge` label alone is insufficient.
- Source files/main remain unchanged by the trial, and a fresh merge preview
  accurately presents the candidate for an operator decision.
- The observation log separates planning assistance from execution interventions,
  with elapsed time, request/usage totals, failures, and uncertainty.
- Feature tests are narrow and fast. Do not introduce another multi-item branch
  integration test for a read-only formatter or download endpoint. Disclose any
  proposed heavy test and obtain acceptance of its extra cost before adding it.

## Validation and handoff

The run's focused acceptance is the validation. Do not rerun unchanged passing
checks just to update this card. T45 handles browser acceptance and final
independent qualification. On failure mark this card Blocked with the exact saved
state and attempted recovery; T45 may still document the failed outcome.

## Completion record

App/source revisions and task ID: pending
Feature branch/commit receipts: pending
Planning assistance and execution interventions: pending
Commands, outcomes, timing, and accounted usage: pending
Acceptance-pack integrity: pending
Remaining limitations: pending

Commit the observer's sanitized record separately from feature work.
Leave feature integration to the operator. Update T44 in TASKS.md truthfully.

Attempt 1 retained: [qualification record](../trials/exporter-20260913/RESULTS.md). No exporter code was written by the observer.
