# Coordinator-assisted recovery (T82)

Implemented September 14, 2026. Core implementation: `2ab0367`;
follow-up documentation/integration commit is the commit containing this record.

## Settings and authority

Execution settings contain **Coordinator assistance — recommended**, Off/On,
and an installed local model selector. `execution.coordinator_assistance` is a
boolean defaulting to false; `execution.coordinator_model` is a saved string.
An empty model reuses the captured local chat model if available. Saving does
not perform inference, install a model, change placement, or authorize cloud
fallback. Existing tasks remain Off unless their captured configuration explicitly
opted in. New tasks and proposals snapshot the choice. Legacy authorization
comparisons accept only missing optional false/empty defaults.

Follow-up: current-chat On/Off is visible beside the composer and in pause/settings
views, separately from new-chat defaults. An explicit `coordinator_reassessment`
start option enables one unused consultation for a paused Interactive worker
progress stop with a captured local model. It rejects mixed start options,
Unattended tasks, pending approvals/checks/reviews/commits, environment/conflict
stops, exhausted time/turns and any existing episode for that request. It keeps
request history, counters, remaining working time, placement and review authority.
No applicable advice leaves a visible pause instead of dispatching the worker.
This is the only new current-chat opt-in; ordinary Resume does not enable it.
Eligibility compares current request turns against the operator's current limit.
An old worker-turn stop marker is cleared only if that check passes; it does not
raise the allowance or reset usage. Other retained limit stops remain blocking.

Local metadata must advertise completion/tools and must not identify a cloud
route. Missing/offline/ineligible local models return to ordinary recovery;
they do not prevent remote work. Local metadata inspection uses the existing
four-second socket timeout. No live inference was used for this implementation.

## Trigger and durable state

The engine calls assistance only after worker repeated inspection/action guidance
fails (or repeated unavailable tool calls). Reviewer decisions/coaching, planning,
normal progress and ordinary conversation do not trigger consultations. Permissions,
environment setup, known workspace conflicts, genuine user waits, cancellation
and hard limits retain their existing resolution paths.

`coordinator_recovery` retains one episode per Interactive request segment or
Unattended item, including review repairs within that item. Stable IDs bind the
attempt to request/item, candidate, authority, model and evidence fingerprint.
States are prepared, dispatched, completed, applied, skipped, failed or exhausted.
Dispatched means the accounted request path was attempted; `request_ids` and the
request metrics distinguish actual transport dispatch from skipped local setup
or slot waits. Prepared/dispatched attempts are never redispatched after reload.
Completed advice can be applied once, with candidate, scope, steering and current
file hashes revalidated. Applied guidance is saved atomically and remains internal;
it never creates a user event or clears recovery counters. A changed context
invalidates pending guidance. A real user follow-up keeps its existing semantics.

An ignored or invalid consultation preserves eligible existing recovery, including
Unattended worker handoff. Advice can suggest that handoff but cannot select or
fund a model. Local/manual placement remains fixed. Saved worker edits still need
normal checks, independent review and the original commit/merge authorization.

## Packet and result contract

Evidence JSON is at most **16,000 characters**: original/latest operator intent,
accepted item scope, current excerpts and hashes, relevant file index, recent
safe action/error evidence, latest check/review, observed ranges, stall and
remaining limits. Excerpts and omitted context are identified. Changed and
previously inspected files take priority in the index. Repository/model text is
untrusted evidence; missing excerpts never prove missing code.

Output is strict JSON at most **2,048 characters**, with nonempty supplied evidence
references and no extra fields:

- `continue`: action (`inspect`, `edit`, `check`, `answer`), next_step, expected_result.
- `need_context`: permitted path, start_line/end_line (at most 300 lines), reason,
  decision. Already supplied ranges are rejected; new inspection uses worker tools.
- `suggest_handoff`: reason, brief; existing policy decides eligibility.
- `needs_user`: concrete question and reason; the existing decision path displays it.
- `unresolved`: blocker and failed_approach; ordinary eligible recovery continues.

All include `outcome` and `evidence`. Unsafe/unknown explicit paths, generic advice,
policy-bypass suggestions and read-only modifying advice are rejected. The engine
never executes coordinator code, commands, tool calls or file edits. Schema and
bounded lexical validation are not a semantic proof of advice quality; ordinary
worker permissions, scope checks and independent review remain decisive.

## Inference lifecycle and accounting

Idle → one consultation → saved result/guidance → idle. No model polling,
background thinking, periodic consultation or hidden output-repair retry.

