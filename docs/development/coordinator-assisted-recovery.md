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
stops, exhausted time/turns and already consumed episodes for that request. The
single format-correction exception below retains the existing episode. It keeps
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

The latest review is projected as decision and feedback first, without nested
checks or old diffs crowding out the actual findings. A bounded current patch
across up to four files is supplied separately; file excerpts start near the
latest changed hunk instead of always showing imports. Omitted sections remain
explicit. Worker continuation also receives this current patch/review summary,
so advisory inspection suggestions cannot override already completed work.

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

Prose may use an unambiguous basename of a supplied file (for example `server.py`
for `cheapos/server.py`). A clearly described `/api/...` endpoint or route is not
treated as a filesystem target; traversal and file-like absolute paths remain
rejected. A typed `need_context.path` still requires the exact permitted workspace
path. This changes validation of advisory prose, not file or command permissions.

A previously path-rejected, fully retained reply can be revalidated against its
original packet after a validator fix. **Continue with saved guidance** is offered
only when the reply now passes the full contract and task identity still matches.
Applying it rechecks current file hashes, keeps the existing episode and request
IDs, and records the previous rejection. It makes no coordinator request and
cannot renew consultations. Truncated, still-invalid, already reused and stale
replies remain ineligible; app startup never starts a worker for this action.

## Inference lifecycle and accounting

Idle → one consultation → saved result/guidance → idle. No model polling,
background thinking or periodic consultation. Local recovery requests explicitly
use Ollama's OpenAI-compatible JSON output mode, plus a concrete schema example.
A single complete Markdown JSON fence is accepted, then its contents pass the
same schema, evidence and policy checks. Prose is never mined for an embedded object.

A syntactically malformed JSON reply permits **one format-correction request**
within that episode, announced as **Correcting the coordinator reply format**.
The correction marker is saved before dispatch. Reload, Resume, timeout or a
second malformed reply cannot renew it. Schema/policy rejection, provider failure
and unavailable local inference do not trigger this correction. Both requests
use the same local model and ordinary remaining limits; no remote fallback or
worker-counter reset is added. Current file evidence is checked again first.

An older paused Interactive episode with the exact JSON parse diagnostic and an
unchanged candidate offers **Retry coordinator format** for this unused correction.
The operator need not invent a new prompt; the original episode, request IDs,
duration and usage stay counted. There is no automatic retry on app startup.
New replies retain up to 2,048 characters each (with an explicit truncation flag),
the concrete diagnostic and correction outcome in task history/Details. Earlier
versions discarded the malformed reply, so its exact contents cannot be recovered.

API reference: [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

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

### Coordinator reply-format follow-up

- Diagnosis from retained request metadata: the local model responded, but JSON
  parsing failed. The old implementation discarded the reply, preventing a more
  specific diagnosis of its formatting. The pause now names the parse failure.
- Focused packet/configuration/transport/dispatch batch: **18 passing / 7.70s**.
  Final dispatch/recovery/limits/admission/streaming/Unattended handoff batch:
  **34 passing / 25.72s**, including **25.61s** for the pre-existing full handoff
  fixture. No new heavy test, live inference, deliberate wait or Git workflow
  was added. Existing dispatch cases now cover successful/failed format correction,
  retained accounting, rejection without retry for policy errors, and consumed
  correction markers after reload.
- Frontend: **174 passing / 0.106s**. The single new pure projection case took
  **0.00064s** on its final targeted run. Syntax and diff checks passed.
- Disposable browser fixture with the real engine/API: an older parse-failed
  episode displays the actual cause and **Retry coordinator format**. Clicking
  shows immediate pending feedback, sends one correction, displays guidance, and
  lets the worker edit the same workspace. The original episode/request ID,
  duration, prompt, counters and earlier saved file remain. Changes still require
  verification and review. No personal task was resumed during validation.

### API-reference validation and saved-guidance reuse

- A live retained reply exposed two false rejections: a unique source basename
  and an API endpoint described in prose were both treated as unknown filesystem
  targets. The prior packet also truncated the review before its actual feedback.
- Focused contract/configuration/dispatch/progress checks: **20 passing / 9.64s**.
  Two new pure contract cases cover route versus file references, ambiguous names,
  unsafe/context paths, retained reviewer feedback and changed-hunk selection.
  The entire six-case contract module took **0.005s**. An existing reload fixture
  now checks saved-reply reuse, no inference, no repeated application and unchanged
  usage/counters. No new heavy test or live-model trial was added.
- Frontend: **174 passing / 0.109s**; final affected projection cases **8 passing**.
  Disposable real engine/API browser test: a legacy path-rejected reply offers
  **Continue with saved guidance**, displays immediate pending feedback, and sends
  guidance plus current evidence to the worker. The synthetic provider rejects
  any coordinator call. The worker saved an edit in the original workspace;
  verification and review remained required. The original episode/request ID,
  consumed format-repair marker, duration and earlier saved file stayed intact.
- These checks establish recovery control flow and packet content, not that a
  particular live worker will successfully complete the remaining feature.
