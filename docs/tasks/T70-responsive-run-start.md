# T70 — Close Start immediately and show startup in chat

Status: Ready after dependency
Priority: High — responsive orchestration
Depends on: T69
Size: M
Planning baseline: `db774c7`, September 14, 2026

## Outcome and current behavior

Clicking Start on an inspected proposal immediately closes the dialog and returns
to that task's Chat with visible startup progress. The operator never waits in
a frozen proposal window for the worker or gateway to become ready.

At the baseline, the Start handler in `branch_ui.js` awaits the `branch-start`
API call before closing the dialog or selecting the task. Move the visible
transition ahead of that wait while preserving the authorization contract.
Immediate dismissal is not a claim that the server has accepted the request.

## Read first

[branch_ui.js](../../dist/branch_ui.js) (proposal Start handler),
[app.js](../../dist/app.js) (task selection, pending actions, chat progress),
[server.py](../../cheapos/server.py) (`branch-start`),
[branch_controller.py](../../cheapos/branch_controller.py) (`authorize`, `launch`),
[test_branch_ui.js](../../tests/test_branch_ui.js), and existing start/HTTP tests.

## Implementation work

1. On a valid Start click, synchronously capture the inspected proposal/task
   identity, guard against duplicate submission, close the dialog, and select
   that task's Chat. If selecting a task normally awaits refresh, provide a
   local transition so network latency cannot leave the old modal in place.
2. Show an immediate pending state such as “Starting your approved plan…” inside
   cheapoS's conversation. Mark it as pending until the server acknowledges.
   Keep model selection, checks, and worker pickup visible as real events arrive;
   do not animate invented tool actions or success.
3. Keep the existing explicit `approved` decision and exact proposal binding.
   Preserve stale-proposal checks, command scopes, serialized execution, and
   server idempotency. Do not pre-authorize another plan to make the UI faster.
4. Handle rejection in the task chat with a specific recoverable action. Retain
   the proposal and captured input until successful acknowledgement; a detached
   dialog must not swallow errors. Do not clear the current composer if the
   operator typed a new message while the original Start request was pending.
5. A timeout or lost response has an unknown outcome. Reconcile task state
   before retrying the same action; never create a second run/branch or auto-send
   a new approval. Task switching/reload must not misattribute the response.
6. Preserve Pause visibility near the composer once applicable. If cancellation
   while Start is pending is offered, bind it to the correct run and prevent a
   late response from silently starting work after cancellation.
7. Inspect backend response timing. If authorization currently blocks on model
   pickup, return after durable acceptance/dispatch scheduling, retaining all
   checks and surfacing later failures through the task. Do not redesign the
   backend when the UI await ordering alone resolves the problem.

## Acceptance and focused validation

- With the Start API promise deliberately unresolved, the dialog is already
  closed and Chat shows pending startup before any provider response.
- A second click/Enter/retry cannot create a duplicate start. Successful
  acknowledgement joins the existing event stream without duplicate narration.
- Rejected/stale proposals show errors in Chat and retain recoverable input.
  Unknown outcomes reconcile with the server instead of silently retrying.
- Slow startup, failure, task switching, and the applicable Pause behavior are
  exercised using controlled promises/events, not real sleeps or model calls.
- Reuse T69's isolated browser fixture and existing authorization/HTTP coverage.
  Run backend checks only for changed backend paths. Record timings and exact
  browser outcomes; update this card/TASKS.md and commit the scoped changes.

## Completion record

Pending.