The shared local inference slot waits at most **10 seconds**. Existing brief
transport uses **30 seconds** for connection/headers and JSON response reads,
**60 seconds** for an SSE response, and at most **512 output tokens**, with local
reasoning disabled. These are separate transport phases, not a single 30-second
end-to-end promise. Cancellation closes an active response socket/read and joins
its cancellation watchdog; before response headers, urllib's existing 30-second
socket timeout remains the bound. No force-unload is requested. Transport guards
exist only during the active response, never between consultations.

Requests use the normal reservation, reconciliation, persistence and admission
pipeline with `role=coordinator`, `purpose=coordinator_recovery`. They count in
applicable request/time/usage limits, not worker-turn counters. Failed/cancelled
reservations survive. Branch and lifetime accounting reuse the same request IDs;
there is no second charge. Each episode retains request IDs, duration, result and
an observed subsequent edit/check, without claiming overall task completion.

## Validation and cost

Change-scoped validation only; no full-suite gate or live model trial:

- 170 frontend cases, **0.104 seconds**, including settings, coordinator projection,
  actual-result ordering and worker-stall versus user-question labels.
- New packet/schema cases: four, **0.004 seconds**; configuration: three,
  **0.001 seconds**; brief transport/cancellation/accounting: four, **0.002 seconds**.
- Five tiny dispatch cases reuse the existing single-workspace demo fixture:
  **2.25 seconds** combined with packet cases on the final targeted run. The
  smallest initial worker-loop measurement was **0.55 seconds**; final full
  scripted loop about one second. No subprocess check or full Git workflow was
  added to these cases. They run only when selected by affected imports.
- The scripted Interactive loop repeats inspection, consults once, reads a genuinely
  new test excerpt, then edits through normal tools. Cases also cover Off, permission/
  setup/conflict/role exclusions, invalid/offline advice, real question, cancellation
  with retained reservation, stale output, serialized prepared/uncertain/completed
  episodes, no fake user event, and exactly-once lifetime accounting.
- Shared-slot deterministic timeout case is below **0.001 seconds** and uses no
  real sleep; existing cancellation and ledger restoration cases remain passing.
- Existing Unattended handoff fixture extended in place: **9.60 seconds total**,
  no additional repository setup or second multi-item workflow. An ignored local
  consultation falls through to a distinct worker, real checks, independent review
  and commit. Coordinator usage appears once in branch accounting.
- Final focused backend batch: **80 tests / 9.94 seconds** (routing, recovery,
  admission, placement/preferences, counters, accounting and pause contracts).
  Earlier complementary recovery/transport/read-only batch: **71 / 9.21 seconds**.
  Subsequent small edits were rechecked with their focused cases.
- Actual LocalServer static asset delivery: **one existing HTTP test / 0.032 seconds**.

Disposable browser fixture on port 52642: Off/default setup; opt-in and saved model
without placement change; waiting without invented output; actual streamed output;
Details retained through polling and Changes→Chat; guidance followed by worker
continuation; distinct exhausted/question copy; owning-task Pause request;
354 CSS-pixel viewport without horizontal overflow. Fixture was stopped and
viewport restored. Later actual-result/unattended-label adjustments have pure
projection coverage. Personal tasks, keys and running application were untouched.

This validates control flow, not improved model success rates. A later operator-
selected live comparison should use measurement mode with comparable Off/On tasks,
record added calls/tokens/latency and accepted outcomes, and preserve spending policy.

### Paused-chat opt-in and Send feedback follow-up

- Focused coordinator/configuration/recovery/admission/work-limit cases: **26
  passing**; browser-facing HTTP cases: **23 passing** across the batch and one
  targeted rerun. The pre-existing gateway-mutation test needed a concrete task
  on its mock runtime for admission; its rejection assertions are unchanged.
  Socket tests require loopback permission in the development sandbox.
- Frontend: **173 passing / 0.109 seconds**, plus syntax and diff checks. New Send
  cases hold promises explicitly (no timed sleep), cover duplicate submission,
  delayed acknowledgment, rejection/draft retention and switching chats.
- Added deterministic configuration/status assertions are below **0.002 seconds**
  per case. One new dispatch case reuses the tiny workspace fixture: **1.424
  seconds**, with no test subprocess or multi-item Git run. It checks retained
  request/counters/time/placement, no worker dispatch after invalid advice, and no
  second consultation on repeated clicks. No new heavy test was introduced.
- Disposable browser server on port 5189, scripted providers and real engine/API:
  current chat Off while defaults On; explicit reassessment; guidance visible;
  worker edits the same workspace while the earlier saved file and original
  request remain; verification/review still required. An attempted consultation
  is labeled and cannot be renewed. Enter and Send immediately display pending
  delivery; accepted delivery clears it, rejected delivery keeps an editable draft.
- Browser testing also caught Activity rendering overwriting Chat action handlers;
  handlers now bind within their own tab. No personal task or live model was run.
