# T53 — Preserve a specific, safe pause cause

Status: Not started
Priority: Medium
Depends on: current branch state and request-error metadata
Size: M
Planning baseline: `4b6ed68`, September 14, 2026

## Outcome

Every newly paused unattended run exposes what stopped, which item/stage was
affected, and the supported next action. The operator should not have to open
`task.json` to distinguish a quota problem from a missing decision or a restart.

## Current evidence and files

Read [branch_controller.py](../../cheapos/branch_controller.py) (`execute` and
launch failure handling), [branch_runs.py](../../cheapos/branch_runs.py)
(`summary`, `recover_restart`), [engine.py](../../cheapos/engine.py) (typed errors,
request failures and runtime recovery), and [server.py](../../cheapos/server.py)
(public task/summary projections). Reuse provider, environment, budget, and
authority error metadata already available.

The controller currently infers several reasons from words in exception strings
and otherwise uses `missing_information`. `task.error` may contain more detail,
while summaries carry only the broad reason. Surface structured evidence rather
than dumping the last raw exception or upstream response into the browser.

## Work

1. Add a bounded, versioned pause-detail record alongside existing status and
   `pause_reason`. Suggested fields: cause code, safe explanation, stage, item ID,
   role/model when known, diagnostic event/request ID, and next-action code.
   Include cooldown scope/reset only when supported by recorded metadata.
2. Classify new failures from typed exceptions and structured metadata. Keep
   operator Pause, restart, missing setup, new command permission, exhausted
   allowance, branch drift, changed authority, provider quota/connection failure,
   malformed model response, repeated work, and essential clarification distinct.
   A message containing “limit” is not sufficient to prove budget exhaustion.
3. Carry the original cause through worker recovery and the outer branch catch;
   do not overwrite a known quota or tool failure with generic missing information.
   Link to existing retained diagnostics rather than copying unbounded payloads.
4. Public messages must come from controlled templates and bounded, safe metadata.
   Do not expose keys, headers, credential-bearing URLs, full raw provider bodies,
   tracebacks, or unrelated project content. Unknown failures get an honest
   generic explanation plus a diagnostic reference, not an invented remedy.
5. Persist details through refresh/restart. Distinguish an execution interrupted
   by restart from a previously paused failure. Clear the active banner when
   work validly resumes while retaining historical events. A completed task must
   not display a stale active failure.
6. Extend the existing allowlisted public projections consistently. Old tasks
   without details should keep a useful fallback; do not rewrite their history
   or require a new authorization solely to view a pause.
7. Next-action metadata describes existing controller operations, not permission
   to execute them. Do not change resume, budget, commit, or command grants in
   this card. T54 consumes this record in the interface.

## Acceptance

- Representative failures map to distinct causes with stage/item context and a
  supported next action. Unknown reset times stay unknown.
- Nested recovery preserves the causal error; refresh and restart retain it.
- New events and public summaries expose safe fields only. Synthetic secrets in
  an upstream error do not appear in either public task representation.
- Legacy tasks render a fallback, successful continuation clears the active
  pause, and history remains available.
- Merely reading a pause record dispatches no model, command, or resume operation.

## Focused validation and handoff

Start with the selector plan. Use pure classifier/state dictionaries and tiny
serialization cases. Reuse relevant existing `test_branch_runs.py`,
`test_branch_recovery.py`, `test_branch_state_storage.py`, and `test_branch_http.py`
cases; avoid real restarts and sleeps for a projection test. Report the schema,
legacy behavior, selected checks and new-case timing. Disclose any proposed
heavy case before adding it, then commit and update the task board.
