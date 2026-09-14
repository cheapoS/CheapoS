# T73 — Explain the actual stop reason directly in Chat

Status: Completed
Priority: High — stop hiding actionable failures
Depends on: existing T53/T54 structured pause implementation
Size: M
Planning baseline: `db774c7`, September 14, 2026

## Outcome and operator report

When work stops, the main cheapoS message explains what actually failed and what
the operator can do next. Reading a technical log, opening Details, or changing
tabs must not be required to understand the cause.

The reported message is:

> Work stopped
> This run stopped for an unclassified reason. Inspect the retained diagnostic.
> Saved edits remain in the task copy.

That is inadequate when the retained diagnostic already records a concrete
failure. Unknown classification does not mean the error message is unknown.
Explain the observed failure without pretending to know an upstream root cause.

## Current code and existing evidence

Read [branch_pause.py](../../cheapos/branch_pause.py) (`classify`, `public`,
`apply`), [server.py](../../cheapos/server.py) (`public_task`),
[branch_controller.py](../../cheapos/branch_controller.py) (exception handling),
[branch_ui.js](../../dist/branch_ui.js) (pause presentation),
[guidance.js](../../dist/guidance.js), and
[test_branch_pause.py](../../tests/test_branch_pause.py).

The public pause record currently reconstructs explanation text from a generic
template. `public_task` also replaces `task.error` with that templated explanation.
Changing only an event title or logging a traceback does not fix the information
lost between exception, saved task, public response, and main banner. Reproduce
the whole data path before deciding which layer to change.

The existing missing-executable HTTP assertion identified during the planner
review already fails at baseline `3aa9397`: it expects the absent executable name
but receives only “The task verification environment needs setup.” Address that
same specificity gap here; do not erase the assertion or blame the new planner.

## Implementation work

1. Trace representative failures from their source through pause capture,
   persistence/reload, public serialization, and banner rendering. Keep one
   canonical structured explanation contract shared with Activity and T72.
2. Preserve a bounded, sanitized specific diagnostic alongside the classified
   cause, stage, role/model where relevant, and supported action. Prefer trusted
   structured fields/known error builders. Do not surface arbitrary raw exception
   payloads, provider bodies, credentials, headers, or environment values.
3. When classification is unknown but a safe specific message exists, show it
   prominently instead of replacing it with “unclassified reason.” Preserve its
   meaning through `public_task` and refresh; retaining it only in server logs
   or an expandable technical event is not sufficient.
4. Make the main banner explain the observed failure and consequence in plain
   language, followed by the available next action. For example, when supported
   by evidence: “I couldn't run verification because the selected executable
   `python` isn't available. Choose an available executable and re-check this
   task's environment.” An invalid JSON review response should identify review
   as unfinished, not blame project code or invent a quota cause.
5. Distinguish operator pause, restart, quota, connectivity, invalid model output,
   missing runner, failed checks, exhausted limits, authorization/branch conflict,
   and review disagreement using their existing concrete evidence. Include the
   actual limit/command/error detail where safe and helpful. Claim saved changes,
   passed checks, or commits only when their records support those claims.
6. Preserve the latest relevant failure across restart and ordinary polling.
   A generic wrapper or housekeeping event must not overwrite its cause. A new
   failed attempt must not inherit a stale failure from a previous attempt;
   correlate diagnostic/request/event identity and clear active state through
   existing successful/resume transitions, retaining historical events.
7. Reuse supported actions; do not offer a blind Resume when setup or new
   authorization is required. T72's View technical logs link may provide further
   context once available, but it is always secondary to the visible explanation.
   Rendering must not grant permission, retry inference, or renew allowances.
8. If no diagnostic was recorded, say so honestly, identify the known stage and
   available recovery path, and retain a diagnostic reference if one exists.
   Do not guess, make a diagnostic model call, or re-run work to manufacture a
   cause. Keep legacy tasks usable without inventing missing history.

## Acceptance and focused validation

- A synthetic unclassified exception with a safe concrete message retains it
  through apply/save/load/public serialization and shows it in the main banner.
  The operator does not need to expand Details or visit Technical logs.
- A missing-executable fixture names the unavailable runner and offers the
  environment action; a malformed review response identifies the failed review;
  a known quota case shows the actual recorded scope/retry information, if any.
- The latest failure wins over generic wrappers but is not replaced with an
  unrelated old diagnostic. Restart/polling retain the correct message.
- Private/HTML-looking diagnostic inputs are filtered and escaped; genuinely
  absent details stay unknown. No new authority or retry is introduced.
- Use pure pause/public-record round trips and small JS presentation cases.
  Reuse the existing missing-runner HTTP case rather than adding another full
  workflow. Inspect an isolated browser fixture with this exact generic-banner
  scenario and a concrete retained error; the failure must be clear in Chat.
  Share the fixture with T69–T72 and record any unavailable browser checks.
- Measure any new cases. No real sleeps, live providers, automatic diagnosis
  calls, or heavy agent/Git tests. Update this card and TASKS.md; commit only the
  scoped implementation after relevant validation.

## Completion record

Implemented a canonical bounded diagnostic contract, retained through public
serialization and pause persistence. Trusted missing-executable, planner repair,
review validation, and work-limit builders now explain the observed failure;
raw exceptions/provider bodies remain private. Request identity prevents an
unrelated later attempt from inheriting an old failure. Generic wrappers of the
same recorded request retain the concrete cause. Actions remain advisory and
retain existing permission, retry, and allowance semantics.

Validation: nine pure pause tests passed in 0.005s (four new cases); seven existing
review disagreement tests passed in 0.003s; fifteen existing planner tests passed
in 1.910s. The existing missing-runner HTTP case passed in 1.601s, including its
unchanged assertion naming the absent executable. UI presentation scenarios and
isolated browser availability are recorded with the shared T69–T72 UI work.
No new heavy fixture, live provider call, or retry authority was introduced.
