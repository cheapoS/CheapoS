# T101 — Idempotent branch updates and redacted structural telemetry

Status: **Planned — audit follow-up**, September 18, 2026. Priority: **P2**.
Parent: [T94](T94-operator-limits-and-autonomous-completion.md).
Deliver the two slices independently. Slice A can start without the other audit
patches; align Slice B with [T96 context recovery](T96-context-error-recovery.md),
[T97 provider recovery](T97-provider-recovery-consistency.md) and
[T99 effective budgets](T99-limits-settings-and-effective-budgets.md).

## Outcome and boundaries

An already-current branch update succeeds without sending the operator through
another error/retry cycle. When a payload or edit is transformed, local structural
measurements help locate the change without putting source text into diagnostic
logs. Neither feature expands authorization, starts extra model requests, or
replaces the six primary audit fixes.

This task does not introduce global semantic patch hashing. Python syntax-repair
tracking already uses an AST fingerprint to retain failure history through
cosmetic edits; T98 covers the broader unresolved-failure behavior. Documentation,
comments and formatting can remain legitimate work.

Read [AGENTS.md](../../AGENTS.md), [CONTRIBUTING.md](../../CONTRIBUTING.md) and
[AUTONOMOUS_WORKFLOW.md](../../AUTONOMOUS_WORKFLOW.md).

## Slice A — Successful no-op branch updates

### Evidence

At the audited baseline, `cheapos/branch_update.py:prepare` raises
“Task branch already contains the target. Choose Recheck changes instead” after
its ancestry check. `branch_completion.update_branch` exposes this through the
branch-update action as an error, although no branch update is needed.

### Implementation

1. Validate the same task, source ownership, worktree state, current refs and
   applicable authorization as the existing operation. Only then recognize that
   the feature branch already contains the selected target commit.
2. Return a successful structured no-op, such as HTTP 200 with `updated: false`
   and `state: "already_current"`, together with the normal safe task/readiness
   result. Check the existing response contract before choosing the exact envelope.
3. Do not create an empty merge commit, change refs, discard edits, fabricate an
   approval receipt, clear failed checks or consume a model request for the no-op.
4. Distinguish “branch current” from “review approved.” Reuse verification and
   independent review only while their full identities remain valid. If the
   authorized Update & recheck action still requires checks/review, continue that
   unfinished phase automatically; do not bounce the operator back to Resume.
5. Preserve durable operation identity so repeated clicks, a lost HTTP response,
   or restart do not duplicate an update or recheck. Respect target movement
   between inspection and application; never treat a stale no-op result as fresh
   merge authority. Keep final merge approval separate.
6. Make UI/orchestrator callers handle the no-op as success. “Already up to date”
   is useful status; another recovery prompt is not the expected result.

### Acceptance

- [ ] Already-current target returns successful `updated: false`; source/task
  refs, trees and saved edits are unchanged and no model request is dispatched
  merely to determine that result.
- [ ] Duplicate submission/reload preserves the same operation outcome and does
  not repeat completed checks or start two pending reviews.
- [ ] Changed target, dirty task copy, stale ownership or invalid authorization
  still receive their correct handling; no-op detection bypasses none of them.
- [ ] Current passing evidence reaches the existing ready-for-review state;
  missing/stale evidence follows the authorized recheck path automatically.
- [ ] A no-op never grants merge approval or marks incomplete review as approved.

Starting points: `cheapos/branch_update.py`, `branch_completion.py`, `server.py`,
existing integration UI handlers, `tests/test_branch_update.py` and focused HTTP
fixtures. Extend existing temporary-repository coverage rather than adding a new
full multi-item agent/Git workflow.

## Slice B — Redacted structural telemetry at observed boundaries

### Evidence and naming

Saved failed tool arguments showed indentation loss during the historical syntax
loop, but raw gateway/model responses were not retained for every call. The XML
fallback parser was separately corrected in `49cbecb`; the saved arguments alone
cannot establish the origin of every historical transformation.

Call this **redacted structural telemetry**, not “zero-knowledge.” Counts and
sizes are diagnostic metadata, not a cryptographic privacy proof. Do not promise
that locally observed fields reveal unobserved upstream gateway behavior.

### Implementation

1. Extend existing local request/edit diagnostics with a small versioned schema
   tied to the existing request/tool identity and an explicitly named boundary.
   Use only allowlisted scalar fields, not arbitrary exception dictionaries.
2. Useful fields include payload byte size, logical edit byte/line counts,
   aggregate leading-space/tab counts, extraction path (native tool or XML
   fallback), whether a transformation occurred, and a normalized syntax-error
   category with numeric position when already available.
3. Capture comparable before/after metrics at boundaries cheapoS actually sees:
   response extraction, fallback argument decoding, and final edit validation.
   Distinguish encoded wire size from decoded argument size. An expected JSON/XML
   decoding difference is not proof of corruption. Mark unavailable upstream
   observations as unknown instead of reconstructing or inventing them.
4. Never log raw source, prompt text, complete arguments, exception source lines,
   credentials, headers, or source encoded as hex/base64. Do not copy syntax-error
   messages that can embed private source. Do not add content hashes and call
   them anonymous proof; reuse existing identifiers only where appropriate.
5. Keep collection local and bounded by the existing diagnostics retention
   policy. Avoid per-character/per-chunk logs or repeated parsing of entire files.
   Reuse existing validation results; an incomplete edit fragment must not be
   parsed as a complete Python module solely for telemetry.
6. Telemetry failure or missing fields must not block work or alter requests,
   output budgets, tool arguments, routing, evidence or usage. No extra inference
   calls, provider probes or remote reporting are authorized by this task.
7. Link the measurements from Technical logs when useful. Keep ordinary Chat
   focused on actual work and continuation, not a new stream of diagnostics.

### Acceptance

- [ ] Synthetic native and XML calls retain their executed text exactly, including
  meaningful indentation; before/after metrics identify the locally observed
  representation and transformation without inventing an upstream cause.
- [ ] Fixture source, a secret marker, and their hex/base64 encodings never appear
  in serialized telemetry. Syntax diagnostics use allowlisted categories and
  numeric positions rather than source-bearing exception messages.
- [ ] Missing telemetry, collector failure and old saved records leave execution
  and continuation behavior unchanged; no request or tool is dispatched twice.
- [ ] Collection/retention is bounded and uses existing identities. One request
  cannot create unbounded diagnostic rows by streaming many tiny chunks.
- [ ] Correlation distinguishes request-size changes, parser transformations and
  validation results without claiming these metrics prove historical causality.

Starting points: `cheapos/providers.py`, `streaming.py`, existing fallback tool
parsing, `edit_history.py`, `edit_recovery.py`, `metrics.py` and Technical logs.
Verify current owners before editing. Coordinate T96/T99 fields so there is one
schema for the same observed size/budget rather than competing measurements.

## Validation and delivery

- [ ] Slice A implemented and validated.
- [ ] Slice B implemented and validated.

Start with `python3 -B scripts/check.py --plan`; run only affected checks. Prefer
small deterministic parser/telemetry cases and existing branch-update fixtures.
No live provider calls, private task fixtures, long sleeps or full suite are
needed by default. Disclose and obtain acceptance for new heavy tests under
AGENTS.md; measure and report new-test runtime.

Commit the slices separately when implementing them and record the actual
response contract, telemetry schema, checks and remaining limitations here.
External development agents commit only their own changes and tell the operator;
internal cheapoS workers leave Git operations to the controller. The operator
handles app restarts.
