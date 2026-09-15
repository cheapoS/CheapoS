# Continue an unattended run from chat

A paused run should accept ordinary operator language. Sending a follow-up
(including “try again” or “continue”) now saves that guidance, then calls the
existing branch-resume operation on the same run. It does not create a replacement
task, discard files, renew recovery attempts, increase limits, or authorize a new
plan. Active-run guidance still waits for the next worker turn.

The composer shows delivery immediately. After delivery, the conversation shows
“Continuing saved work…” while resume is pending. Duplicate sends are disabled.
If resume fails, its error remains visible with the saved guidance, and the
operator can retry from saved work without sending the guidance again. Expired
verification grants still open the existing scoped-consent dialog; merge recovery
still requires its existing confirmation. Permission, branch ownership, spending,
verification, and independent review remain enforced by the server.

## Transport compatibility

A successful JSON retry after an SSE compatibility failure now establishes a
task-local JSON preference for that route, role, purpose, and connection revision.
The next ordinary request uses JSON instead of repeating the broken stream. Each
request still passes the usual accounting, cancellation, and authority checks.
Failed/cancelled JSON retries never establish compatibility, and no allowance is
refunded. The preference persists across reload and request-history compaction.
Old saved tasks can recover it from an accounted successful fallback record.

The separate bounded eligible-model handoff added in `cc50684` remains in place
if transport recovery is exhausted. This is transport recovery, not a coordinator
consultation. Optional coordinator assistance applies to eligible worker stalls
in both Interactive and Unattended mode, and otherwise stays idle.

Old unknown transport pause banners are projected from their retained typed error
and matching request identity. They explain the streaming failure and offer Resume
saved work, while retaining original diagnostic history. An older error cannot
replace a later operator, budget, permission, or other specific pause.

## Validation (2026-09-14)

- Transport, brief transport, and pause projection: 34 tests passed in 0.119s.
  The new transport-scope case took under 0.001s and the legacy-pause case 0.005s.
- Frontend checks: 178 tests passed in approximately 0.12s. Four new chat cases
  cover save-before-resume, ordinary wording, duplicate protection, saved guidance
  after failure, active-run steering, rejected delivery, and scoped consent;
  together they took under 0.01s. Existing renderer assertions cover pending/error
  feedback, escaped diagnostics, retry controls, and populated pause details.
- Existing branch recovery, execution-context, and planning-race checks passed
  (11 cases). The existing recovery module took 58.7s; no new heavy case was added.
- Existing model-pool module: 20/21 passed. The action-recovery handoff test
  `test_unavailable_tool_during_action_recovery_hands_off_without_executing_any_calls`
  expects worker `b` but receives `a`; the same failure reproduces from an unchanged
  `cc50684` archive in a separate directory (0.435s). Its assertions are unchanged.
- Browser acceptance uses a disposable repository and scripted providers only.
  Personal tasks and real model endpoints are not test fixtures.

Browser result: entering **continue** in the paused task saved one guidance
message and showed immediate continuation status. Releasing the fixture's held
request resumed the same workspace with JSON, ran the saved unit test, completed
scripted independent item/final reviews, committed the item, and displayed
**Ready for your review**. The fixture asserted that the worker received operator
guidance and the saved file content, and that it never attempted SSE. Populated
pause details were visible; no live model requests or personal task mutations
were made. This is deterministic UI/controller coverage, not a live-model quality
qualification. The temporary browser fixture is not added to routine tests.
